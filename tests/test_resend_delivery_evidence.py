import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('evidence', Path(__file__).resolve().parents[1]/'scripts/ops/resend_delivery_evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


def test_content_rejection_preserves_codes_without_private_data():
    report = evidence.summarize({
        'last_event': 'bounced', 'to': ['private@example.invalid'],
        'text': 'https://private.invalid/reset?token=SECRET', 'message_id': 'PRIVATE_ID',
        'bounce': {'type': 'Transient', 'subType': 'ContentRejected',
                   'message': 'private@example.invalid',
                   'diagnosticCode': ['smtp; 550-5.7.1 [192.0.2.10 12] Gmail has detected that this message is likely550-5.7.1 unsolicited mail. 550 5.7.1 PRIVATE_ID - gsmtp']},
    })
    assert report['smtp_codes'] == ['550']
    assert report['enhanced_codes'] == ['5.7.1']
    assert report['bounce_subtype'] == 'ContentRejected'
    assert report['likely_unsolicited'] and not report['provider_delivered']
    assert report['recipient_receipt'] == 'unverified'
    text = json.dumps(report)
    for value in ('private', 'SECRET', 'PRIVATE_ID', '192.0.2.10'):
        assert value not in text


@pytest.mark.parametrize('status,delivered', [('sent', False), ('delivered', True), ('bounced', False), ('opened', True)])
def test_provider_acceptance_never_proves_inbox_receipt(status, delivered):
    report = evidence.summarize({'last_event': status})
    assert report['provider_delivered'] is delivered
    assert report['recipient_receipt'] == 'unverified'


def test_untrusted_categories_cannot_escape_allowlist():
    report = evidence.summarize({'last_event': 'SECRET', 'bounce': {'type': 'SECRET', 'subType': 'SECRET', 'diagnosticCode': 'smtp; 550 5.7.1 SECRET'}})
    assert 'SECRET' not in json.dumps(report)
    assert report['smtp_codes'] == ['550']
