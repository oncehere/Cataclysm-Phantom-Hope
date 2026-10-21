import json
import os
from cph_ai_companion import platform_io
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from cph_ai_companion.budget import BudgetError, ConsumptionLedger


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.owner = "a" * 64
        self.ledger = ConsumptionLedger(self.root)

    def test_reservation_is_private_persistent_and_usage_never_refunds(self):
        self.assertEqual(self.ledger.transact(self.owner, reserve=100, max_calls=2, max_tokens=500), (1, 100))
        restarted = ConsumptionLedger(self.root)
        self.assertEqual(restarted.transact(self.owner), (1, 100))
        self.assertEqual(restarted.transact(self.owner, extra=40), (1, 140))
        fd = platform_io.open_file(self.ledger.path, os.O_RDONLY)
        try:
            self.assertTrue(platform_io.private_file(fd))
        finally:
            os.close(fd)
        self.assertEqual(restarted.transact(self.owner, reserve=100, max_calls=2, max_tokens=500), (2, 240))
        with self.assertRaisesRegex(BudgetError, "session_call_budget_exhausted"):
            restarted.transact(self.owner, reserve=100, max_calls=2, max_tokens=500)
        self.assertEqual(self.ledger.transact(self.owner), (2, 240))

    def test_concurrent_reservations_cannot_spend_the_same_last_call(self):
        def reserve(_):
            try:
                ConsumptionLedger(self.root).transact(self.owner, reserve=1, max_calls=3, max_tokens=100)
                return True
            except BudgetError as exc:
                self.assertEqual(exc.code, "session_call_budget_exhausted")
                return False
        with ThreadPoolExecutor(max_workers=8) as executor:
            self.assertEqual(sum(executor.map(reserve, range(8))), 3)
        self.assertEqual(self.ledger.transact(self.owner), (3, 3))

    def test_failed_atomic_replace_does_not_grant_or_erase_counters(self):
        self.ledger.transact(self.owner, reserve=100, max_calls=3, max_tokens=500)
        with patch("cph_ai_companion.platform_io.replace_file", side_effect=OSError):
            with self.assertRaisesRegex(BudgetError, "budget_ledger_unavailable"):
                self.ledger.transact(self.owner, reserve=100, max_calls=3, max_tokens=500)
        self.assertEqual(ConsumptionLedger(self.root).transact(self.owner), (1, 100))
        self.assertEqual(list(self.root.glob(".runtime-budget*.tmp")), [])

    def test_unknown_corrupt_and_symlink_ledgers_do_not_reset_budget(self):
        for raw in ('{"schema_version":2,"accounts":{}}',
                    '{"schema_version":true,"accounts":{}}',
                    '{"schema_version":1,"accounts":{},"accounts":{}}',
                    json.dumps({"schema_version": 1, "accounts": {self.owner: {"calls": True, "tokens": 0}}})):
            self.ledger.path.write_text(raw)
            self.ledger.path.chmod(0o600)
            with self.assertRaisesRegex(BudgetError, "invalid_budget_ledger"):
                self.ledger.transact(self.owner)
            self.assertEqual(self.ledger.path.read_text(), raw)
        self.ledger.path.unlink()
        target = self.root / "existing"
        target.write_text("preserve")
        self.ledger.path.symlink_to(target)
        with self.assertRaisesRegex(BudgetError, "invalid_budget_ledger"):
            self.ledger.transact(self.owner)
        self.assertEqual(target.read_text(), "preserve")

    def test_token_exhaustion_leaves_reserved_attempt_charged(self):
        self.ledger.transact(self.owner, reserve=100, max_calls=10, max_tokens=100)
        with self.assertRaisesRegex(BudgetError, "session_token_budget_exhausted"):
            self.ledger.transact(self.owner, reserve=1, max_calls=10, max_tokens=100)
        self.assertEqual(self.ledger.transact(self.owner), (1, 100))


if __name__ == "__main__":
    unittest.main()
