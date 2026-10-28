import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('preflight', Path(__file__).resolve().parents[1] / 'scripts/ops/resend_production_preflight.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def configs():
    original = {'services': {'api': {'image': 'exact-image', 'volumes': ['data:/app/data'],
                'environment': {'VALYQON_EMAIL_MODE': 'disabled', 'VALYQON_LEGAL_REQUIRED': 'true'}},
                'caddy': {'image': 'proxy'}}}
    candidate = copy.deepcopy(original)
    candidate['services']['api']['environment'].update(
        VALYQON_EMAIL_MODE='smtp', VALYQON_SMTP_HOST='smtp.resend.com',
        VALYQON_SMTP_PORT='465', VALYQON_SMTP_USERNAME='resend',
        VALYQON_SMTP_PASSWORD='re_PRIVATE_SENTINEL',
        VALYQON_SMTP_FROM='noreply@valyqon.dns.army',
        VALYQON_SMTP_SSL='true', VALYQON_SMTP_STARTTLS='false',
        VALYQON_PUBLIC_BASE_URL='https://valyqon.duckdns.org')
    return original, candidate


def test_mail_only_candidate_accepted_without_mutating_inputs():
    original, candidate = configs()
    saved = copy.deepcopy((original, candidate))
    module.validate_diff(original, candidate)
    assert (original, candidate) == saved


@pytest.mark.parametrize('change', ['image', 'volume', 'proxy', 'legal', 'provider', 'extra_env', 'credential'])
def test_unsafe_candidate_rejected(change):
    a, b = configs()
    api = b['services']['api']
    if change == 'image': api['image'] = 'different'
    if change == 'volume': api['volumes'] = ['other:/app/data']
    if change == 'proxy': b['services']['caddy']['image'] = 'different'
    if change == 'legal': api['environment']['VALYQON_LEGAL_REQUIRED'] = 'false'
    if change == 'provider': api['environment']['VALYQON_SMTP_HOST'] = 'smtp.gmail.com'
    if change == 'extra_env': api['environment']['UNREVIEWED'] = 'true'
    if change == 'credential': api['environment']['VALYQON_SMTP_PASSWORD'] = ''
    with pytest.raises(AssertionError): module.validate_diff(a, b)



def test_current_sender_and_duckdns_link_hosts_require_review():
    _, candidate = configs()
    env = candidate['services']['api']['environment']
    assert module.sender_link_host_status(env) == 'DIFFERENT_HOST'


def test_future_same_host_alignment_without_sending_any_email():
    _, candidate = configs()
    env = candidate['services']['api']['environment']
    env['VALYQON_SMTP_FROM'] = 'VALYQON AI <team@auth.valyqon.example>'
    env['VALYQON_PUBLIC_BASE_URL'] = 'https://AUTH.valyqon.example'
    assert module.sender_link_host_status(env) == 'EXACT_MATCH'


@pytest.mark.parametrize('mail_from,public_base', [
    ('bad-address', 'https://auth.valyqon.example'),
    ('team@auth.valyqon.example', 'http://auth.valyqon.example'),
    ('team@auth.valyqon.example', 'https://[unclosed'),
    ('team@auth.valyqon.example', ''),
])
def test_link_host_audit_uncertain_config_never_claims_match(mail_from, public_base):
    assert module.sender_link_host_status({
        'VALYQON_SMTP_FROM': mail_from,
        'VALYQON_PUBLIC_BASE_URL': public_base,
    }) == 'UNKNOWN'


def test_different_subdomains_are_not_claimed_identical():
    assert module.sender_link_host_status({
        'VALYQON_SMTP_FROM': 'team@auth.valyqon.example',
        'VALYQON_PUBLIC_BASE_URL': 'https://app.valyqon.example',
    }) == 'DIFFERENT_HOST'
