#!/usr/bin/env python3
"""Installed-package driver for the isolated native joint test.

The official SDK talks only to a local synthetic HTTP endpoint. The game owns
the NPC, perceived ground item, costs, receipt and safe handoff. This script
never adds the source tree to Python's import path or synthesizes game effects.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
import os
from pathlib import Path
import threading
import time

from cph_ai_companion.config import default_config, load_config
from cph_ai_companion.memory import MemoryStore
from cph_ai_companion.runtime import AgentRuntime
from cph_ai_companion.transport import JsonRpcClient, SessionDescriptor


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("session", "profile", "profile-id", "result"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    result_path = Path(args.result)
    profile = Path(args.profile)
    calls: list[dict] = []
    checkpoints: list[dict] = []

    class JointClient(JsonRpcClient):
        def request(self, method, params=None):
            reply = super().request(method, params)
            if method == "checkpoint" and isinstance(reply, dict) and reply.get("accepted") is True:
                checkpoints.append(dict(params["reference"]))
            return reply

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/chat/completions" or not 0 < length <= 1024 * 1024:
                    raise ValueError("invalid_fake_request")
                body = json.loads(self.rfile.read(length))
                calls.append({"stream": body.get("stream"), "has_tools": "tools" in body})
                payload = json.loads(body["messages"][-1]["content"])
                observed = payload["observations"]["nearby"]["items"]
                rock = next(item for item in observed if item["item_type"] == "rock")
                candidate = {"steps": [{"id": "joint-gather-one", "action": "gather",
                                        "args": {**rock["position"], "item_type": "rock", "count": 1}}]}
                response = {"id": "joint-fake", "object": "chat.completion", "created": 1,
                            "model": "joint-fake", "choices": [{"index": 0, "finish_reason": "stop",
                                                               "message": {"role": "assistant", "content": json.dumps(candidate)}}],
                            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
                data = json.dumps(response).encode()
                self.send_response(200)
            except (ValueError, KeyError, StopIteration, TypeError):
                data = b'{"error":{"type":"invalid_fake_request","message":"invalid_fake_request"}}'
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = default_config()
    config["profile_id"] = args.profile_id
    config["llm"].update(base_url=f"http://127.0.0.1:{server.server_port}/v1", model="joint-fake")
    config["limits"]["max_calls"] = 1
    config["limits"]["session_max_calls"] = 1
    os.environ[config["llm"]["api_key_env"]] = "synthetic-loopback-test-key"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (profile / "background.md").write_text("Synthetic fixed companion for an isolated native test.\n", encoding="utf-8")
    memory = runtime = None
    result: dict = {"state": "failed", "sdk_version": version("openai")}
    exit_code = 1
    try:
        config = load_config(profile)
        memory = MemoryStore(profile, config)
        client = JointClient(SessionDescriptor.load(args.session), timeout=5)
        runtime = AgentRuntime(config, memory, client, profile=profile)
        deadline = time.monotonic() + 45
        gathered = False
        while time.monotonic() < deadline:
            step = runtime.run_once() if not gathered else {"state": "waiting_for_checkpoint"}
            status = client.request("status")
            receipts = [receipt for receipt in status.get("receipts", [])
                        if receipt.get("action") == "gather" and receipt.get("state") == "succeeded"]
            if receipts:
                gathered = True
                # Capture the actual terminal status in the same production path
                # used during cooldown. No model call or forged receipt is needed.
                runtime._capture_receipts(status)
                if status.get("checkpoint_requested") is True:
                    runtime._lifecycle(status)
                if not checkpoints:
                    time.sleep(0.002)
                    continue
                records = memory.retrieve(status["context"], limit=100)
                recorded = [record for record in records if record["kind"] == "receipt"
                            and record.get("data", {}).get("operation_id") == receipts[-1]["operation_id"]]
                if not recorded:
                    raise ValueError("real_receipt_not_journaled")
                runtime.request_stop()
                stopped = runtime.run_once()
                detach = stopped.get("detach", {})
                result.update(state="passed", sdk_calls=len(calls), receipt_state=receipts[-1]["state"],
                              memory_receipts=len(recorded), detach_state=detach.get("detach_state"),
                              actor_id=status.get("actor_id"), non_streaming=all(call["stream"] is False for call in calls),
                              no_tools=all(not call["has_tools"] for call in calls), checkpoint_prepared=True,
                              checkpoint_projection_version=checkpoints[-1]["projection_version"],
                              checkpoint_file_revision=checkpoints[-1]["revision"])
                if result["detach_state"] != "detached":
                    raise ValueError("handoff_not_confirmed")
                exit_code = 0
                break
            if step.get("state") in {"rejected", "stopped", "discarded"}:
                raise ValueError("joint_plan_" + step["state"])
            time.sleep(0.02)
        else:
            raise ValueError("joint_driver_deadline")
    except Exception as exc:
        # Deliberately exclude background, credentials, observations and exception
        # body from this small diagnostic artifact.
        result.update(state="failed", error_type=type(exc).__name__, sdk_calls=len(calls))
    finally:
        if runtime is not None:
            runtime.close()
        if memory is not None:
            memory.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temporary = result_path.with_suffix(".pending")
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(result_path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
