import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from app.auth import AuthRepository, AuthService, InvalidCredentials, RegistrationError, WEB_OWNER_OFFSET, hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        encoded = hash_password("correct horse battery staple")
        self.assertTrue(encoded.startswith("scrypt$"))
        self.assertNotIn("correct horse battery staple", encoded)
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_password_policy_rejects_short_password(self):
        with self.assertRaises(ValueError):
            hash_password("short")


class AuthRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "auth.db"
        self.repository = AuthRepository(self.db_path)
        self.repository.initialize()
        self.service = AuthService(self.repository)

    def test_register_normalizes_email_and_allocates_owner(self):
        account = self.service.register("  User@Example.COM  ", "very secure password 123")
        self.assertEqual(account.email, "user@example.com")
        self.assertEqual(account.owner_user_id, WEB_OWNER_OFFSET + account.id)
        self.assertTrue(account.is_active)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.service.register("user@example.com", "very secure password 123")
        with self.assertRaises(RegistrationError):
            self.service.register("USER@example.com", "another secure password 456")

    def test_raw_password_is_never_stored(self):
        password = "very secure password 123"
        self.service.register("user@example.com", password)
        with closing(sqlite3.connect(self.db_path)) as conn:
            stored = conn.execute("SELECT password_hash FROM auth_accounts").fetchone()[0]
        self.assertNotEqual(stored, password)
        self.assertNotIn(password, stored)

    def test_login_and_session_round_trip(self):
        account = self.service.register(
            "user@example.com",
            "very secure password 123",
        )

        verification_token, _ = (
            self.service
            .issue_email_verification(
                account,
                enforce_cooldown=False,
            )
        )

        verified = (
            self.service
            .verify_email(
                verification_token
            )
        )

        self.assertTrue(
            verified.email_verified
        )

        authenticated = (
            self.service.authenticate(
                "USER@example.com",
                "very secure password 123",
            )
        )

        self.assertEqual(
            authenticated.id,
            account.id,
        )
        token = self.service.create_session(authenticated)
        self.assertGreater(len(token), 20)
        resolved = self.service.account_for_token(token)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, account.id)
        with closing(sqlite3.connect(self.db_path)) as conn:
            stored_token = conn.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
        self.assertNotEqual(stored_token, token)
        self.assertNotIn(token, stored_token)
        self.service.logout(token)
        self.assertIsNone(self.service.account_for_token(token))

    def test_wrong_password_is_rejected(self):
        self.service.register("user@example.com", "very secure password 123")
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate("user@example.com", "not the right password")

    def test_legacy_owner_link_for_migration(self):
        account = self.service.register("user@example.com", "very secure password 123")
        linked = self.service.link_legacy_owner(account, 1844282717)
        self.assertEqual(linked.owner_user_id, 1844282717)


if __name__ == "__main__":
    unittest.main()
