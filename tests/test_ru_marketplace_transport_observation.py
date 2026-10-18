"""Transport observation never counts a status or blocked response as ingestion."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from app.sources.http import ConnectorTransportError
from scripts import ru_marketplace_transport_observation as module


@pytest.mark.parametrize('status', [200, 403, 404, 503])
def test_numeric_status_survives_bounded_rejection_without_payload(monkeypatch, status):
    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs['follow_redirects'] is False
        assert kwargs['trust_env'] is False
        class Client:
            async def get(self, url):
                response = SimpleNamespace(status_code=status, content=b'private-body',
                                           headers={'content-type': 'text/html'})
                await kwargs['event_hooks']['response'][0](response)
                if status != 200:
                    raise ConnectorTransportError(retryable=status == 503)
                return response
        yield Client()
    monkeypatch.setattr(module, 'source_client', client)
    result = asyncio.run(module.probe('tektorg'))
    assert result['http_status'] == status
    assert result['verified_ingestion'] is False
    assert 'private-body' not in str(result)
    assert ('error_class' in result) == (status != 200)


@pytest.mark.parametrize("location,classification", [
    ("/223-fz/procedures/", "SAME_LISTING_SLASH_VARIANT"),
    ("https://www.tektorg.ru/223-fz/procedures", "SAME_LISTING"),
    ("https://www.tektorg.ru/another-path", "SAME_HOST_OTHER_PATH"),
    ("https://evil.example/223-fz/procedures/", "NONCANONICAL_OR_CROSS_ORIGIN"),
    ("https://user:SECRET@www.tektorg.ru/223-fz/procedures/", "NONCANONICAL_OR_CROSS_ORIGIN"),
    ("https://www.tektorg.ru/223-fz/procedures/?token=SECRET", "NONCANONICAL_OR_CROSS_ORIGIN"),
    ("", "ABSENT_OR_OVERSIZED"),
    ("https://www.tektorg.ru/with spaces", "INVALID"),
])
def test_tektorg_307_redirect_diagnostic_never_leaks_or_follows(location, classification):
    result = module.safe_redirect_class(
        location, host="www.tektorg.ru",
        listing_url="https://www.tektorg.ru/223-fz/procedures",
    )
    assert result == classification
    assert "SECRET" not in result
    assert "evil.example" not in result


def test_redirect_http_status_preserved_without_following_private_target(monkeypatch):
    @asynccontextmanager
    async def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        class Client:
            async def get(self, url):
                response = SimpleNamespace(
                    status_code=307, content=b"private-body",
                    headers={"location": "/223-fz/procedures/?session=SECRET"},
                )
                await kwargs["event_hooks"]["response"][0](response)
                raise ConnectorTransportError(retryable=False)
        yield Client()
    monkeypatch.setattr(module, "source_client", client)
    result = asyncio.run(module.probe("tektorg"))
    assert result["http_status"] == 307
    assert result["redirect_class"] == "NONCANONICAL_OR_CROSS_ORIGIN"
    assert not result["verified_ingestion"]
    assert "SECRET" not in str(result)
    assert "private-body" not in str(result)
