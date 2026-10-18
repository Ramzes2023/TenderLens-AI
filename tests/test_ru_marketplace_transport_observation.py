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
