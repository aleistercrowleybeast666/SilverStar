"""Validate Java exports against the exact common schema and common synthetic golden."""
from pathlib import Path, PurePosixPath
import copy
import hashlib
import json
import os
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get('SILVERSTAR_ANDROID_BUILD_ROOT', str(ROOT/'build')))
deps = os.environ.get('SILVERSTAR_ANDROID_PYTHON_DEPS')
if deps: sys.path.insert(0, str(Path(deps).resolve()))
from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS = ROOT / 'reference/shared-0.1.3/contracts'
schema = json.loads((CONTRACTS / 'session_export_v1.schema.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())
checks = 0


def check(value, label):
    global checks
    checks += 1
    if not value:
        raise AssertionError(label)


def manifest_validate(manifest):
    validator.validate(manifest)
    paths = [entry['path'].casefold() for entry in manifest['files']]
    if len(paths) != len(set(paths)):
        raise ValueError('case-folded duplicate paths')


golden = json.loads((CONTRACTS / 'session_export_v1.golden.json').read_text(encoding='utf-8'))
manifest_validate(golden)
wire_golden = json.loads((CONTRACTS / 'log_file_service_v1.json').read_text(encoding='utf-8'))['golden']
content = bytes.fromhex(wire_golden['file_bytes_hex'])
check(len(content) == golden['files'][0]['size_bytes'], 'shared golden original byte length')
check(hashlib.sha256(content).hexdigest() == golden['files'][0]['sha256'], 'shared golden SHA-256')

for label, expected_version in [('new', '1'), ('legacy', 'legacy-unversioned')]:
    path = BUILD / f'storage-tests/{label}-session-export.zip'
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        manifest_validate(manifest)
        expected = {'manifest.json'} | {f['path'] for f in manifest['files']}
        check(set(archive.namelist()) == expected, f'{label}: exact declared file set')
        check(len(archive.namelist()) == len(expected), f'{label}: no duplicates')
        for entry in manifest['files']:
            payload = archive.read(entry['path'])
            check(len(payload) == entry['size_bytes'], f'{label}: size')
            check(hashlib.sha256(payload).hexdigest() == entry['sha256'], f'{label}: SHA-256')
            if entry['role'] == 'session_log':
                check(entry['format'] == 'silverstar.gshc-jsonl', 'format')
                check(entry['format_version'] == expected_version, 'format version')
                first = json.loads(payload.splitlines()[0])
                if label == 'new':
                    check(first['log_format'] == 'silverstar.gshc-jsonl' and first['log_format_version'] == 1, 'SESSION_START identity')
                else:
                    check('log_format_version' not in first and b'\r\n' in payload, 'legacy not rewritten')
        check(manifest['source_app']['version'] == '0.1.3-dev.1', 'independent App identity')
        check(manifest['protocols']['source_contract_tag'] == ('v0.1.2' if label == 'new' else None), 'frozen own provenance; imported unknown not fabricated')

for label in ['tf', 'mock']:
    with zipfile.ZipFile(BUILD / f'storage-tests/{label}-session-export.zip') as archive:
        manifest = json.loads(archive.read('manifest.json'))
        manifest_validate(manifest)
        check(set(archive.namelist()) == {'manifest.json'} | {f['path'] for f in manifest['files']}, 'TF declared files')
        for entry in manifest['files']:
            payload = archive.read(entry['path'])
            check(len(payload) == entry['size_bytes'], 'TF member byte length')
            check(hashlib.sha256(payload).hexdigest() == entry['sha256'], 'TF member SHA-256')
            if entry['format'] in ['SSLOG', 'synthetic-fixture']:
                check(payload == content, 'shared TF golden bytes preserved without conversion')
                check(entry['role'] == ('flight_log' if label == 'tf' else 'attachment'), 'mock is not a flight log')
                check(entry['format_version'] == ('0.0' if label == 'tf' else '1'), 'SSLOG identity unchanged')
        check(manifest['protocols']['air'] is None, 'unknown downloaded AIR provenance stays unknown')
        check(manifest['protocols']['log_file_service'] == 1, 'shared LOGFILE v1 identity')

bad_cases = []
bad = copy.deepcopy(golden); bad['producer'] = {}; bad_cases.append(bad)
bad = copy.deepcopy(golden); bad['files'][0]['role'] = 'raw_session'; bad_cases.append(bad)
for unsafe in ['../flight.sslog', '/flight.sslog', 'C:/flight.sslog', 'logs/../flight.sslog', 'logs\\flight.sslog']:
    bad = copy.deepcopy(golden); bad['files'][0]['path'] = unsafe; bad_cases.append(bad)
bad = copy.deepcopy(golden); bad['files'].append(dict(bad['files'][0], path='LOGS/FLIGHT.SSLOG')); bad_cases.append(bad)
for bad in bad_cases:
    rejected = False
    try:
        manifest_validate(bad)
    except Exception:
        rejected = True
    check(rejected, 'invalid export rejected')

print(f'PASS: {checks} shared-schema/golden assertions (jsonschema Draft 2020-12); Java ZIPs, raw bytes, version identities, paths, duplicates.')
