"""Offline B2B reproduction from an operator-supplied genuine capture.

Usage: python tests/ru12_capture_diagnostic.py path/to/captured.html
Never fetches, inserts, changes source configuration, or claims live proof.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.sources.b2b_center import MAX_BYTES, parse_b2b_center_listing
from app.sources.opportunities import validate_notice
from ru12_six_sources_live_smoke import exception_frames


def diagnose(path):
    report = dict(proof_origin='offline_capture', fixture_used=True, live_verified=False,
                  stage='read', state='BLOCKED')
    try:
        with Path(path).open('rb') as capture:
            payload = capture.read(MAX_BYTES + 1)
        report['sha256'] = hashlib.sha256(payload).hexdigest()
        report['stage'] = 'parse'
        notices = parse_b2b_center_listing(payload)
        report['stage'] = 'validation'
        for notice in notices:
            validate_notice(notice, 'b2b_center')
        report.update(state='OFFLINE_PARSE_VALIDATED', records=len(notices))
    except Exception as error:
        report['exceptions'] = exception_frames(error)
    return report


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Supply one captured B2B HTML file path')
    print(json.dumps(diagnose(sys.argv[1]), indent=2))
