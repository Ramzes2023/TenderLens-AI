from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from app.api.config import ApiSettings
from app.api.dashboard import dashboard_html
from app.api.main import create_app
from app.api.runtime import ApiRuntime
from app.auth import AuthRepository, AuthService
from app.support import SupportRepository


class RecordingEmailSender:
    public_base_url = "http://testserver"

    def __init__(self):
        self.messages = []

    def send_verification(
        self,
        *,
        recipient,
        verification_url,
        expires_at,
    ):
        self.messages.append(
            {
                "recipient": recipient,
                "verification_url":
                    verification_url,
                "expires_at":
                    expires_at,
            }
        )


def verify_latest(
    client,
    app,
):
    sender = (
        app.state.runtime
        .email_sender
    )

    assert sender.messages

    url = sender.messages[
        -1
    ]["verification_url"]

    token = parse_qs(
        urlsplit(url).query
    )["token"][0]

    verified = client.post(
        "/api/v1/auth/verify-email",
        json={
            "token": token,
        },
    )

    assert (
        verified.status_code
        == 200
    )

    assert (
        verified.json()[
            "email_verified"
        ]
        is True
    )

    return verified.json()


def make_client(tmp_path, provider=None):
    db = Path(tmp_path) / "support.db"

    auth_repo = AuthRepository(db)
    auth_repo.initialize()

    support_repo = SupportRepository(db)
    support_repo.initialize()

    runtime = ApiRuntime(
        provider=provider,
        auth_service=AuthService(
            auth_repo
        ),
        email_sender=RecordingEmailSender(),
        support_repository=support_repo,
    )

    settings = ApiSettings(
        host="127.0.0.1",
        port=8000,
        reload=False,
        api_key="legacy",
    )

    return (
        create_app(
            runtime=runtime,
            settings=settings,
        ),
        support_repo,
    )


def test_support_ui_is_in_shell():
    html = dashboard_html()

    assert 'id="supportCenter"' in html
    assert "VALYQON SUPPORT CENTER" in html
    assert "/assets/support.css" in html
    assert "/assets/support.js" in html


def test_support_ticket_round_trip(tmp_path):
    app, _ = make_client(tmp_path)

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "support@example.com",
                "password": "SupportTest123!",
            },
        )

        assert registered.status_code == 201

        verify_latest(
            client,
            app,
        )

        created = client.post(
            "/api/v1/support/tickets",
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": "support@example.com",
                "category": "technical_problem",
                "subject": "Discovery issue",
                "description": (
                    "Discovery did not load "
                    "after selecting a company."
                ),
                "priority": "normal",
                "page_path": "/dashboard#support",
            },
        )

        assert created.status_code == 201

        ticket = created.json()

        assert ticket["status"] == "open"
        assert ticket["public_id"].startswith(
            "VAL-"
        )

        listed = client.get(
            "/api/v1/support/tickets"
        )

        assert listed.status_code == 200
        assert len(listed.json()) == 1

        detail = client.get(
            "/api/v1/support/tickets/"
            + ticket["public_id"]
        )

        assert detail.status_code == 200


def test_support_requires_session(tmp_path):
    app, _ = make_client(tmp_path)

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        response = client.get(
            "/api/v1/support/tickets"
        )

        assert response.status_code == 401


def test_support_owner_isolation(tmp_path):
    app, _ = make_client(tmp_path)

    with TestClient(
        app,
        follow_redirects=False,
    ) as first:

        assert first.post(
            "/api/v1/auth/register",
            json={
                "email": "first@example.com",
                "password": "SupportTest123!",
            },
        ).status_code == 201

        verify_latest(
            first,
            app,
        )

        created = first.post(
            "/api/v1/support/tickets",
            json={
                "first_name": "First",
                "last_name": "User",
                "email": "first@example.com",
                "category": "other",
                "subject": "Private ticket",
                "description": (
                    "This request belongs "
                    "to the first user only."
                ),
                "priority": "normal",
            },
        )

        assert created.status_code == 201
        ticket_id = created.json()["public_id"]

    with TestClient(
        app,
        follow_redirects=False,
    ) as second:

        assert second.post(
            "/api/v1/auth/register",
            json={
                "email": "second@example.com",
                "password": "SupportTest123!",
            },
        ).status_code == 201

        verify_latest(
            second,
            app,
        )

        listed = second.get(
            "/api/v1/support/tickets"
        )

        assert listed.status_code == 200
        assert listed.json() == []

        detail = second.get(
            "/api/v1/support/tickets/"
            + ticket_id
        )

        assert detail.status_code == 404

class FakeSupportProvider:
    async def generate(
        self,
        prompt,
        *,
        max_tokens=512,
    ):
        assert "VALYQON Support Assistant" in prompt
        assert "LATEST USER MESSAGE" in prompt
        assert max_tokens == 700

        return SimpleNamespace(
            text=(
                "Open Discover and select an active "
                "company before starting discovery."
            ),
            provider="fake",
            model="support-test",
        )


def test_live_support_assistant(tmp_path):
    app, _ = make_client(
        tmp_path,
        provider=FakeSupportProvider(),
    )

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email":
                    "ai-support@example.com",
                "password":
                    "SupportTest123!",
            },
        )

        assert registered.status_code == 201

        verify_latest(
            client,
            app,
        )

        response = client.post(
            "/api/v1/support/assistant",
            json={
                "message":
                    "How do I discover tenders?",
                "history": [],
                "page_path":
                    "/dashboard#support",
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["provider"] == "fake"
        assert body["model"] == "support-test"
        assert "Discover" in body["answer"]


def test_live_support_assistant_requires_llm(
    tmp_path,
):
    app, _ = make_client(tmp_path)

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        assert client.post(
            "/api/v1/auth/register",
            json={
                "email":
                    "no-ai@example.com",
                "password":
                    "SupportTest123!",
            },
        ).status_code == 201

        verify_latest(
            client,
            app,
        )

        response = client.post(
            "/api/v1/support/assistant",
            json={
                "message":
                    "Can you help me?",
            },
        )

        assert response.status_code == 503
