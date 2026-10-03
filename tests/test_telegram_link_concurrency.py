import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

from app.auth import AuthRepository, AuthService


class TelegramLinkConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "auth.db"
        self.repository = AuthRepository(self.path)
        self.repository.initialize()
        self.service = AuthService(self.repository)
        self.account = self.repository.create_account(
            "concurrency@example.com",
            "not-a-real-password-hash",
        )

    def test_two_simultaneous_claims_have_exactly_one_winner(self):
        # Repeat the race several times so we exercise separate SQLite
        # connections under actual overlapping claim attempts.
        for _ in range(20):
            token, _ = self.service.create_telegram_link(self.account)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            barrier = Barrier(2)

            def claim():
                repository = AuthRepository(self.path)
                marker = datetime.now(timezone.utc).isoformat(timespec="microseconds")
                barrier.wait(timeout=5)
                return repository.claim_telegram_link(
                    token_hash=token_hash,
                    now=marker,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(claim)
                second = pool.submit(claim)
                results = [first.result(timeout=15), second.result(timeout=15)]

            self.assertEqual(results.count(self.account.id), 1)
            self.assertEqual(results.count(None), 1)


if __name__ == "__main__":
    unittest.main()
