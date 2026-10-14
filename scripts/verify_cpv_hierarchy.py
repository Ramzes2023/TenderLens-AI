"""Verify inert, pinned Genericode; never derive edges from code prefixes."""
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analytics.cpv import CPV_LABELS

SHA256 = 'e8f48feedb63ce1583caa22825011afccd402973c28a885c2e81f89460fd6301'
URL = 'https://raw.githubusercontent.com/OP-TED/eForms-SDK/1.15.1/codelists/cpv.gc'

def extract(raw):
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('Genericode checksum mismatch')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML declarations forbidden')
    root = ET.fromstring(raw)
    if root.tag != '{http://docs.oasis-open.org/codelist/ns/genericode/1.0/}CodeList':
        raise ValueError('Unexpected Genericode format')
    identity = root.find('Identification')
    expected = {'ShortName': 'cpv_2008_core', 'Version': '2008',
                'CanonicalUri': 'http://publications.europa.eu/resource/dataset/cpv',
                'Agency/LongName': 'Publications Office of the European Union'}
    if any(identity.findtext(key) != value for key, value in expected.items()):
        raise ValueError('Metadata mismatch')
    rows = {}
    for row in root.findall('./SimpleCodeList/Row'):
        values = row.findall('Value')
        data = {v.attrib['ColumnRef']: v.findtext('SimpleValue') for v in values}
        if len(data) != len(values) or data['code'] in rows:
            raise ValueError('Duplicate column/code')
        rows[data['code']] = data
    if set(rows) != set(CPV_LABELS):
        raise ValueError('Code coverage mismatch')
    mismatches = {code: {'genericode': d['Name'], 'registry': CPV_LABELS[code]}
                  for code, d in rows.items() if d['Name'] != CPV_LABELS[code]}
    all_edges = {code: d['parentCode'] for code, d in rows.items() if d.get('parentCode')}
    if any(parent not in rows for parent in all_edges.values()):
        raise ValueError('Orphan parent')
    for code in rows:
        seen = set()
        while code in all_edges:
            if code in seen:
                raise ValueError('Hierarchy cycle')
            seen.add(code)
            code = all_edges[code]
    edges = {c:p for c,p in all_edges.items() if c not in mismatches and p not in mismatches}
    return {'version': 'cpv-2008-explicit-parents-sdk1.15.1-v1', 'cpv_version': '2008',
            'sdk_version': '1.15.1', 'reference_url': URL, 'reference_sha256': SHA256,
            'label_reference_sha256': 'e4134a747acbc18d99a778412002caf55212baf8cbc1c695a03fab00edecbbb9',
            'rows': len(rows), 'explicit_edges': len(all_edges), 'verified_edges': len(edges),
            'missing_parent': sorted(set(rows)-set(all_edges)),
            'withheld_edges': {c:p for c,p in all_edges.items() if c not in edges},
            'label_mismatches': mismatches, 'orphans': 0, 'cycles': 0, 'parents': edges}

if __name__ == '__main__':
    data = extract(Path(sys.argv[1]).read_bytes())
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k not in ('parents','label_mismatches','withheld_edges','missing_parent')}))
