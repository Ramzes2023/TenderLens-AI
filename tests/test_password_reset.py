"""Password reset persistence and service security contracts."""
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.auth import (
    AuthRepository, AuthRepositoryError, AuthService, EmailNotVerified,
    InvalidCredentials, PasswordResetInvalid, PasswordResetRateLimited,
    verify_password,
)

OLD_PASSWORD = "original secure password 123"
NEW_PASSWORD = "replacement secure password 456"


@pytest.fixture
def core(tmp_path):
    repository = AuthRepository(tmp_path / "reset.db")
    repository.initialize()
    service = AuthService(repository)
    account = service.register("user@example.com", OLD_PASSWORD)
    return repository, service, account


def rows(repository, sql, params=()):
    with closing(repository._connect()) as conn:
        return conn.execute(sql, params).fetchall()


def execute(repository, sql, params=()):
    with closing(repository._connect()) as conn:
        with conn:
            conn.execute(sql, params)


def test_hash_only_and_thirty_minute_expiry(core):
    repository, service, account = core
    before = datetime.now(timezone.utc)
    with patch("app.auth.service.secrets.token_urlsafe", return_value="raw-reset-token") as generate:
        token, expires = service.issue_password_reset(account)
    generate.assert_called_once_with(32)
    ticket = rows(repository, "SELECT * FROM auth_password_resets")[0]
    assert ticket["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in tuple(ticket)
    assert 1798 <= (datetime.fromisoformat(expires) - before).total_seconds() <= 1800
    assert 1799 <= (datetime.fromisoformat(expires) - datetime.fromisoformat(ticket["created_at"])).total_seconds() <= 1800


def test_expiry_boundary_and_replay(core):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    execute(repository, "UPDATE auth_password_resets SET expires_at=?", (repository._now(),))
    with pytest.raises(PasswordResetInvalid):
        service.reset_password(token, NEW_PASSWORD)
    token, _ = service.issue_password_reset(account, enforce_cooldown=False)
    service.reset_password(token, NEW_PASSWORD)
    with pytest.raises(PasswordResetInvalid):
        service.reset_password(token, OLD_PASSWORD)


def test_rotation_and_sixty_second_cooldown(core):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    with pytest.raises(PasswordResetRateLimited):
        service.issue_password_reset(account)
    assert service.request_password_reset(account.email) is None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    execute(repository, "UPDATE auth_password_resets SET created_at=?",
            ((now - timedelta(seconds=59)).isoformat(),))
    with patch("app.auth.service.datetime") as clock:
        clock.now.return_value = now
        with pytest.raises(PasswordResetRateLimited):
            service.issue_password_reset(account)
        execute(repository, "UPDATE auth_password_resets SET created_at=?",
                ((now - timedelta(seconds=60)).isoformat(),))
        fresh, _ = service.issue_password_reset(account)
    assert len(rows(repository, "SELECT * FROM auth_password_resets WHERE consumed_at IS NULL")) == 1
    with pytest.raises(PasswordResetInvalid):
        service.reset_password(token, NEW_PASSWORD)
    service.reset_password(fresh, NEW_PASSWORD)


def test_revoke_preserves_cooldown(core):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    service.revoke_password_reset(token)
    with pytest.raises(PasswordResetInvalid):
        service.reset_password(token, NEW_PASSWORD)
    assert service.request_password_reset(account.email) is None


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_password_policy_reused_without_consuming_token(core, password):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    with pytest.raises(PasswordResetInvalid, match="Password must contain"):
        service.reset_password(token, password)
    assert rows(repository, "SELECT consumed_at FROM auth_password_resets")[0][0] is None
    service.reset_password(token, NEW_PASSWORD)


def test_password_change_revokes_all_sessions_and_other_tickets(core):
    repository, service, account = core
    execute(repository, "UPDATE auth_accounts SET email_verified=1, updated_at='2000-01-01' WHERE id=?", (account.id,))
    account = repository.find_account_by_id(account.id)
    sessions = [service.create_session(account) for _ in range(3)]
    token, _ = service.issue_password_reset(account)
    # Simulate a legacy extra pending ticket; reset must invalidate every ticket.
    execute(repository, "INSERT INTO auth_password_resets VALUES ('other', ?, ?, NULL, ?)",
            (account.id, "2099-01-01", repository._now()))
    result = service.reset_password(token, NEW_PASSWORD)
    assert result.updated_at != "2000-01-01"
    with pytest.raises(InvalidCredentials):
        service.authenticate(account.email, OLD_PASSWORD)
    assert service.authenticate(account.email, NEW_PASSWORD).id == account.id
    assert all(service.account_for_token(session) is None for session in sessions)
    assert not rows(repository, "SELECT * FROM auth_sessions")
    assert not rows(repository, "SELECT * FROM auth_password_resets WHERE consumed_at IS NULL")


def test_unverified_stays_unverified(core):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    result = service.reset_password(token, NEW_PASSWORD)
    assert not result.email_verified
    assert result.email_verified_at is None
    assert verify_password(NEW_PASSWORD, repository.find_account_by_email(account.email)[1])
    with pytest.raises(EmailNotVerified):
        service.authenticate(account.email, NEW_PASSWORD)
    verify_token, _ = service.issue_email_verification(result)
    service.verify_email(verify_token)
    assert service.authenticate(account.email, NEW_PASSWORD).email_verified


def test_unknown_inactive_and_deactivated_ticket(core):
    repository, service, account = core
    assert service.request_password_reset("missing@example.com") is None
    assert service.request_password_reset("bad email") is None
    token, _ = service.issue_password_reset(account)
    execute(repository, "UPDATE auth_accounts SET is_active=0 WHERE id=?", (account.id,))
    assert service.request_password_reset(account.email) is None
    with pytest.raises(PasswordResetInvalid):
        service.reset_password(token, NEW_PASSWORD)


def test_reset_transaction_rolls_back_on_session_failure(core):
    repository, service, account = core
    session = service.create_session(account)
    token, _ = service.issue_password_reset(account)
    execute(repository, """CREATE TRIGGER fail_revoke BEFORE DELETE ON auth_sessions
            BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
    with pytest.raises(AuthRepositoryError):
        repository.consume_password_reset(
            token_hash=hashlib.sha256(token.encode()).hexdigest(), password_hash="changed",
            now=repository._now(),
        )
    assert verify_password(OLD_PASSWORD, repository.find_account_by_email(account.email)[1])
    assert rows(repository, "SELECT consumed_at FROM auth_password_resets")[0][0] is None
    assert service.account_for_token(session) is not None


def test_concurrent_claim_only_one_succeeds(core):
    repository, service, account = core
    token, _ = service.issue_password_reset(account)
    def reset():
        try:
            service.reset_password(token, NEW_PASSWORD)
            return True
        except PasswordResetInvalid:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: reset(), range(2))) == [False, True]


def test_additive_schema_is_idempotent_and_cascades(core):
    repository, service, account = core
    service.issue_password_reset(account)
    repository.initialize()
    assert len(rows(repository, "SELECT * FROM auth_password_resets")) == 1
    indexes = rows(repository, "PRAGMA index_list(auth_password_resets)")
    assert {row["name"] for row in indexes} >= {"idx_auth_password_resets_account", "idx_auth_password_resets_expires"}
    # Existing personal-workspace foreign keys intentionally restrict account deletion.
    execute(repository, "DELETE FROM organizations WHERE personal_account_id=?", (account.id,))
    execute(repository, "DELETE FROM auth_accounts WHERE id=?", (account.id,))
    assert not rows(repository, "SELECT * FROM auth_password_resets")
