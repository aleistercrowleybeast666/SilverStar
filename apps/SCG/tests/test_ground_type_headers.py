"""Compile the actual shared type headers emitted by both ground render routes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from test_round2_targets import _GroundBoardProject_Get
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import GroundFiles_Render


def test_ground_shared_type_header_closure( builtin_catalog, workspace_root, tmp_path, tmp_path_factory):
    route = 'ordinary-uart'
    files = GroundFiles_Render(_GroundBoardProject_Get(builtin_catalog), builtin_catalog, WorkspacePolicy(workspace_root))
    paths = ('Interfaces/Inc/system_device_types.h', 'Interfaces/Inc/system_navigation_provenance.h',
             'Common/Inc/silverstar_compiler.h')
    for path in paths:
        (tmp_path / Path(path).name).write_bytes(files[path])
    source = tmp_path / 'type-closure.c'
    source.write_text('#include "system_device_types.h"\nint main(void) { SystemInertialIncrement value = {0}; return (int)value.provenance.valid; }\n', encoding='utf8')
    binary = tmp_path / 'type-closure.exe'
    command = [shutil.which('gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror', '-pedantic', '-fanalyzer',
               '-I' + str(tmp_path), str(source), '-o', str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (tmp_path / 'compile.log').write_text(result.stdout + result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout + result.stderr
    ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    (tmp_path / 'type-closure-receipt.json').write_text(json.dumps({'route': route, 'command': command,
        'compile_exit': result.returncode, 'run_exit': ran.returncode,
        'generated_headers_sha256': {path: hashlib.sha256(files[path]).hexdigest() for path in paths}}, indent=2), encoding='utf8')
