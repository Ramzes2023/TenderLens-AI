"""Produce allowlisted, recipient-free evidence from a Resend GET-email response.

The official MCP summary can omit bounce details. Inspect an existing GET-email
request log's response_body using read-only get-log; never replay or resend it.
This module performs no network operations and emits neither bodies nor headers.
"""
import re


def summarize(email):
    bounce = email.get('bounce') or {}
    diagnostics = bounce.get('diagnosticCode') or []
    if isinstance(diagnostics, str):
        diagnostics = [diagnostics]
    diagnostics = ' '.join(str(value) for value in diagnostics)
    # Only known protocol codes and fixed categories can enter published evidence.
    smtp_codes = sorted(set(re.findall(r'\b[245]\d{2}(?=[\s-])', diagnostics)))
    enhanced = sorted(set(re.findall(r'\b[245]\.\d{1,3}\.\d{1,3}\b', diagnostics)))
    status = email.get('last_event')
    if status not in {'sent', 'delivered', 'bounced', 'delivery_delayed', 'failed', 'suppressed', 'complained', 'opened', 'clicked', 'scheduled'}:
        status = 'unknown'
    kind = bounce.get('type')
    subtype = bounce.get('subType')
    result = {
        'event': status,
        'bounce_type': kind if kind in {'Transient', 'Permanent', 'Undetermined'} else 'unknown',
        'bounce_subtype': subtype if subtype in {'ContentRejected', 'General', 'NoEmail', 'Suppressed', 'MailboxFull', 'MessageTooLarge', 'AttachmentRejected', 'OnAccountSuppressionList'} else 'unknown',
        'smtp_codes': smtp_codes, 'enhanced_codes': enhanced,
        'likely_unsolicited': 'likely' in diagnostics.lower() and 'unsolicited mail' in diagnostics.lower(),
        'provider_delivered': status in {'delivered', 'opened', 'clicked'},
        # Neither a provider event nor message content proves recipient confirmation.
        'recipient_receipt': 'unverified',
    }
    return result
