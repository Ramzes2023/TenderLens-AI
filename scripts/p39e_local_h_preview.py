"""Opt-in, static P39D fixture viewer. No server or application integration."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.cache/phase24p3/p39e-preview/index.html'
ASSETS = Path(__file__).with_name('p39e_preview')
sys.path.insert(0, str(ROOT))


def offline_guard(event, args):
    # asyncio creates an internal socketpair; creation alone is not network IO.
    if event.startswith('socket.') and event != 'socket.__new__':
        raise RuntimeError('offline_network_denied')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = os.fsdecode(args[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold().rstrip(' .')
        if name == '.env' or name.startswith(('.env.', '.env:')):
            raise RuntimeError('offline_secret_denied')


def escaped_json(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


async def collect(guarded=False):
    if guarded:
        # Installed after stdlib event-loop wakeup pair initialization, before H imports.
        sys.addaudithook(offline_guard)
    from app.analytics.offline_fixture import CASES, FIXTURE_SHA256, fixture_payload, stable, calculate, OUTPUT_LIMIT
    from app.analytics.offline_spike import FixtureSpike
    gate = FixtureSpike()
    cases = {}
    try:
        for case in CASES:
            expected = calculate(fixture_payload(case))
            envelope = await gate.run(case)
            result = envelope['result']
            if len(stable(result)) > OUTPUT_LIMIT or stable(result) != stable(expected):
                raise ValueError('output_contract')
            cases[case] = result
        if gate.active or gate.tasks or len(gate.receipts) != len(CASES):
            raise ValueError('worker_cleanup')
        return {'fixture_sha256': FIXTURE_SHA256, 'cases': cases}
    finally:
        await gate.shutdown()


def render(data):
    css = (ASSETS / 'style.css').read_text(encoding='utf-8')
    js = (ASSETS / 'view.js').read_text(encoding='utf-8')
    def digest(text):
        return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()
    csp = "default-src 'none'; script-src 'sha256-" + digest(js) + "'; style-src 'sha256-" + digest(css) + "'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'"
    template = (ASSETS / 'page.html').read_text(encoding='utf-8')
    return template.replace('@@CSP@@', csp).replace('@@CSS@@', css).replace('@@DATA@@', escaped_json(data)).replace('@@JS@@', js)


def build(target=TARGET, guarded=False):
    # Invalidate old success before a rebuild; never retain a stale successful file.
    target.unlink(missing_ok=True)
    data = asyncio.run(collect(True) if guarded else collect())
    html = render(data)
    if len(html.encode()) > 256 * 1024:
        raise ValueError('preview_output_limit')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', mode='w', encoding='utf-8', newline='\n', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return target.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-fixture', action='store_true')
    args = parser.parse_args(argv)
    if not args.build_fixture:
        print('DISABLED: use --build-fixture for OFFLINE TEST FIXTURE. No preview created; no server.')
        return 0
    try:
        path = build(guarded=True)
    except Exception:
        print('BUILD FAILED: offline fixture/worker/output validation. No successful preview.', file=sys.stderr)
        return 1
    print('PREVIEW_HTML=' + str(path))
    print('Open this file directly in a browser. OFFLINE TEST FIXTURE; no server.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
