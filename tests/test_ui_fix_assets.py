"""Pure packaging regressions: no environment loading, database or external services."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UIFixAssets(unittest.TestCase):
    def test_fallback_preserves_real_geometry_and_contains_no_metrics(self):
        static = ROOT / 'app/api/static'
        raw = (static / 'geography_fallback.js').read_text(encoding='utf-8')
        data = json.loads(raw.split('window.ValyqonWorldOutlines = ', 1)[1].strip().removesuffix(';'))
        self.assertEqual(data, json.loads((static / 'geography_world.geojson').read_text(encoding='utf-8')))
        self.assertEqual(len(data['features']), 176)
        self.assertNotIn('tender_count', raw)

    def test_fallback_precedes_map_and_locale_precedes_guidance(self):
        source = (ROOT / 'app/api/saas_shell.py').read_text(encoding='utf-8')
        self.assertLess(source.index('/assets/geography_fallback.js'), source.index('/assets/geography.js'))
        self.assertLess(source.index('/assets/locale.js'), source.index('/assets/workspace_ux.js'))
        self.assertIn('COPY app /app/app', (ROOT / 'Dockerfile').read_text())

    def test_setup_does_not_mutate_tenant_or_call_api(self):
        source = (ROOT / 'app/api/static/workspace_ux.js').read_text(encoding='utf-8')
        self.assertNotIn('fetch(', source)
        self.assertNotIn('state.organizationId =', source)
        self.assertNotIn('state.activeCompanyId =', source)


if __name__ == '__main__':
    unittest.main()
