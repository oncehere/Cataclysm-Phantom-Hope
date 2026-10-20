#!/usr/bin/env python3
"""Opt-in, bounded acceptance against synthetic data. Default is offline.

Use one campaign directory for the entire authorized round. Its counters and
failure stop survive process restarts; game/profile checkpoints cannot reset it.
Credentials are inherited in CPH_LLM_API_KEY or read once from non-echoing stdin.
The CLI always uses the same Windows user-local ledger for this grant.
"""
from __future__ import annotations

import argparse
import getpass
from copy import deepcopy
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from acceptance_cases import (CandidateError, VALIDATION_CODES, correction_for, messages_for,
                              synthetic_cases, validate_candidate)
from cph_ai_companion import platform_io
from cph_ai_companion.budget import BudgetError, ConsumptionLedger
from cph_ai_companion.protocol import ProtocolError, schema_digest
from cph_ai_companion.provider import ProcessProvider, ProviderConfig, ProviderError
from cph_ai_companion.runtime import conservative_input_tokens
from cph_ai_companion.transport import strict_json

MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
CALL_LIMIT = 1000
FAILURE_LIMIT = 3
OWNER = hashlib.sha256(b"CPH Windows builtin acceptance authorized 20261020 max1000").hexdigest()


def campaign_root():
    if not platform_io.WINDOWS or not os.environ.get("LOCALAPPDATA"):
        raise ValueError("windows_campaign_directory_required")
    return Path(os.environ["LOCALAPPDATA"]) / "cph-ai-companion" / "acceptance" / "windows-builtin-20261020"


def fatal_diagnostics(diagnostics):
    return (diagnostics.get("http_status") in (401, 402, 403)
            or diagnostics.get("reason") in ("authentication_failed", "insufficient_balance", "permission_denied")
            or diagnostics.get("error_code") in ("insufficient_quota", "insufficient_balance", "invalid_api_key")
            or diagnostics.get("error_type") in ("insufficient_quota", "billing_error", "authentication_error", "permission_error"))


def cached_candidate(campaign, path, case):
    candidate = validate_candidate(strict_json(path.read_bytes()), case)
    digest = hashlib.sha256(encode(candidate)).hexdigest()
    if not any(call.get("state") == "candidate_validated" and call.get("case") == case["name"]
               and call.get("model") == MODEL and call.get("candidate_sha256") == digest
               and call.get("protocol_digest") == schema_digest() for call in campaign.state["calls"]):
        raise ValueError("candidate_provenance_missing")
    return candidate


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Campaign:
    def __init__(self, root):
        self.root = platform_io.private_directory(root, create=True)
        self.lock = platform_io.open_file(self.root / ".campaign.lock", os.O_RDWR | os.O_CREAT)
        try:
            platform_io.lock_file(self.lock, blocking=False)
            self.ledger = ConsumptionLedger(self.root)
            self.path = self.root / "acceptance-state.json"
            if self.path.exists():
                fd = platform_io.open_file(self.path, os.O_RDONLY)
                with os.fdopen(fd, "rb") as source:
                    if not platform_io.private_file(source.fileno()):
                        raise ValueError("invalid_campaign")
                    self.state = strict_json(source.read(1024 * 1024 + 1))
                if (set(self.state) != {"schema_version", "failures", "pending", "halt", "models", "calls"}
                        or type(self.state["schema_version"]) is not int or self.state["schema_version"] != 1
                        or type(self.state["failures"]) is not int or not 0 <= self.state["failures"] <= CALL_LIMIT
                        or type(self.state["pending"]) is not bool
                        or self.state["halt"] not in (None, "consecutive_failures", "authentication_or_balance")
                        or not isinstance(self.state["calls"], list) or len(self.state["calls"]) > CALL_LIMIT):
                    raise ValueError("invalid_campaign")
                if self.state["pending"]:
                    # A crash or lost reply is a failed attempt, never free quota.
                    self.finish({"state": "interrupted_attempt"}, success=False)
            else:
                # Losing the companion state cannot silently reset the failure stop.
                if self.ledger.transact(OWNER)[0]:
                    raise ValueError("campaign_state_missing")
                self.state = {"schema_version": 1, "failures": 0, "pending": False,
                              "halt": None, "models": None, "calls": []}
                self.save()
        except BaseException:
            self.close()
            raise

    def save(self):
        platform_io.atomic_write(self.path, encode(self.state))

    def reserve(self, estimate):
        if self.state["halt"]:
            raise ValueError("campaign_stopped")
        self.state["pending"] = True
        self.save()
        try:
            used, _ = self.ledger.transact(OWNER, reserve=estimate + 1024,
                                            max_calls=CALL_LIMIT, max_tokens=CALL_LIMIT * 5120)
        except BudgetError:
            self.state["pending"] = False
            self.save()
            raise
        return used

    def finish(self, result, *, success, fatal=False):
        self.state["pending"] = False
        self.state["failures"] = 0 if success else self.state["failures"] + 1
        if fatal:
            self.state["halt"] = "authentication_or_balance"
        elif self.state["failures"] >= FAILURE_LIMIT:
            self.state["halt"] = "consecutive_failures"
        self.state["calls"].append(deepcopy(result))
        self.save()

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def models_preflight():
    request = urllib.request.Request(BASE_URL + "/models", headers={
        "Authorization": "Bearer " + os.environ["CPH_LLM_API_KEY"]})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return {"state": "failed", "code": "models_response_too_large"}
            value = strict_json(raw)
            found = any(isinstance(item, dict) and item.get("id") == MODEL for item in value.get("data", []))
            return {"state": "verified" if found else "failed", "http_status": response.status,
                    "code": "model_found" if found else "model_unavailable", "model": MODEL}
    except urllib.error.HTTPError as exc:
        return {"state": "failed", "http_status": exc.code, "code": "models_http_error"}
    except (OSError, ValueError):
        return {"state": "failed", "code": "models_request_failed"}


def dry_run():
    results = []
    for case in synthetic_cases():
        validate_candidate(case["fixture"], case)
        # Exercise every fixed diagnostic with the longest emitted field path;
        # the known mode enums include their longest spelling for a safe bound.
        corrections = [None] + [{"code": code, "path": "$.tasks[0].constraints.max_distance",
                                 "actual_mode": "prioritize"} for code in sorted(VALIDATION_CODES)]
        estimates = [conservative_input_tokens(messages_for(case, correction)) for correction in corrections]
        if max(estimates) > 4096:
            raise ValueError("input_limit_exceeded")
        results.append({"case": case["name"], "input_upper_bounds": [estimates[0], max(estimates[1:])],
                        "validation_feedback_variants": len(VALIDATION_CODES)})
    return {"state": "offline_validated", "cases": results, "online_calls": 0,
            "call_limit": CALL_LIMIT, "consecutive_failure_limit": FAILURE_LIMIT,
            "protocol_digest": schema_digest(), "native_replay": "not_run"}


def campaign_report(report, campaign, state, **fields):
    used, reserved = campaign.ledger.transact(OWNER)
    return {**report, "state": state, "online_calls": used, "calls_used": used,
            "reserved_tokens": reserved, "calls": campaign.state["calls"], **fields}


def online(root):
    report = dry_run()
    campaign = Campaign(root)
    provider = None
    try:
        if campaign.state["halt"]:
            return campaign_report(report, campaign, "campaign_stopped", reason=campaign.state["halt"])
        if not os.environ.get("CPH_LLM_API_KEY"):
            print("WAITING_FOR_KEY_STDIN", flush=True)
            key = (getpass.getpass("DeepSeek API key (not echoed): ") if sys.stdin.isatty()
                   else sys.stdin.readline(4097)).strip()
            if not key or len(key) > 4096 or any(c.isspace() for c in key):
                raise ValueError("invalid_stdin_credential")
            os.environ["CPH_LLM_API_KEY"] = key
            key = None
        os.environ.pop("OPENAI_LOG", None)
        for name in ("openai", "httpx", "httpcore", "httpx2", "httpcore2"):
            logging.getLogger(name).disabled = True
        if campaign.state["models"] is None:
            campaign.state["models"] = models_preflight()
            if campaign.state["models"].get("http_status") in (401, 402, 403):
                campaign.state["halt"] = "authentication_or_balance"
            campaign.save()
        report["models"] = campaign.state["models"]
        if report["models"]["state"] != "verified":
            return campaign_report(report, campaign, "stopped_at_models")
        candidates = platform_io.private_directory(campaign.root / "candidates", create=True)
        provider = ProcessProvider(ProviderConfig(BASE_URL, MODEL, "CPH_LLM_API_KEY", 1024, True, "disabled"))
        for case in synthetic_cases():
            path = candidates / (case["name"] + "-candidate.json")
            if path.exists():
                cached_candidate(campaign, path, case)
                continue
            correction = None
            while not campaign.state["halt"]:
                messages = messages_for(case, correction)
                estimate = conservative_input_tokens(messages)
                if estimate > 4096:
                    raise ValueError("input_limit_exceeded")
                used = campaign.reserve(estimate)
                result = {"case": case["name"], "attempt": used, "input_upper_bound": estimate,
                          "correction": correction is not None, "model": MODEL, "protocol_digest": schema_digest()}
                started = time.monotonic()
                try:
                    completion = provider.complete(messages, timeout=30, max_output_tokens=1024)
                except ProviderError as exc:
                    result.update(state="provider_failed", code=exc.code, diagnostics=exc.diagnostics,
                                  elapsed_seconds=round(time.monotonic() - started, 3))
                    fatal = fatal_diagnostics(exc.diagnostics)
                    campaign.finish(result, success=False, fatal=fatal)
                    correction = exc.code
                    continue
                result["elapsed_seconds"] = round(time.monotonic() - started, 3)
                result["usage"] = {k: v for k, v in (completion.usage or {}).items()
                                   if k in ("prompt_tokens", "completion_tokens", "total_tokens") and type(v) is int and v >= 0}
                if "total_tokens" in result["usage"]:
                    campaign.ledger.transact(OWNER, extra=max(0, result["usage"]["total_tokens"] - estimate - 1024))
                try:
                    candidate = validate_candidate(completion.value, case)
                except (CandidateError, ProtocolError) as error:
                    correction = correction_for(error, completion.value, case)
                    result.update(state="candidate_rejected", code=correction["code"], validation=correction)
                    campaign.finish(result, success=False)
                    continue
                platform_io.atomic_write(path, encode(candidate))
                result.update(state="candidate_validated", candidate_sha256=hashlib.sha256(encode(candidate)).hexdigest())
                campaign.finish(result, success=True)
                break
            if campaign.state["halt"]:
                break
        return campaign_report(report, campaign,
                               "campaign_stopped" if campaign.state["halt"] else "candidates_validated",
                               reason=campaign.state["halt"], candidate_directory=str(candidates),
                               native_replay="not_run")
    finally:
        if provider:
            provider.close()
        campaign.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()
    root = None
    try:
        root = campaign_root() if args.online else None
        report = online(root) if args.online else dry_run()
    except (ValueError, OSError, BudgetError):
        # Never print provider text, endpoint response bodies or private config.
        report = {"state": "local_validation_failed", "native_replay": "not_run"}
    if args.online and root is not None and root.is_dir():
        platform_io.atomic_write(root / "result.json", encode(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["state"] in ("offline_validated", "candidates_validated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
