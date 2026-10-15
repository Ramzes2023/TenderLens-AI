import hashlib
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.auth import (
    AuthRepository,
    AuthService,
    EmailVerificationInvalid,
    EmailVerificationRateLimited,
)


class EmailVerificationCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(
            self.tmp.cleanup
        )

        self.db_path = (
            Path(self.tmp.name)
            / "email-verification.db"
        )

        self.repository = AuthRepository(
            self.db_path
        )

        self.repository.initialize()

        self.service = AuthService(
            self.repository,
            verification_minutes=30,
            verification_cooldown_seconds=60,
        )

    def register(self):
        return self.service.register(
            "user@example.com",
            "very secure password 123",
        )

    def test_new_account_starts_unverified(self):
        account = self.register()

        self.assertFalse(
            account.email_verified
        )

        self.assertIsNone(
            account.email_verified_at
        )

    def test_raw_verification_token_is_never_stored(self):
        account = self.register()

        token, expires_at = (
            self.service
            .issue_email_verification(
                account
            )
        )

        self.assertGreater(
            len(token),
            20,
        )

        self.assertTrue(
            expires_at
        )

        with closing(
            sqlite3.connect(
                self.db_path
            )
        ) as conn:
            stored = conn.execute(
                """
                SELECT token_hash
                FROM auth_email_verifications
                """
            ).fetchone()[0]

        self.assertNotEqual(
            stored,
            token,
        )

        self.assertNotIn(
            token,
            stored,
        )

        self.assertEqual(
            stored,
            hashlib.sha256(
                token.encode(
                    "utf-8"
                )
            ).hexdigest(),
        )

    def test_valid_token_verifies_account_once(self):
        account = self.register()

        token, _ = (
            self.service
            .issue_email_verification(
                account
            )
        )

        verified = (
            self.service
            .verify_email(
                token
            )
        )

        self.assertTrue(
            verified.email_verified
        )

        self.assertIsNotNone(
            verified.email_verified_at
        )

        stored = (
            self.repository
            .find_account_by_id(
                account.id
            )
        )

        self.assertTrue(
            stored.email_verified
        )

        with self.assertRaises(
            EmailVerificationInvalid
        ):
            self.service.verify_email(
                token
            )

    def test_expired_token_is_rejected(self):
        account = self.register()

        raw_token = (
            "expired-email-token"
        )

        past = (
            datetime.now(
                timezone.utc
            )
            - timedelta(
                minutes=5
            )
        ).isoformat(
            timespec="seconds"
        )

        created = (
            self.repository
            .create_email_verification(
                account_id=account.id,
                token_hash=hashlib.sha256(
                    raw_token.encode(
                        "utf-8"
                    )
                ).hexdigest(),
                expires_at=past,
                cooldown_after=None,
            )
        )

        self.assertTrue(
            created
        )

        with self.assertRaises(
            EmailVerificationInvalid
        ):
            self.service.verify_email(
                raw_token
            )

    def test_resend_cooldown_is_enforced(self):
        account = self.register()

        self.service.issue_email_verification(
            account
        )

        with self.assertRaises(
            EmailVerificationRateLimited
        ):
            (
                self.service
                .issue_email_verification(
                    account
                )
            )

    def test_token_rotation_invalidates_previous_pending_token(self):
        account = self.register()

        first, _ = (
            self.service
            .issue_email_verification(
                account,
                enforce_cooldown=False,
            )
        )

        second, _ = (
            self.service
            .issue_email_verification(
                account,
                enforce_cooldown=False,
            )
        )

        self.assertNotEqual(
            first,
            second,
        )

        with self.assertRaises(
            EmailVerificationInvalid
        ):
            self.service.verify_email(
                first
            )

        verified = (
            self.service
            .verify_email(
                second
            )
        )

        self.assertTrue(
            verified.email_verified
        )


class ExistingAccountMigrationTests(unittest.TestCase):
    def test_pre_24n_account_is_grandfathered_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = (
                Path(directory)
                / "legacy-auth.db"
            )

            with closing(
                sqlite3.connect(
                    db_path
                )
            ) as conn:
                conn.execute(
                    """
                    CREATE TABLE auth_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT NOT NULL
                            COLLATE NOCASE
                            UNIQUE,
                        password_hash TEXT NOT NULL,
                        owner_user_id INTEGER UNIQUE,
                        is_active INTEGER
                            NOT NULL
                            DEFAULT 1
                            CHECK(
                                is_active
                                IN (0,1)
                            ),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )

                conn.execute(
                    """
                    INSERT INTO auth_accounts(
                        email,
                        password_hash,
                        owner_user_id,
                        is_active,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?)
                    """,
                    (
                        "legacy@example.com",
                        "legacy-hash",
                        4_000_000_000_001,
                        "2026-01-01T00:00:00+00:00",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )

                conn.commit()

            repository = AuthRepository(
                db_path
            )

            repository.initialize()

            record = (
                repository
                .find_account_by_email(
                    "legacy@example.com"
                )
            )

            self.assertIsNotNone(
                record
            )

            account, _ = record

            self.assertTrue(
                account.email_verified
            )

            self.assertIsNone(
                account.email_verified_at
            )


if __name__ == "__main__":
    unittest.main()
