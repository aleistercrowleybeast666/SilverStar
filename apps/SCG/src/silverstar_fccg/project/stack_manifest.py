"""Read sealed stack review data without executing project code.

Owner: core plugin Tools. The SCG project-module mirror is byte-identical and
tested. Version 2 splits immutable cases; it does not enroll or weaken a case.
"""
import hashlib
import json
from pathlib import Path
import re


def _Object_Parse(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate software stack proof JSON key: ' + key)
        value[key] = item
    return value


def _File_Read(root, relative, maximum):
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Unsafe software stack proof path')
    path = root / relative
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not path.is_file():
        raise ValueError('Unsafe or missing software stack proof file')
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink() or (hasattr(current, 'is_junction') and current.is_junction()):
            raise ValueError('Linked software stack proof input')
    if path.stat().st_size > maximum:
        raise ValueError('Oversized software stack proof input')
    with path.open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Oversized software stack proof input')
    return raw


def Manifest_Load(root, manifest_path, manifest_sha256):
    """Verify the complete index and every case, including unselected cases."""
    root_path = Path(root).absolute()
    relative = Path(manifest_path).absolute().relative_to(root_path)
    root_path = root_path.resolve(strict=True)
    # Legacy sealed reports remain readable; all new index/case files obey
    # the repository's 2 MiB bound. No source or artifact hash is omitted.
    raw = _File_Read(root_path, relative, 32 * 1024 * 1024)
    if (not isinstance(manifest_sha256, str) or
            re.fullmatch(r'[0-9a-f]{64}', manifest_sha256) is None or
            hashlib.sha256(raw).hexdigest() != manifest_sha256):
        raise ValueError('Unreviewed software stack manifest')
    manifest = json.loads(raw, object_pairs_hook=_Object_Parse)
    if not isinstance(manifest, dict) or manifest.get('schema') not in (
            'silverstar.software-stack-inputs/1', 'silverstar.software-stack-inputs/2'):
        raise ValueError('Unsupported software stack proof schema')
    if not isinstance(manifest.get('review_revision'), str) or not manifest['review_revision']:
        raise ValueError('Missing software stack review revision')
    rows = manifest.get('cases')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Missing software stack proof cases')
    split = manifest['schema'].endswith('/2')
    if split and len(raw) > 2 * 1024 * 1024:
        raise ValueError('Oversized software stack proof index')
    cases, files, names = [], {}, set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str):
            raise ValueError('Malformed software stack case')
        name = row['name']
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', name) is None or name in names:
            raise ValueError('Duplicate or invalid software stack case name')
        names.add(name)
        case = row
        if split:
            expected = 'Tools/software_stack_cases/' + name + '.json'
            if (set(row) != {'name', 'path', 'sha256'} or row['path'] != expected or
                    not isinstance(row['sha256'], str) or
                    re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is None):
                raise ValueError('Unsafe or incomplete software stack case reference')
            case_raw = _File_Read(root_path, expected, 2 * 1024 * 1024)
            if hashlib.sha256(case_raw).hexdigest() != row['sha256']:
                raise ValueError('Changed software stack case: ' + name)
            case = json.loads(case_raw, object_pairs_hook=_Object_Parse)
            if not isinstance(case, dict) or case.get('name') != name:
                raise ValueError('Mismatched software stack case identity')
            files[name] = {'path': expected, 'sha256': row['sha256']}
        cases.append(case)
    return {**manifest, 'cases': cases, 'sealed_case_files': files}
