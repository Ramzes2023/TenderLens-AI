"""Inspect pinned offline search-field documentation, never claim JSON shape."""
import hashlib
import json
from pathlib import Path
import sys
from scripts.verify_cpv_reference import ReferenceRows

SHA256 = '79324dc627ee846f137e8cf4d069509784d51dcc7770f592dcd58096e261a419'

class Fields(ReferenceRows):
    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag,attrs)
        if tag == 'br' and self.parts is not None:
            self.parts.append(' ')

def inspect(raw):
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('TED field-list checksum mismatch')
    parser = Fields()
    parser.feed(raw.decode('utf-8'))
    expected = {'classification-cpv': 'BT-262-Procedure BT-263-Procedure BT-262-Part BT-263-Part BT-262-Lot BT-263-Lot'}
    for prefix, bt in [('main','BT-262'),('additional','BT-263')]:
        for suffix, context in [('proc','Procedure'),('part','Part'),('lot','Lot')]:
            expected[f'{prefix}-classification-{suffix}'] = f'{bt}-{context}'
    rows = [row for row in parser.rows if row and row[0] in expected]
    if len(rows) != 7 or any(len(row)!=4 or row[3]!=expected[row[0]] for row in rows):
        raise ValueError('TED classification field contexts mismatch')
    return {'reference_url':'https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html',
            'reference_sha256':SHA256, 'documentation_component':'ODS 1 / displayed 1.0',
            'columns':['Search field','Alias 1','Alias 2','Reference in the eForms SDK'],
            'rows':rows, 'response_json_types':'not documented in supplied field-list',
            'response_context_binding':'not documented in supplied field-list',
            'extraction_status':'pending'}

if __name__ == '__main__':
    result = inspect(Path(sys.argv[1]).read_bytes())
    if len(sys.argv)>2:
        Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
