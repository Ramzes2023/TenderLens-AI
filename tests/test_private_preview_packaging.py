import unittest
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / 'ops/private_preview'


class PreviewBuildPackagingTests(unittest.TestCase):
    def test_safe_archive_contains_current_ui_and_excludes_private_material(self):
        import json
        import subprocess
        import sys
        import tarfile
        import shutil
        builder = ROOT / 'artifacts/private-preview-preflight/build_safe_archive.py'
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / 'source'
            stage.mkdir()
            for name in ('app', 'ops'):
                shutil.copytree(ROOT / name, stage / name,
                                ignore=shutil.ignore_patterns('__pycache__'))
            (stage / 'config').mkdir()
            shutil.copyfile(ROOT / 'config/company_profile.example.json',
                            stage / 'config/company_profile.example.json')
            private = ('app/.env', 'app/customer.key', 'app/data/accounts.json',
                       'ops/secrets/token.txt', 'app/customers.csv')
            for name in private:
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('PRIVATE_SENTINEL')
            output = Path(directory) / 'preview.tar.gz'
            subprocess.run([sys.executable, str(builder), str(stage), str(output)],
                           check=True, capture_output=True, text=True)
            with tarfile.open(output, 'r:gz') as archive:
                names = archive.getnames()
                expected = [p.relative_to(ROOT).as_posix()
                            for p in (ROOT / 'app/api/static').rglob('*') if p.is_file()]
                expected.append('app/api/saas_shell.py')
                for name in expected:
                    self.assertIn(name, names)
                    self.assertEqual(archive.extractfile(name).read(),
                                     (ROOT / name).read_bytes())
                world = json.load(archive.extractfile('app/api/static/geography_world.geojson'))
                self.assertEqual(len(world['features']), 176)
                for name in private:
                    self.assertNotIn(name, names)
                self.assertTrue(all(member.isfile() for member in archive.getmembers()))
        recipe = (OPS / 'Dockerfile.preview.txt').read_text()
        self.assertIn('COPY app /app/app', recipe)
        ignore = (OPS / 'Dockerfile.preview.txt.dockerignore').read_text()
        self.assertIn('!app/api/static/**', ignore)

    def test_published_services_have_bridge_and_database_stays_internal(self):
        compose = (OPS / 'compose.yaml').read_text()
        api, rest = compose.split('\n  db:\n', 1)
        db, mailpit = rest.split('\n  mailpit:\n', 1)
        self.assertIn('networks: [isolated, loopback]', api)
        self.assertIn('networks: [isolated]', db)
        self.assertNotIn('ports:', db)
        self.assertIn('networks: [isolated, loopback]', mailpit)
        self.assertIn('internal: true', compose)
        self.assertIn('com.docker.network.bridge.enable_ip_masquerade: "false"', compose)
        self.assertIn('com.docker.network.bridge.host_binding_ipv4: "127.0.0.1"', compose)
        factory = (OPS / 'preview_app.py').read_text()
        self.assertLess(factory.index('        install()'), factory.index('    from app.api.main import create_app'))

    def test_copied_runtime_source_permissions_are_normalized_before_user(self):
        recipe = (OPS / 'Dockerfile.preview.txt').read_text()
        normalization = ('RUN chmod 755 /app && '
                         'find /app/app /app/config /app/ops -type d -exec chmod 755 {} + && '
                         'find /app/app /app/config /app/ops -type f -exec chmod 644 {} +')
        self.assertIn(normalization, recipe)
        # All copies must precede normalization, which must precede privilege drop.
        self.assertLess(recipe.rindex('\nCOPY '), recipe.index(normalization))
        self.assertLess(recipe.index(normalization), recipe.index('\nUSER preview'))
        self.assertNotIn('chmod 777', recipe)
        self.assertIn('chown preview:preview /app/data', recipe)

    def test_packaged_build_recipe_resolves_and_matches_canonical(self):
        import re
        compose = (OPS / 'compose.yaml').read_text()
        context = re.search(r'^      context: (.+)$', compose, re.M).group(1)
        recipe = re.search(r'^      dockerfile: (.+)$', compose, re.M).group(1)
        build_root = (OPS / context).resolve()
        self.assertEqual(build_root, ROOT)
        packaged = build_root / recipe
        self.assertEqual(packaged.suffix, '.txt')
        self.assertEqual(packaged.read_bytes(), (OPS / 'Dockerfile.preview').read_bytes())
        self.assertEqual(Path(str(packaged) + '.dockerignore').read_bytes(),
                         (OPS / 'Dockerfile.preview.dockerignore').read_bytes())
        # A source-only archive must preserve the relative repository layout.
        with tempfile.TemporaryDirectory() as directory:
            import shutil
            stage = Path(directory)
            for source in (OPS / 'compose.yaml', packaged, Path(str(packaged) + '.dockerignore')):
                target = stage / source.relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            staged_context = (stage / 'ops/private_preview' / context).resolve()
            self.assertTrue((staged_context / recipe).is_file())
            self.assertTrue(Path(str(staged_context / recipe) + '.dockerignore').is_file())

