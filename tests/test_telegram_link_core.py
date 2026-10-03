import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth import AuthRepository, AuthService, TelegramLinkError, WEB_OWNER_OFFSET


class TelegramLinkCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "auth.db"
        self.repository = AuthRepository(self.path)
        self.repository.initialize()
        self.service = AuthService(self.repository)

    def account(self, email="owner@example.com"):
        return self.repository.create_account(email, "not-a-real-password-hash")

    def test_ticket_is_hashed_and_can_be_used_once(self):
        account = self.account()
        token, expires_at = self.service.create_telegram_link(account)

        self.assertTrue(token)
        self.assertTrue(expires_at)
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT token_hash, consumed_at FROM auth_telegram_links"
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], hashlib.sha256(token.encode("utf-8")).hexdigest())
        self.assertNotEqual(row[0], token)
        self.assertIsNone(row[1])

        linked = self.service.consume_telegram_link(token, 1844282717)
        self.assertEqual(linked.owner_user_id, 1844282717)

        with self.assertRaises(TelegramLinkError):
            self.service.consume_telegram_link(token, 1844282717)

    def test_expired_ticket_is_rejected(self):
        account = self.account()
        token = "expired-ticket"
        expired = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat(timespec="seconds")
        self.repository.create_telegram_link(
            account_id=account.id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            expires_at=expired,
        )

        with self.assertRaisesRegex(TelegramLinkError, "invalid, expired"):
            self.service.consume_telegram_link(token, 1844282717)

        current = self.repository.find_account_by_id(account.id)
        self.assertGreaterEqual(current.owner_user_id, WEB_OWNER_OFFSET)

    def test_new_ticket_invalidates_previous_ticket(self):
        account = self.account()
        first, _ = self.service.create_telegram_link(account)
        second, _ = self.service.create_telegram_link(account)

        with self.assertRaises(TelegramLinkError):
            self.service.consume_telegram_link(first, 1844282717)

        linked = self.service.consume_telegram_link(second, 1844282717)
        self.assertEqual(linked.owner_user_id, 1844282717)

    def test_claim_is_atomic_until_released(self):
        account = self.account()
        token, _ = self.service.create_telegram_link(account)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        marker = datetime.now(timezone.utc).isoformat(timespec="microseconds")

        claimed = self.repository.claim_telegram_link(
            token_hash=token_hash,
            now=marker,
        )
        self.assertEqual(claimed, account.id)
        self.assertIsNone(
            self.repository.claim_telegram_link(
                token_hash=token_hash,
                now=marker,
            )
        )

        self.repository.release_telegram_link(
            token_hash=token_hash,
            consumed_at=marker,
        )
        claimed_again = self.repository.claim_telegram_link(
            token_hash=token_hash,
            now=marker,
        )
        self.assertEqual(claimed_again, account.id)

    def test_failed_owner_migration_releases_ticket(self):
        account = self.account()
        token, _ = self.service.create_telegram_link(account)

        with closing(sqlite3.connect(self.path)) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tenders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_user_id INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO tenders(owner_user_id) VALUES (?)",
                    (account.owner_user_id,),
                )

        with self.assertRaises(TelegramLinkError):
            self.service.consume_telegram_link(token, 1844282717)

        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        marker = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        self.assertEqual(
            self.repository.claim_telegram_link(
                token_hash=token_hash,
                now=marker,
            ),
            account.id,
        )

    def test_already_linked_account_cannot_issue_another_ticket(self):
        account = self.account()
        token, _ = self.service.create_telegram_link(account)
        linked = self.service.consume_telegram_link(token, 1844282717)

        with self.assertRaisesRegex(TelegramLinkError, "already connected"):
            self.service.create_telegram_link(linked)


if __name__ == "__main__":
    unittest.main()
