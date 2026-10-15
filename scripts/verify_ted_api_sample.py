"""Audit pinned public TED data offline; never execute YAML or fetch notice links."""
import hashlib
import json
from pathlib import Path
import re
import sys


OPENAPI_SHA256 = 'e0cfe4e84123c3b62118ca99e07e8b9a09467494846280b8c7e60d700fbd2ff8'
RESPONSE_SHA256 = '8246a105bea0e0603a2669bbc99a2098df704870449060c827bf7973c6585b81'
CONTEXT_FIELDS = tuple(f'{role}-classification-{scope}'
                       for role in ('main', 'additional') for scope in ('proc', 'part', 'lot'))


def inspect(openapi, request, response):
    """Return a minimal exact-value subset and separate sample proof from schema."""
    for raw, digest in ((openapi, OPENAPI_SHA256), (response, RESPONSE_SHA256)):
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('TED evidence checksum mismatch')
    # Only inspect the pinned NoticeResponse section as text, without YAML tags/loaders.
    schema = openapi.decode('utf-8').split('    NoticeResponse:\n', 1)[1]
    schema = re.split(r'\n    [A-Za-z][^\n]*:\n', schema, maxsplit=1)[0]
    fields = ('classification-cpv', *CONTEXT_FIELDS)
    for field in fields:
        block = f'        {field}:\n          type: array\n          items:\n            type: string\n'
        if block not in schema:
            raise ValueError('TED schema field type mismatch')
    query = json.loads(request)
    payload = json.loads(response)
    if query['fields'] != ['publication-number', 'classification-cpv',
                           'main-classification-proc', 'additional-classification-proc',
                           'main-classification-lot', 'additional-classification-lot',
                           'main-classification-part', 'additional-classification-part']:
        raise ValueError('Unexpected capture fields')
    notices = []
    for raw in payload['notices']:
        if set(raw) != {'publication-number', 'classification-cpv', 'links'}:
            raise ValueError('Unexpected sampled notice fields')
        codes = raw['classification-cpv']
        if not isinstance(codes, list) or not codes or any(type(code) is not str for code in codes):
            raise ValueError('Unexpected sampled CPV type')
        notices.append({key: raw[key] for key in ('publication-number', 'classification-cpv')})
    return {
        'endpoint_url': 'https://api.ted.europa.eu/v3/notices/search',
        'openapi_sha256': OPENAPI_SHA256,
        'response_sha256': RESPONSE_SHA256,
        'request_sha256': hashlib.sha256(request).hexdigest(),
        'request': query,
        'response': {**{key: value for key, value in payload.items() if key != 'notices'},
                     'notices': notices},
        'removed_fields': ['notices[].links'],
        'schema_only_array_of_string_fields': list(CONTEXT_FIELDS),
        'demonstrated_array_of_string_fields': ['classification-cpv'],
        'context_binding': 'unproven; aggregate across Procedure/Part/Lot',
        'extraction_status': 'blocked_entity_scope',
    }


if __name__ == '__main__':
    directory = Path(sys.argv[1])
    result = inspect(*(directory.joinpath(name).read_bytes() for name in
                       ('ted-api-v3.yaml', 'request.json', 'public-search-response.json')))
    print(json.dumps(result, indent=2))
