"""Lossless sealed case storage, including failures in unselected inputs."""
import hashlib
import json
from pathlib import Path

import pytest

from silverstar_fccg.project.stack_manifest import Manifest_Load

SCG = Path(__file__).resolve().parents[1]
TOOLS = SCG/'plugins/builtin/silverstar_core_0_1_0/payload/Tools'


def _Hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _Write(root):
    directory = root/'Tools/software_stack_cases'
    directory.mkdir(parents=True)
    cases = [{'name': name, 'complete_source_inputs': {'a.c': 'a'*64},
              'compiled_artifacts': {'firmware.elf': 'b'*64}, 'review': 'preserve all fields'}
             for name in ('selected', 'unselected')]
    rows = []
    for case in cases:
        path = directory/(case['name']+'.json')
        path.write_text(json.dumps(case), encoding='utf8')
        rows.append(dict(name=case['name'], path=path.relative_to(root).as_posix(), sha256=_Hash(path)))
    manifest = dict(schema='silverstar.software-stack-inputs/2', review_revision='test', cases=rows)
    path = root/'Tools/software_stack_inputs.json'
    path.write_text(json.dumps(manifest), encoding='utf8')
    return path, manifest, cases


def test_all_twenty_cases_equal_reviewed_pre_split_values_and_gui_uses_same_parser():
    mirror = SCG/'src/silverstar_fccg/project/stack_manifest.py'
    assert mirror.read_bytes() == (TOOLS/'stack_manifest.py').read_bytes()
    proof = json.loads((SCG/'tests/fixtures/stack_manifest_review_20261110.json').read_bytes())
    loaded = Manifest_Load(TOOLS.parent, TOOLS/'software_stack_inputs.json', proof['split_index_sha256'])
    actual = {case['name']: hashlib.sha256(json.dumps(case, sort_keys=True,
              separators=(',', ':')).encode()).hexdigest() for case in loaded['cases']}
    assert actual == proof['unchanged_case_canonical_sha256']
    assert len(actual) == proof['case_count'] == 20
    assert {name+'-'+config for name in ('f407', 'installation', 'h743', 'pid', 'lqr')
            for config in ('Release', 'Debug')} <= set(actual)
    assert all((TOOLS.parent/row['path']).stat().st_size < 2*1024*1024
               for row in loaded['sealed_case_files'].values())


def test_split_and_legacy_preserve_complete_case_data(tmp_path):
    path, manifest, cases = _Write(tmp_path)
    actual = Manifest_Load(tmp_path, path, _Hash(path))
    assert actual['cases'] == cases and len(actual['sealed_case_files']) == 2
    manifest.update(schema='silverstar.software-stack-inputs/1', cases=cases)
    path.write_text(json.dumps(manifest), encoding='utf8')
    legacy = Manifest_Load(tmp_path, path, _Hash(path))
    assert legacy['cases'] == cases and legacy['sealed_case_files'] == {}


@pytest.mark.parametrize('change', ('missing', 'bytes', 'identity', 'traversal', 'absolute',
                                  'duplicate_case', 'missing_hash', 'empty', 'schema', 'index_hash',
                                  'duplicate_json_key', 'oversized_case', 'oversized_index', 'linked'))
def test_incomplete_or_changed_index_rejects_even_unselected_cases(tmp_path, monkeypatch, change):
    path, manifest, _ = _Write(tmp_path)
    digest = _Hash(path)
    row = manifest['cases'][1]
    case_path = tmp_path/row['path']
    if change == 'missing': case_path.unlink()
    if change == 'bytes': case_path.write_bytes(case_path.read_bytes()+b'\n')
    if change == 'identity':
        case_path.write_text('{"name":"wrong"}', encoding='utf8')
        row['sha256'] = _Hash(case_path)
    if change == 'traversal': row['path'] = 'Tools/software_stack_cases/../../outside.json'
    if change == 'absolute': row['path'] = str(case_path.resolve())
    if change == 'duplicate_case': manifest['cases'].append(dict(row))
    if change == 'missing_hash': row.pop('sha256')
    if change == 'empty': manifest['cases'] = []
    if change == 'schema': manifest['schema'] = 'unknown'
    if change == 'index_hash': manifest['cases'].pop()
    if change == 'duplicate_json_key':
        case_path.write_text('{"name":"unselected","name":"unselected"}', encoding='utf8')
        row['sha256'] = _Hash(case_path)
    if change == 'oversized_case':
        case_path.write_bytes(b' '*(2*1024*1024+1))
        row['sha256'] = _Hash(case_path)
    if change == 'linked':
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda value: value == case_path or original(value))
    path.write_text(json.dumps(manifest)+(' '*(2*1024*1024) if change == 'oversized_index' else ''), encoding='utf8')
    if change != 'index_hash': digest = _Hash(path)
    with pytest.raises((ValueError, OSError)):
        Manifest_Load(tmp_path, path, digest)
