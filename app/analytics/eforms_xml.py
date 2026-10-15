"""Offline, bounded eForms context extraction; no fetching or notice membership.

This is a path whitelist, not full XSD validation. Only the evidenced
ContractNotice root is supported. Group IDs are retained without inventing CPV.
"""
import hashlib
import io
import re
import xml.etree.ElementTree as ET

from .cpv import CPV_METADATA, validate_cpv

VERSION = 'eforms-xml-context-v1'
MAX_BYTES = 2 * 1024 * 1024
SCHEMA_SHA256 = '79241647c6acae10fcf61b3112cef35228339c632c664bfc4f8101f82c0556bd'
EXAMPLE_SHA256 = '3bba90994d3e7d86ed8bb07f5c2fc49b8be27523b9ac5397c83ee86312b43ef8'
NS = {
    'cn': 'urn:oasis:names:specification:ubl:schema:xsd:ContractNotice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'efac': 'http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1',
    'efbc': 'http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1',
    'efext': 'http://data.europa.eu/p27/eforms-ubl-extensions/1',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'xml': 'http://www.w3.org/XML/1998/namespace',
}


def q(name):
    prefix, local = name.split(':')
    return '{' + NS[prefix] + '}' + local


def extract_eforms_classifications(raw, *, evidence_kind, source_reference):
    """Accept bytes already obtained by an authorized caller; return sidecar only.

    Provenance labels are caller assertions, never proof of a published notice.
    Fail closed on unsupported classifications; return no partial extraction.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError('XML byte size/type rejected')
    if evidence_kind not in ('sdk_example', 'synthetic_test', 'published_notice'):
        raise ValueError('Unknown evidence kind')
    if not isinstance(source_reference, str) or not 0 < len(source_reference) <= 2000:
        raise ValueError('Source reference required')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError:
        raise ValueError('Only UTF-8 XML supported') from None
    if '\x00' in text or re.search(r'<!\s*(DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('DTD/entities forbidden')
    encoding = re.search(r'<\?xml\s[^?]*encoding\s*=\s*[\'"]([^\'"]+)', text)
    if encoding and encoding[1].lower() not in ('utf-8', 'utf8'):
        raise ValueError('Only UTF-8 XML supported')
    depth = count = 0
    try:
        parser = ET.iterparse(io.StringIO(text), events=('start', 'end', 'start-ns'))
        for event, node in parser:
            if event == 'start-ns':
                if node[1] not in NS.values():
                    raise ValueError('Unknown namespace')
            elif event == 'start':
                depth += 1
                count += 1
                if depth > 64 or count > 20000:
                    raise ValueError('XML structure limit exceeded')
                for name in (node.tag, *node.attrib):
                    if name.startswith('{'):
                        if name[1:].split('}')[0] not in NS.values():
                            raise ValueError('Unknown namespace')
                    elif name == node.tag:
                        raise ValueError('Unqualified XML element')
            else:
                depth -= 1
        root = parser.root
    except ET.ParseError:
        raise ValueError('Malformed XML') from None
    if root.tag != q('cn:ContractNotice'):
        raise ValueError('Unsupported notice root')

    # Namespace-expanded indexed paths locate original nodes independently of prefixes.
    paths = {root: '/' + root.tag + '[1]'}
    for parent in root.iter():
        indices = {}
        for child in parent:
            indices[child.tag] = indices.get(child.tag, 0) + 1
            paths[child] = paths[parent] + '/' + child.tag + f'[{indices[child.tag]}]'

    def one(parent, name, required=False):
        nodes = parent.findall(q(name))
        if len(nodes) > 1 or (required and not nodes):
            raise ValueError('Ambiguous/missing ' + name)
        if not nodes:
            return None
        node = nodes[0]
        if len(node) or not node.text or not node.text.strip():
            raise ValueError('Invalid ' + name)
        return {'value': node.text, 'attributes': dict(node.attrib), 'path': paths[node]}

    procedure_id = one(root, 'cbc:ContractFolderID', True)
    contexts = [{'scope': 'procedure', 'id': procedure_id, 'element': root}]
    seen = set()
    for lot in root.findall(q('cac:ProcurementProjectLot')):
        identity = one(lot, 'cbc:ID', True)
        scheme = identity['attributes'].get('schemeName')
        scope = {'Lot': 'lot', 'LotsGroup': 'group_of_lots', 'Part': 'part'}.get(scheme)
        prefix = {'Lot': 'LOT', 'LotsGroup': 'GLO', 'Part': 'PAR'}.get(scheme)
        if scope is None or not re.fullmatch(str(prefix) + r'-[0-9]{4}', identity['value']):
            raise ValueError('Unknown context identity')
        if identity['value'] in seen:
            raise ValueError('Duplicate context ID')
        seen.add(identity['value'])
        contexts.append({'scope': scope, 'id': identity, 'element': lot})
    if any(c['scope'] == 'part' for c in contexts) and any(
        c['scope'] in ('lot', 'group_of_lots') for c in contexts
    ):
        raise ValueError('Parts cannot coexist with lots/groups')
    accepted = set()
    accepted_containers = set()
    entries = []
    result_contexts = []
    for context in contexts:
        element = context['element']
        result_contexts.append({
            'scope': context['scope'], 'id': context['id'], 'path': paths[element],
            'internal_id': None,
        })
        projects = element.findall(q('cac:ProcurementProject'))
        if len(projects) > 1:
            raise ValueError('Ambiguous procurement project')
        for project in projects:
            result_contexts[-1]['internal_id'] = one(project, 'cbc:ID')
            for name, role in (('MainCommodityClassification', 'main'),
                               ('AdditionalCommodityClassification', 'additional')):
                classifications = project.findall(q('cac:' + name))
                if role == 'main' and len(classifications) > 1:
                    raise ValueError('Ambiguous main classification')
                for classification in classifications:
                    nodes = classification.findall(q('cbc:ItemClassificationCode'))
                    if len(nodes) != 1 or context['scope'] == 'group_of_lots':
                        raise ValueError('Unsupported classification context/cardinality')
                    node = nodes[0]
                    if len(node) or node.get('listName') != 'cpv':
                        raise ValueError('Unknown classification scheme/shape')
                    if node.get('listVersionID') not in (None, '2008'):
                        raise ValueError('Unsupported CPV version')
                    code = node.text
                    status = validate_cpv(code)
                    if status != 'verified':
                        raise ValueError('CPV rejected: ' + status)
                    accepted.add(node)
                    accepted_containers.add(classification)
                    entries.append({'scope': context['scope'], 'context_id': context['id'],
                                    'procedure_id': procedure_id, 'role': role, 'code': code,
                                    'scheme': 'cpv-2008', 'cpv_version': '2008',
                                    'path': paths[node], 'attributes': dict(node.attrib),
                                    'validation': status})
    for node in root.iter():
        local = node.tag.split('}')[-1]
        if (local == 'ItemClassificationCode' and node not in accepted) or (
            'CommodityClassification' in local and node not in accepted_containers
        ):
            raise ValueError('Unknown classification path')
    digest = hashlib.sha256(raw).hexdigest()
    if digest == EXAMPLE_SHA256 and evidence_kind != 'sdk_example':
        raise ValueError('Official SDK example is not a published notice')
    return {'version': VERSION, 'provenance': {
        'source_reference': source_reference, 'evidence_kind': evidence_kind,
        'xml_sha256': digest, 'schema_sha256': SCHEMA_SHA256,
        'cpv_reference_sha256': CPV_METADATA['reference_sha256'],
        'origin_independently_verified': False,
    }, 'versions': {name: one(root, 'cbc:' + name) for name in
                    ('UBLVersionID', 'CustomizationID', 'VersionID')},
        'notice_id': one(root, 'cbc:ID'), 'contexts': result_contexts, 'entries': entries}
