import time
import unittest
import importlib.util
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from unittest.mock import patch

from cph_ai_companion.provider import (Completion, ProcessProvider, ProviderConfig,
                                       ProviderError, decode_completion, parse_model_json, _call_openai)
from cph_ai_companion.protocol import task_catalog, validate_tasks
from cph_ai_companion.runtime import build_messages, conservative_input_tokens


def sleeping_worker(*args):
    time.sleep(5)
    return {"value": {"steps": []}}


def safe_worker(*args):
    return {"value": {"steps": []}, "usage": None}


def leaking_worker(*args):
    raise RuntimeError("PRIVATE_KEY PRIVATE_PROMPT PRIVATE_BACKGROUND")


def sdk_client_exception_worker(config, messages, timeout, max_output_tokens):
    exceptions = {"TypeError": TypeError, "ValueError": ValueError, "RuntimeError": RuntimeError}
    with patch("openai.OpenAI", side_effect=exceptions[config["model"]]("SYNTHETIC_PRIVATE_CLIENT_TEXT")):
        return _call_openai(config, messages, timeout, max_output_tokens)


def diagnostic_injection_worker(*args):
    error = ProviderError("provider_request_failed", diagnostics={"reason": "bad_request", "exception_type": "APIStatusError"})
    # Even accidental mutation after construction cannot disclose arbitrary
    # fields/strings through the worker packet.
    error.diagnostics.update(http_status=True, error_type="SYNTHETIC_PRIVATE_TYPE",
                             error_code="SYNTHETIC_PRIVATE_CODE", parameter="SYNTHETIC_PRIVATE_PARAMETER",
                             url="https://private.invalid/key", headers={"Authorization": "SYNTHETIC_PRIVATE_KEY"})
    raise error


def sdk_network_cause_worker(config, messages, timeout, max_output_tokens):
    import ssl
    import httpx2
    from openai import APIConnectionError
    causes = {"tls": lambda: ssl.SSLCertVerificationError(1, "SYNTHETIC_PRIVATE_CERT"),
              "dns": lambda: socket.gaierror(-2, "SYNTHETIC_PRIVATE_HOST"),
              "refused": lambda: ConnectionRefusedError("SYNTHETIC_PRIVATE_ENDPOINT"),
              "proxy": lambda: httpx2.ProxyError("SYNTHETIC_PRIVATE_PROXY"),
              "timeout": lambda: TimeoutError("SYNTHETIC_PRIVATE_TIMEOUT"),
              "too_deep": lambda: ConnectionRefusedError("SYNTHETIC_PRIVATE_ENDPOINT")}
    cause = causes[config["model"]]()
    for _ in range(3 if config["model"] == "too_deep" else 2):
        wrapper = RuntimeError("SYNTHETIC_PRIVATE_WRAPPER")
        wrapper.__cause__ = cause
        cause = wrapper
    error = APIConnectionError(request=httpx2.Request("POST", "https://private.invalid"))
    error.__cause__ = cause
    with patch("openai.OpenAI", side_effect=error):
        return _call_openai(config, messages, timeout, max_output_tokens)


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

    def test_thinking_and_json_options_require_explicit_supported_values(self):
        baseline = {"base_url": "http://127.0.0.1/v1", "model": "fake"}
        self.assertIsNone(ProviderConfig.from_mapping(baseline).thinking_mode)
        for mode in ("enabled", "disabled"):
            self.assertEqual(ProviderConfig.from_mapping({**baseline, "thinking_mode": mode}).thinking_mode, mode)
        for mode in (None, True, "auto", {"type": "enabled"}):
            with self.assertRaisesRegex(ProviderError, "invalid_thinking_mode"):
                ProviderConfig.from_mapping({**baseline, "thinking_mode": mode})
        with self.assertRaisesRegex(ProviderError, "invalid_json_mode"):
            ProviderConfig.from_mapping({**baseline, "json_mode": "true"})

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

    def test_diagnostics_drop_unknown_values_and_fields_across_worker(self):
        with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", "fake"), worker=diagnostic_injection_worker) as provider:
            with self.assertRaises(ProviderError) as caught:
                provider.complete([], timeout=3)
        self.assertEqual(caught.exception.diagnostics, {"reason": "bad_request", "exception_type": "APIStatusError"})
        self.assertEqual(str(caught.exception), "provider_request_failed")
        self.assertIsNone(caught.exception.__cause__)

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_sdk_client_diagnostics_use_fixed_labels_across_worker(self):
        cases = {"TypeError": ("client_type_error", "TypeError"),
                 "ValueError": ("client_error", "ValueError"), "RuntimeError": ("unknown_error", "UnknownError")}
        for name, (reason, exception_type) in cases.items():
            with self.subTest(exception=name):
                with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", name), worker=sdk_client_exception_worker) as provider:
                    with self.assertRaises(ProviderError) as caught:
                        provider.complete([], timeout=10)
                self.assertEqual(caught.exception.diagnostics, {"reason": reason, "exception_type": exception_type})
                self.assertEqual(str(caught.exception), "provider_request_failed")
                self.assertNotIn("SYNTHETIC_PRIVATE", repr(caught.exception))

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_sdk_connection_diagnostics_exclude_endpoint_and_cause(self):
        # Keep a local port bound but not listening, so no other process can
        # acquire it and no external host or service is contacted.
        with socket.socket() as endpoint:
            endpoint.bind(("127.0.0.1", 0))
            config = ProviderConfig(f"http://127.0.0.1:{endpoint.getsockname()[1]}/v1", "fake")
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"}):
                with ProcessProvider(config) as provider:
                    with self.assertRaises(ProviderError) as caught:
                        provider.complete([], timeout=10)
        self.assertEqual(caught.exception.diagnostics, {"reason": "connection_failed", "exception_type": "APIConnectionError"})
        self.assertEqual(str(caught.exception), "provider_request_failed")
        self.assertIsNone(caught.exception.__cause__)

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_sdk_network_diagnostics_only_inspect_known_cause_types_with_depth_bound(self):
        cases = {"tls": "tls_verification_failed", "dns": "dns_failure", "refused": "connection_refused",
                 "proxy": "proxy_error", "timeout": "request_timeout", "too_deep": "connection_failed"}
        for name, reason in cases.items():
            with self.subTest(cause=name):
                with ProcessProvider(ProviderConfig("http://127.0.0.1/v1", name), worker=sdk_network_cause_worker) as provider:
                    with self.assertRaises(ProviderError) as caught:
                        provider.complete([], timeout=10)
                self.assertEqual(caught.exception.diagnostics, {"reason": reason, "exception_type": "APIConnectionError"})
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(caught.exception.diagnostics))
                self.assertNotIn("private.invalid", repr(caught.exception))
                self.assertIsNone(caught.exception.__cause__)

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_sdk_http_diagnostics_survive_worker_without_response_secrets(self):
        cases = {
            400: ("bad_request", "BadRequestError", "invalid_request_error", "unsupported_parameter", "thinking"),
            401: ("authentication_failed", "AuthenticationError", "authentication_error", "invalid_api_key", None),
            402: ("insufficient_balance", "APIStatusError", "insufficient_quota", "insufficient_quota", None),
            429: ("rate_limited", "RateLimitError", "rate_limit_error", "rate_limit_exceeded", None),
            500: ("server_error", "InternalServerError", "server_error", "internal_error", None),
        }
        selected = {"status": 400, "unknown": False}
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                status = selected["status"]
                requests.append(status)
                self.rfile.read(int(self.headers["Content-Length"]))
                _, _, error_type, error_code, parameter = cases[status]
                error = {"message": "SYNTHETIC_PRIVATE_BODY https://private.invalid/key",
                         "type": error_type, "code": error_code, "param": parameter,
                         "private": "SYNTHETIC_PRIVATE_FIELD"}
                if selected["unknown"]:
                    error.update(type="SYNTHETIC_PRIVATE_TYPE", code="SYNTHETIC_PRIVATE_CODE",
                                 param="SYNTHETIC_PRIVATE_PARAMETER")
                data = json.dumps({"error": error}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Private-Fixture", "SYNTHETIC_PRIVATE_HEADER")
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = ProviderConfig(f"http://127.0.0.1:{server.server_port}/v1", "fake", "CPH_LOOPBACK_TEST_KEY")
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost", "CPH_LOOPBACK_TEST_KEY": "SYNTHETIC_PRIVATE_KEY"}):
                with ProcessProvider(config) as provider:
                    for status, (reason, exception_type, error_type, error_code, parameter) in cases.items():
                        with self.subTest(status=status):
                            selected["status"] = status
                            with self.assertRaises(ProviderError) as caught:
                                provider.complete([{"role": "user", "content": "SYNTHETIC_PRIVATE_PROMPT"}], timeout=10)
                            error = caught.exception
                            self.assertEqual(str(error), "provider_request_failed")
                            self.assertEqual(error.code, "provider_request_failed")
                            expected = {"http_status": status, "reason": reason, "exception_type": exception_type,
                                        "error_type": error_type, "error_code": error_code}
                            if parameter:
                                expected["parameter"] = parameter
                            self.assertEqual(getattr(error, "diagnostics", None), expected)
                            public = json.dumps(error.diagnostics) + str(error) + repr(error)
                            self.assertNotIn("SYNTHETIC_PRIVATE", public)
                            self.assertNotIn("private.invalid", public)
                            self.assertIsNone(error.__cause__)
                    selected.update(status=400, unknown=True)
                    with self.assertRaises(ProviderError) as caught:
                        provider.complete([], timeout=10)
                    self.assertEqual(caught.exception.diagnostics, {
                        "http_status": 400, "reason": "bad_request", "exception_type": "BadRequestError"})
            self.assertEqual(requests, list(cases) + [400])  # No implicit SDK retries.
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    @unittest.skipUnless(importlib.util.find_spec("openai"), "Official SDK not installed in this interpreter")
    def test_actual_build_messages_pass_sdk_json_mode_gate(self):
        context = {"world_id": "S", "branch_id": "B", "actor_id": 7, "load_epoch": "L",
                   "request_id": "R", "event_watermark": 1, "policy_version": "P", "memory_version": "M", "game_time": 0}
        request = {"context": context, "observations": {}, "action_catalog": [],
                   "task_catalog": [entry for entry in task_catalog() if entry["name"] == "gather"]}
        messages = build_messages(request, {"background": "", "records": [], "revision": "M"},
                                  {"personality": {}, "limits": {"max_input_tokens": 4096, "max_steps": 5}})
        self.assertLessEqual(conservative_input_tokens(messages), 4096)
        candidate = {"context": context, "tasks": [{"id": "rock", "kind": "gather", "args": {"item_type": "rock", "count": 1}}]}
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                keyword = any("json" in message["content"].lower() for message in body["messages"])
                valid = body.get("response_format") == {"type": "json_object"} and keyword
                calls.append(valid)
                response = ({"id": "json-gate", "object": "chat.completion", "created": 1, "model": "fake",
                             "choices": [{"index": 0, "finish_reason": "stop", "message": {
                                 "role": "assistant", "content": json.dumps(candidate)}}]} if valid else
                            {"error": {"type": "invalid_request_error", "code": "invalid_request_error",
                                       "message": "SYNTHETIC_PRIVATE_JSON_GATE"}})
                data = json.dumps(response).encode()
                self.send_response(200 if valid else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            config = ProviderConfig(f"http://127.0.0.1:{server.server_port}/v1", "fake", json_mode=True)
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1,localhost"}):
                with ProcessProvider(config) as provider:
                    with self.assertRaises(ProviderError) as missing:
                        provider.complete([{"role": "user", "content": "Return an object"}], timeout=10)
                    self.assertEqual(missing.exception.diagnostics["http_status"], 400)
                    self.assertEqual(missing.exception.diagnostics["reason"], "bad_request")
                    actual = provider.complete(messages, timeout=10)
                    self.assertEqual(validate_tasks(actual.value), candidate)
            self.assertEqual(calls, [False, True])  # Two requests, with no error retry.
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

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
                error_mode.clear()
                for mode in ("disabled", "enabled"):
                    explicit = ProviderConfig(config.base_url, "fake", max_output_tokens=64,
                                              json_mode=True, thinking_mode=mode)
                    with ProcessProvider(explicit) as provider:
                        provider.complete([], timeout=10)
            self.assertEqual(len(requests), 4)  # one 500 has no SDK retries
            self.assertEqual(requests[0][0], "/v1/chat/completions")
            self.assertIs(requests[0][1]["stream"], False)
            self.assertEqual(requests[0][1]["max_tokens"], 64)
            self.assertNotIn("tools", requests[0][1])
            self.assertNotIn("thinking", requests[0][1])
            self.assertNotIn("response_format", requests[0][1])
            for index, mode in ((2, "disabled"), (3, "enabled")):
                self.assertEqual(requests[index][1]["thinking"], {"type": mode})
                self.assertEqual(requests[index][1]["response_format"], {"type": "json_object"})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
