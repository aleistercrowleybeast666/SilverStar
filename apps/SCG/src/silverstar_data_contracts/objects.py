from copy import deepcopy
from importlib.resources import files
import json


def ObjectCatalog_DefaultGet():
    value = json.loads(files(__package__).joinpath('data/persistent_objects_v1.json').read_text(encoding='utf8'))
    ObjectCatalog_Validate(value)
    return value


def ObjectCatalog_Validate(document):
    if (type(document) is not dict or set(document) != {'schema_id', 'endianness', 'objects', 'rules'}
            or document['schema_id'] != 'silverstar.object-catalog/1.0' or document['endianness'] != 'little'):
        raise ValueError('object_catalog_schema')
    objects = document['objects']
    if type(objects) is not list or not 1 <= len(objects) <= 64:
        raise ValueError('object_catalog_capacity')
    seen = set()
    sizes = {'u8': 1, 'u16': 2, 'u32': 4, 'f32': 4, 'bytes': 1}
    tails = {'none', 'ssob_payload', 'ssic_kind_payload', 'canonical_snapshot_json', 'section_rows_or_flight_configuration'}
    for item in objects:
        if type(item) is not dict or set(item) != {'type_id', 'schema_version', 'min_bytes', 'max_bytes', 'fields', 'tail_encoding'}:
            raise ValueError('object_catalog_entry')
        identity = item['type_id']
        if type(identity) is not str or not 1 <= len(identity) <= 96 or identity in seen:
            raise ValueError('object_catalog_identity')
        seen.add(identity)
        if (type(item['schema_version']) is not int or item['schema_version'] != 1
                or type(item['min_bytes']) is not int or type(item['max_bytes']) is not int
                or not 0 < item['min_bytes'] <= item['max_bytes'] <= 1048576
                or type(item['tail_encoding']) is not str or item['tail_encoding'] not in tails):
            raise ValueError('object_catalog_bounds')
        fields = item['fields']
        if type(fields) is not list or not 1 <= len(fields) <= 64:
            raise ValueError('object_catalog_fields')
        names, end = set(), 0
        for field in fields:
            if type(field) is not dict or set(field) != {'name', 'type', 'count', 'offset', 'unit'}:
                raise ValueError('object_catalog_field')
            if (type(field['name']) is not str or not 1 <= len(field['name']) <= 96 or field['name'] in names
                    or type(field['type']) is not str or field['type'] not in sizes or type(field['count']) is not int or not 1 <= field['count'] <= 4096
                    or type(field['offset']) is not int or field['offset'] != end
                    or type(field['unit']) is not str or not 1 <= len(field['unit']) <= 64):
                raise ValueError('object_catalog_field_layout')
            names.add(field['name'])
            end += sizes[field['type']] * field['count']
        if end != item['min_bytes'] or item['tail_encoding'] == 'none' and end != item['max_bytes']:
            raise ValueError('object_catalog_layout_length')
    if (type(document['rules']) is not dict or len(document['rules']) > 32 or
            any(type(key) is not str or type(value) is not str or len(value) > 2048 for key, value in document['rules'].items())):
        raise ValueError('object_catalog_rules')
    return deepcopy(document)
