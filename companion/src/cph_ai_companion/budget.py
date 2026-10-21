"""Private consumption counters independent of game and cognition checkpoints.

An attempt is durably reserved before a worker starts. Unknown, failed and
cancelled calls retain that reservation; later usage can only increase it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from . import platform_io


class BudgetError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


MAX_COUNTER = 10 ** 18


class ConsumptionLedger:
    """One small profile-local ledger, serialized independently of memory saves."""

    def __init__(self, profile: Path) -> None:
        self.root = platform_io.private_directory(profile, create=True)
        self.path = profile / "runtime-budget.json"

    def _read(self) -> dict[str, Any]:
        try:
            descriptor = platform_io.open_file(self.path, os.O_RDONLY)
        except FileNotFoundError:
            return {}
        except OSError:
            raise BudgetError("invalid_budget_ledger") from None
        try:
            with os.fdopen(descriptor, "rb") as source:
                if not platform_io.private_file(source.fileno()):
                    raise ValueError()
                raw = source.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise ValueError()
            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError()
                    result[key] = item
                return result
            data = json.loads(raw, object_pairs_hook=unique)
            if (not isinstance(data, dict) or set(data) != {"schema_version", "accounts"}
                    or type(data["schema_version"]) is not int or data["schema_version"] != 1):
                raise ValueError()
            accounts = data["accounts"]
            if not isinstance(accounts, dict) or len(accounts) > 256:
                raise ValueError()
            for key, account in accounts.items():
                if not re.fullmatch(r"[a-f0-9]{64}", key) or not isinstance(account, dict) or set(account) != {"calls", "tokens"}:
                    raise ValueError()
                if any(type(n) is not int or not 0 <= n <= MAX_COUNTER for n in account.values()):
                    raise ValueError()
            return accounts
        except (OSError, ValueError, TypeError, RecursionError):
            raise BudgetError("invalid_budget_ledger") from None

    def _write(self, accounts: dict[str, Any]) -> None:
        if self.path.is_symlink():
            raise BudgetError("invalid_budget_ledger")
        encoded = json.dumps({"schema_version": 1, "accounts": accounts}, separators=(",", ":")).encode("utf-8")
        platform_io.atomic_write(self.path, encoded)

    def transact(self, owner: str, *, reserve: int = 0, extra: int = 0,
                 max_calls: int = 0, max_tokens: int = 0) -> tuple[int, int]:
        try:
            descriptor = platform_io.open_file(self.root / ".runtime-budget.lock", os.O_CREAT | os.O_RDWR)
            with os.fdopen(descriptor, "rb") as lock:
                if not platform_io.private_file(lock.fileno()):
                    raise BudgetError("invalid_budget_ledger")
                platform_io.lock_file(lock.fileno())
                accounts = self._read()
                account = accounts.get(owner, {"calls": 0, "tokens": 0})
                if reserve:
                    if account["calls"] >= max_calls:
                        raise BudgetError("session_call_budget_exhausted")
                    if account["tokens"] + reserve > max_tokens:
                        raise BudgetError("session_token_budget_exhausted")
                if reserve or extra:
                    if owner not in accounts and len(accounts) >= 256:
                        raise BudgetError("budget_ledger_full")
                    accounts[owner] = {"calls": account["calls"] + bool(reserve),
                                       "tokens": min(MAX_COUNTER, account["tokens"] + reserve + extra)}
                    self._write(accounts)
                    account = accounts[owner]
                return account["calls"], account["tokens"]
        except OSError:
            raise BudgetError("budget_ledger_unavailable") from None
