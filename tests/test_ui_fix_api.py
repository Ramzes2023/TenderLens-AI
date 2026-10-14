"""Actual static routing with a supplied inert runtime; no database or environment files."""
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

with patch.dict(os.environ,{'PYTHON_DOTENV_DISABLED':'1'},clear=True):
    from app.api.main import create_app
    from app.api.runtime import ApiRuntime
    from app.api.config import ApiSettings


def test_geography_assets_are_served_without_procurement_services():
    app=create_app(runtime=ApiRuntime(),settings=ApiSettings(host='127.0.0.1',port=8000,reload=False,api_key=None))
    with TestClient(app) as client:
        response=client.get('/assets/geography_world.geojson')
        assert response.status_code==200
        assert response.headers['content-type'].split(';')[0]=='application/geo+json'
        assert len(response.json()['features'])==176
        fallback=client.get('/assets/geography_fallback.js')
        assert fallback.status_code==200
        assert 'javascript' in fallback.headers['content-type']
        assert 'window.ValyqonWorldOutlines' in fallback.text
        for file in ['workspace_locale.js','workspace_ux.js','geography.css']:
            assert client.get('/assets/'+file).status_code==200
