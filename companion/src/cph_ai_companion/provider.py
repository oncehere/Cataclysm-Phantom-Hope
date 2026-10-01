"""A bounded, explicitly started Chat Completions adapter.

The SDK is imported only inside the owned worker process. No model-supplied
tools, Python, or shell commands are executed by this module.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import math
import multiprocessing
import os
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


MAX_COMPLETION_BYTES = 1024 * 1024


class ProviderError(Exception):
    """Public errors contain a stable code, never SDK response text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProviderError("invalid_model_json")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ProviderError("invalid_model_json")


def parse_model_json(content: Any) -> dict[str, Any]:
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_COMPLETION_BYTES:
        raise ProviderError("invalid_model_json")
    try:
        value = json.loads(content, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError):
        raise ProviderError("invalid_model_json") from None
    if not isinstance(value, dict):
        raise ProviderError("invalid_model_json")
    return value


@dataclass(frozen=True)
class ProviderConfig:
    base_url: str
    model: str
    api_key_env: str | None = None
    max_output_tokens: int = 2048
    json_mode: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProviderConfig":
        if not isinstance(value, Mapping):
            raise ProviderError("invalid_provider_config")
        value = value.get("llm", value)
        if not isinstance(value, Mapping):
            raise ProviderError("invalid_provider_config")
        base_url = value.get("base_url")
        model = value.get("model")
        key_env = value.get("api_key_env")
        max_output = value.get("max_output_tokens", 2048)
        if not isinstance(base_url, str) or not isinstance(model, str) or not model.strip():
            raise ProviderError("provider_not_configured")
        try:
            url = urlsplit(base_url)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError
            if url.query or url.fragment:
                raise ValueError
            if url.scheme == "http":
                if url.hostname != "localhost" and not ipaddress.ip_address(url.hostname).is_loopback:
                    raise ValueError
            _ = url.port
        except ValueError:
            raise ProviderError("invalid_provider_endpoint") from None
        if key_env is not None and (
            not isinstance(key_env, str) or not key_env.isidentifier() or len(key_env) > 128
        ):
            raise ProviderError("invalid_credential_reference")
        if type(max_output) is not int or not 1 <= max_output <= 65536:
            raise ProviderError("invalid_output_limit")
        return cls(base_url, model, key_env, max_output, value.get("json_mode") is True)


@dataclass(frozen=True)
class Completion:
    value: dict[str, Any]
    usage: dict[str, int] | None = None


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def decode_completion(response: Any) -> Completion:
    """Accept one fully ended textual choice, not a parsable truncated prefix."""
    choices = _field(response, "choices")
    if not isinstance(choices, (list, tuple)) or len(choices) != 1:
        raise ProviderError("invalid_completion")
    choice = choices[0]
    if _field(choice, "finish_reason") != "stop":
        raise ProviderError("incomplete_completion")
    message = _field(choice, "message")
    if message is None or _field(message, "tool_calls") or _field(message, "function_call"):
        raise ProviderError("unexpected_tool_call")
    if _field(message, "refusal"):
        raise ProviderError("model_refused")
    value = parse_model_json(_field(message, "content"))
    raw_usage = _field(response, "usage")
    usage = None
    if raw_usage is not None:
        values = {key: _field(raw_usage, key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        if all(type(item) is int and item >= 0 for item in values.values()):
            usage = values
    return Completion(value, usage)


def _call_openai(config: dict[str, Any], messages: list[dict[str, str]], timeout: float,
                 max_output_tokens: int) -> dict[str, Any]:
    # Unsetting this in the child prevents SDK debug logs from disclosing payloads.
    os.environ.pop("OPENAI_LOG", None)
    for name in ("openai", "httpx", "httpcore"):
        logging.getLogger(name).disabled = True
    try:
        from openai import OpenAI
    except ImportError:
        raise ProviderError("sdk_not_installed") from None
    key_env = config.get("api_key_env")
    api_key = os.environ.get(key_env) if key_env else "local-no-key"
    if not api_key:
        raise ProviderError("credential_missing")
    try:
        with OpenAI(base_url=config["base_url"], api_key=api_key, max_retries=0, timeout=timeout) as client:
            params: dict[str, Any] = {
                "model": config["model"], "messages": messages,
                "stream": False, "max_tokens": max_output_tokens,
            }
            if config.get("json_mode"):
                params["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**params)
            result = decode_completion(response)
            return {"value": result.value, "usage": result.usage}
    except ProviderError:
        raise
    except Exception:
        # HTTP bodies and SDK exception messages can contain prompts, URLs or keys.
        raise ProviderError("provider_request_failed") from None


def _worker_entry(connection: Any, config: dict[str, Any], messages: list[dict[str, str]],
                  timeout: float, max_output_tokens: int, worker: Callable[..., Any]) -> None:
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            try:
                result = {"ok": True, "result": worker(config, messages, timeout, max_output_tokens)}
            except ProviderError as exc:
                result = {"ok": False, "code": exc.code}
            except BaseException:
                result = {"ok": False, "code": "provider_worker_failed"}
            data = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(data) > MAX_COMPLETION_BYTES:
                data = b'{"ok":false,"code":"completion_too_large"}'
            connection.send_bytes(data)
    finally:
        connection.close()


class ProcessProvider:
    """One owned worker at a time, with a wall deadline including SDK work."""

    def __init__(self, config: ProviderConfig | Mapping[str, Any], *,
                 worker: Callable[..., Any] = _call_openai) -> None:
        self.config = config if isinstance(config, ProviderConfig) else ProviderConfig.from_mapping(config)
        self._worker = worker
        self._context = multiprocessing.get_context("spawn")
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._closed = False
        self._process: Any = None

    def complete(self, messages: list[dict[str, str]], *, timeout: float = 30,
                 max_output_tokens: int | None = None,
                 on_wait: Callable[[], bool | None] | None = None) -> Completion:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ProviderError("invalid_timeout")
        if not self._lock.acquire(blocking=False):
            raise ProviderError("provider_busy")
        receiver = sender = process = None
        watchdog = None
        worker_guard = threading.Lock()
        finished = threading.Event()
        expired = threading.Event()
        try:
            if self._closed:
                raise ProviderError("provider_closed")
            self._cancel.clear()
            # Also bound input IPC independently of token accounting.
            if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > MAX_COMPLETION_BYTES:
                raise ProviderError("context_too_large")
            output_limit = max_output_tokens or self.config.max_output_tokens
            if type(output_limit) is not int or not 1 <= output_limit <= self.config.max_output_tokens:
                raise ProviderError("invalid_output_limit")
            receiver, sender = self._context.Pipe(duplex=False)
            process = self._context.Process(
                target=_worker_entry,
                args=(sender, asdict(self.config), messages, timeout, output_limit, self._worker),
                daemon=True,
            )
            deadline = time.monotonic() + timeout
            process.start()
            self._process = process
            sender.close()

            def check_request() -> float:
                remaining = deadline - time.monotonic()
                if expired.is_set() or remaining <= 0:
                    raise ProviderError("provider_timeout")
                if self._cancel.is_set() or self._closed:
                    raise ProviderError("provider_cancelled")
                return remaining

            def enforce_deadline() -> None:
                # Callback RPCs can block the caller. This monitor owns this
                # exact Process object, never a cached PID or a later request.
                # Final cleanup joins it before closing the process handle.
                while not finished.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        expired.set()
                    if remaining <= 0 or self._cancel.is_set() or self._closed:
                        with worker_guard:
                            if process.is_alive():
                                process.kill()
                            process.join(0.2)
                        return
                    finished.wait(min(0.05, remaining))

            watchdog = threading.Thread(target=enforce_deadline, daemon=True)
            watchdog.start()
            next_check = time.monotonic()
            while True:
                remaining = check_request()
                if on_wait is not None and time.monotonic() >= next_check:
                    valid = on_wait()
                    remaining = check_request()
                    if valid is False:
                        raise ProviderError("request_invalidated")
                    next_check = time.monotonic() + 0.2
                if receiver.poll(min(0.05, remaining)):
                    check_request()
                    try:
                        packet = parse_model_json(receiver.recv_bytes(MAX_COMPLETION_BYTES).decode("utf-8"))
                    except (EOFError, OSError, UnicodeError):
                        check_request()
                        raise ProviderError("provider_worker_failed") from None
                    check_request()
                    if packet.get("ok") is not True:
                        code = packet.get("code")
                        allowed = {
                            "sdk_not_installed", "credential_missing", "provider_request_failed",
                            "invalid_model_json", "invalid_completion", "incomplete_completion",
                            "unexpected_tool_call", "model_refused", "completion_too_large",
                        }
                        raise ProviderError(code if code in allowed else "provider_worker_failed")
                    result = packet.get("result")
                    if not isinstance(result, dict) or not isinstance(result.get("value"), dict):
                        raise ProviderError("invalid_completion")
                    check_request()
                    return Completion(result["value"], result.get("usage"))
                check_request()
                with worker_guard:
                    alive = process.is_alive()
                if not alive:
                    check_request()
                    raise ProviderError("provider_worker_failed")
        finally:
            finished.set()
            if watchdog is not None:
                watchdog.join()
            if sender is not None:
                sender.close()
            if receiver is not None:
                receiver.close()
            if process is not None and process.pid is not None:
                with worker_guard:
                    process.join(0.05)
                    if process.is_alive():
                        process.terminate()
                        process.join(0.2)
                    if process.is_alive():
                        process.kill()
                        process.join(0.2)
                    if not process.is_alive():
                        process.close()
            self._process = None
            self._lock.release()

    def cancel(self) -> None:
        self._cancel.set()

    def close(self) -> None:
        self._closed = True
        self.cancel()

    def __enter__(self) -> "ProcessProvider":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
