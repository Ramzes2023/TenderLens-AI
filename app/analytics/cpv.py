"""Offline CPV 2008 labels and verified explicit edges. No inferred check digits."""
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType


_DATA = json.loads(Path(__file__).with_name('cpv_2008.json').read_text(encoding='utf-8'))
CPV_METADATA = MappingProxyType({k: v for k, v in _DATA.items() if k != 'labels'})
CPV_LABELS = MappingProxyType(_DATA['labels'])
CPV_VERSION = '2008'
CPV_SCHEME = 'cpv-2008'


def validate_cpv(code):
    """Require exact reference notation; never silently strip a check digit."""
    if not isinstance(code, str):
        return 'invalid'
    if re.fullmatch(r'[0-9]{8}-[0-9]', code):
        return 'unsupported_check_digit'
    if not re.fullmatch(r'[0-9]{8}', code):
        return 'invalid'
    return 'verified' if code in CPV_LABELS else 'unknown'


_HIERARCHY = json.loads(Path(__file__).with_name('cpv_2008_parents.json').read_text(encoding='utf-8'))
CPV_HIERARCHY_METADATA = MappingProxyType({k:v for k,v in _HIERARCHY.items() if k != 'parents'})
CPV_PARENTS = MappingProxyType(_HIERARCHY['parents'])


def cpv_parent(code):
    """An absent explicit edge is unknown, never an inferred root."""
    status = validate_cpv(code)
    parent = CPV_PARENTS.get(code) if status == 'verified' else None
    return {'code': code, 'parent': parent,
            'status': ('verified' if parent else 'unknown_parent') if status == 'verified' else status}


def cpv_ancestors(code):
    status = validate_cpv(code)
    ancestors = []
    current = code
    if status == 'verified':
        while current in CPV_PARENTS:
            current = CPV_PARENTS[current]
            ancestors.append(current)
        status = 'unknown_parent'
    return {'code': code, 'ancestors': ancestors, 'status': status}


def cpv_descendants(code):
    status = validate_cpv(code)
    result = []
    if status == 'verified':
        result = sorted(child for child in CPV_PARENTS if code in cpv_ancestors(child)['ancestors'])
    return {'code': code, 'descendants': result,
            'status': 'verified_edges_only' if status == 'verified' else status}


def cpv_category_match(classification, category, *, include_descendants=True):
    """Tri-state match over verified memberships; legacy snapshots stay exact-only.

    None means unsupported/unknown, False requires a proven different branch.
    """
    if validate_cpv(category) != 'verified':
        return None
    codes = [code for scheme, code in classification.get('memberships', [])
             if scheme == CPV_SCHEME and validate_cpv(code) == 'verified']
    if category in codes:
        return True
    if not include_descendants:
        return False if codes else None
    if classification.get('version') != 'source-classifications-cpv2008-v2':
        return None
    if any(category in cpv_ancestors(code)['ancestors'] for code in codes):
        return True
    # A shared verified ancestor proves separate branches without asserting roots.
    category_lineage = {category, *cpv_ancestors(category)['ancestors']}
    if codes and all(category_lineage.intersection({code, *cpv_ancestors(code)['ancestors']})
                     for code in codes):
        return False
    # Unknown terminals cannot prove non-membership; no fabricated roots.
    return None


def verify_reference(raw):
    return hashlib.sha256(raw).hexdigest() == CPV_METADATA['reference_sha256']
