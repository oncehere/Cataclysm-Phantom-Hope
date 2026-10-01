import time
import unittest
import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from unittest.mock import patch

from cph_ai_companion.provider import (Completion, ProcessProvider, ProviderConfig,
                                      ProviderError, decode_completion, parse_model_json)


def sleeping_worker(*args):
    time.sleep(5)
    return {"value": {"steps": []}}


def safe_worker(*args):
    return {"value": {"steps": []}, "usage": None}


def leaking_worker(*args):
    raise RuntimeError("PRIVATE_KEY PRIVATE_PROMPT PRIVATE_BACKGROUND")


class ProviderTests(unittest.TestCase):
    def response(self, **overrides):
        response = {"choices": [{"finish_reason": "stop", "message": {"content": '{"steps":[]}'}}]}
        response["choices"][0].update(overrides)
        return response

    def test_requires_fully_finished_text_not_tool_or_truncated_json(self):
        self.assertEqual(decode_completion(self.response()), Completion({"steps": []}, None))
        for reason in (None, "length", "tool_calls", "content_filter"):
            with self.assertRaises(ProviderError):
                decode_completion(self.response(finish_reason=reason))
        with self.assertRaisesRegex(ProviderError, "unexpected_tool_call"):
            decode_completion(self.response(message={"content": '{"steps":[]}', "tool_calls": [{}]}))

    def test_json_duplicates_nan_and_code_fences_rejected(self):
        for value in ('{"x":1,"x":2}', '{"x":NaN}', '```json\n{}\n```', '[]', 17):
            with self.assertRaises(ProviderError):
                parse_model_json(value)

    def test_endpoint_and_credentials_never_hidden_in_config(self):
        for url in ("https://key:secret@example.test/v1", "http://example.test", "https://example.test?key=secret"):
            with self.assertRaises(ProviderError) as caught:
                ProviderConfig.from_mapping({"base_url": url, "model": "model"})
            self.assertNotIn("secret", str(caught.exception))
        local = ProviderConfig.from_mapping({"base_url": "http://127.0.0.1:8888/v1", "model": "fake"})
        self.assertEqual(local.model, "fake")

    def test_worker_has_hard_wall_deadline_and_is_terminated(self):
        provider = ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=sleeping_worker)
        start = time.monotonic()
        with self.assertRaisesRegex(ProviderError, "provider_timeout"):
            provider.complete([{"role": "user", "content": "x"}], timeout=0.2)
        self.assertLess(time.monotonic() - start, 2)
        self.assertIsNone(provider._process)
        provider.close()

    def test_worker_success_and_exception_redaction(self):
        config = ProviderConfig("http://127.0.0.1/v1", "fake")
        with ProcessProvider(config, worker=safe_worker) as provider:
            self.assertEqual(provider.complete([], timeout=3).value, {"steps": []})
        with ProcessProvider(config, worker=leaking_worker) as provider:
            with self.assertRaises(ProviderError) as caught:
                provider.complete([], timeout=3)
            self.assertEqual(str(caught.exception), "provider_worker_failed")
        with self.assertRaisesRegex(ProviderError, "provider_closed"):
            provider.complete([], timeout=1)

    def test_blocking_wait_callback_cannot_extend_owned_worker_deadline(self):
        with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=sleeping_worker) as provider:
            observed = []

            def blocked_rpc():
                owned_process = provider._process
                time.sleep(0.5)  # A bounded observer RPC outlives the model timeout.
                observed.append(owned_process.is_alive())
                return True

            with self.assertRaisesRegex(ProviderError, "^provider_timeout$"):
                provider.complete([], timeout=0.15, on_wait=blocked_rpc)
            self.assertEqual(observed, [False])  # Dead before the callback returned.
            self.assertIsNone(provider._process)

    def test_late_read_of_successful_completion_after_callback_is_not_accepted(self):
        with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=safe_worker) as provider:
            def blocked_rpc():
                time.sleep(0.5)
                return True

            with self.assertRaisesRegex(ProviderError, "^provider_timeout$"):
                provider.complete([], timeout=0.15, on_wait=blocked_rpc)
            self.assertIsNone(provider._process)
            # The old watchdog cannot cancel a subsequent invocation.
            self.assertEqual(provider.complete([], timeout=3).value, {"steps": []})

    def test_signal_cancellation_terminates_worker_during_blocked_callback(self):
        with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=sleeping_worker) as provider:
            observed = []

            def blocked_rpc():
                owned_process = provider._process
                provider.cancel()
                time.sleep(0.2)
                observed.append(owned_process.is_alive())
                return True

            with self.assertRaisesRegex(ProviderError, "^provider_cancelled$"):
                provider.complete([], timeout=3, on_wait=blocked_rpc)
            self.assertEqual(observed, [False])
            self.assertIsNone(provider._process)

    def test_invalidation_cancels_owned_worker(self):
        with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=sleeping_worker) as provider:
            with self.assertRaisesRegex(ProviderError, "request_invalidated"):
                provider.complete([], timeout=3, on_wait=lambda: False)
            self.assertIsNone(provider._process)

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_official_sdk_against_loopback_http_and_no_implicit_retry(self):
        requests = []
        error_mode = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                requests.append((self.path, json.loads(self.rfile.read(length))))
                body = ({"error": {"message": "SYNTHETIC PRIVATE SERVER TEXT", "type": "server_error"}}
                        if error_mode.is_set() else
                        {"id": "fake", "object": "chat.completion", "created": 1, "model": "fake",
                         "choices": [{"index": 0, "finish_reason": "stop",
                                      "message": {"role": "assistant", "content": '{"steps":[]}'}}],
                         "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}})
                encoded = json.dumps(body).encode()
                self.send_response(500 if error_mode.is_set() else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = ProviderConfig(f"http://127.0.0.1:{server.server_port}/v1", "fake", max_output_tokens=64)
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"}):
                with ProcessProvider(config) as provider:
                    actual = provider.complete([{"role": "user", "content": "Synthetic local test"}], timeout=10)
                    self.assertEqual(actual, Completion({"steps": []}, {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}))
                    error_mode.set()
                    with self.assertRaisesRegex(ProviderError, "^provider_request_failed$"):
                        provider.complete([], timeout=10)
            self.assertEqual(len(requests), 2)  # one success plus one 500, no SDK retries
            self.assertEqual(requests[0][0], "/v1/chat/completions")
            self.assertIs(requests[0][1]["stream"], False)
            self.assertEqual(requests[0][1]["max_tokens"], 64)
            self.assertNotIn("tools", requests[0][1])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
