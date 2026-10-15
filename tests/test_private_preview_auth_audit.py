"""Synthetic-only identity/persistence regressions; never load owner configuration.

Links and cookies stay in memory. Assertions report statuses, never raw tickets.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {'PYTHON_DOTENV_DISABLED': '1'}, clear=True):
    from app.auth import (
        AuthRepository, AuthService, EmailNotVerified, InvalidCredentials,
        PasswordResetInvalid,
    )
    from ops.private_preview.preview_app import SignedPreviewAuth

PASSWORD = 'Synthetic original password 12345'
REPLACEMENT = 'Synthetic replacement password 54321'


class PreviewIdentityPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'synthetic-auth.db'
        self.repository = AuthRepository(self.path)
        self.repository.initialize()
        self.addCleanup(self.repository.database.close)
        self.service = SignedPreviewAuth(AuthService(self.repository), 'a' * 64)

    def verified(self, email):
        account = self.service.register(email, PASSWORD)
        token, _ = self.service.issue_email_verification(account)
        return self.service.verify_email(token)

    def reopen(self):
        self.repository.database.close()
        repository = AuthRepository(self.path)
        repository.initialize()
        self.addCleanup(repository.database.close)
        return SignedPreviewAuth(AuthService(repository), 'a' * 64)

    def test_normalized_identity_reset_and_reopen(self):
        account = self.verified('  Alice@Example.Test  ')
        self.assertEqual(account.email, 'alice@example.test')
        self.assertEqual(self.service.authenticate(' ALICE@example.TEST ', PASSWORD).id, account.id)
        session = self.service.create_session(account)
        # A fresh storage object, same signing key, and persisted session.
        reopened = self.reopen()
        self.assertEqual(reopened.account_for_token(session).id, account.id)
        prepared = reopened.request_password_reset(' ALICE@EXAMPLE.TEST ')
        self.assertIsNotNone(prepared)
        _, ticket, _ = prepared
        reopened.reset_password(ticket, REPLACEMENT)
        reopened.repository.database.close()
        final_repository = AuthRepository(self.path)
        final_repository.initialize()
        self.addCleanup(final_repository.database.close)
        final = SignedPreviewAuth(AuthService(final_repository), 'a' * 64)
        self.assertIsNone(final.account_for_token(session))
        with self.assertRaises(InvalidCredentials):
            final.authenticate('alice@example.test', PASSWORD)
        self.assertEqual(final.authenticate('alice@example.test', REPLACEMENT).id, account.id)
        with self.assertRaises(PasswordResetInvalid):
            final.reset_password(ticket, PASSWORD)
        new_session = final.create_session(account)
        final.logout(new_session)
        self.assertIsNone(final.account_for_token(new_session))

    def test_reset_for_alice_does_not_change_bob_or_bobs_session(self):
        alice = self.verified('alice@example.test')
        bob = self.verified('bob@example.test')
        alice_session = self.service.create_session(alice)
        bob_session = self.service.create_session(bob)
        prepared = self.service.request_password_reset('alice@example.test')
        _, ticket, _ = prepared
        # Reset is bound to its ticket, even while another account is signed in.
        self.assertEqual(self.service.reset_password(ticket, REPLACEMENT).id, alice.id)
        self.assertIsNone(self.service.account_for_token(alice_session))
        self.assertEqual(self.service.account_for_token(bob_session).id, bob.id)
        with self.assertRaises(InvalidCredentials):
            self.service.authenticate('bob@example.test', REPLACEMENT)
        self.assertEqual(self.service.authenticate('bob@example.test', PASSWORD).id, bob.id)
        self.assertEqual(self.service.authenticate('alice@example.test', REPLACEMENT).id, alice.id)
        self.assertIsNone(self.service.request_password_reset('missing@example.test'))

    def test_reset_does_not_bypass_verification(self):
        account = self.service.register('unverified@example.test', PASSWORD)
        verification, _ = self.service.issue_email_verification(account)
        _, ticket, _ = self.service.request_password_reset('unverified@example.test')
        changed = self.service.reset_password(ticket, REPLACEMENT)
        self.assertFalse(changed.email_verified)
        with self.assertRaises(EmailNotVerified):
            self.service.authenticate('unverified@example.test', REPLACEMENT)
        self.service.verify_email(verification)
        self.assertEqual(self.service.authenticate('unverified@example.test', REPLACEMENT).id, account.id)


if __name__ == '__main__':
    unittest.main()
