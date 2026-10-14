"""Independent source categories and explicitly versioned TED CPV labels.

Only the existing AusTender and ZA offline fixtures establish these labels.
No hierarchy or industry crosswalk is asserted without a verified reference.
Unversioned CPV and other systems remain unsupported. Never infer industry,
parent edges or check digits. Multiple memberships are deduplicated.
"""

from app.analytics.cpv import CPV_LABELS, CPV_SCHEME, validate_cpv

TAXONOMY_VERSION = 'source-classifications-cpv2008-v2'
LEGACY_TAXONOMY_VERSION = 'observed-source-categories-v1'
REGISTRY = {
    ('austender-category', '80100000'): 'Management advisory services',
    ('za-etenders-category', 'Services: General'): 'Services: General',
}


def normalize_classifications(entries, *, version=TAXONOMY_VERSION):
    if version not in (TAXONOMY_VERSION, LEGACY_TAXONOMY_VERSION):
        raise ValueError('Unsupported classification policy version.')
    results = []
    for entry in entries:
        key = (entry['scheme'], entry['code'])
        label = REGISTRY.get(key) if all(isinstance(value, str) for value in key) else None
        status = 'verified' if label and entry.get('label') in (None, label) else (
            'conflicting' if label else 'unsupported')
        if entry['scheme'] == CPV_SCHEME and version == TAXONOMY_VERSION:
            status = validate_cpv(entry['code'])
            label = CPV_LABELS.get(entry['code']) if isinstance(entry['code'], str) else None
            if status == 'verified' and entry.get('label') not in (None, label):
                status = 'conflicting'
        results.append({**entry, 'status': status, 'canonical_label': label if status == 'verified' else None})
    memberships = sorted({(e['scheme'], e['code']) for e in results if e['status'] == 'verified'})
    return {'version': version, 'entries': results,
            'memberships': [list(key) for key in memberships],
            'status': 'missing' if not entries else 'verified' if all(e['status'] == 'verified' for e in results) else 'partial' if memberships else 'unsupported',
            'industry_status': 'unmapped', 'industries': [], 'hierarchies': []}
