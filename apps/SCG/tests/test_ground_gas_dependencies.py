"""Real ARM assembler dependency tests; no target execution or synthetic .d pass."""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import shutil
import subprocess

import pytest

from test_ground_usb_review_boundaries import _ArtifactModule_Get, _ArmCompiler_Get, PAYLOAD
from silverstar_fccg.generator.multi_target import _Makefile_Render


def _Run(command, root, *, expected=0):
    result = subprocess.run(list(map(str, command)), cwd=root, capture_output=True, text=True, timeout=120)
    with (root / 'commands.jsonl').open('a', encoding='utf8') as log:
        log.write(json.dumps({'command': list(map(str, command)), 'exit': result.returncode,
                              'stdout': result.stdout, 'stderr': result.stderr}) + '\n')
    if expected == 0:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, result.stdout + result.stderr
    return result


def _Source_Get(kind, directive, path):
    if kind == 'c':
        first = '.pushsection .rodata.review,"a",%progbits\n.inc'
        second = directive.removeprefix('inc') + ' "' + path + '"\n.popsection\n'
        return '__asm__(' + json.dumps(first) + ' ' + json.dumps(second) + ');\nint Probe(void) {return 0;}\n'
    return ('.syntax unified\n.thumb\n.section .rodata.review,"a",%progbits\n'
            '.macro Load op\n.\\op "' + path + '"\n.endm\nLoad ' + directive + '\n')


def _Compile(root, source, *, build='build'):
    compiler = _ArmCompiler_Get()
    obj = Path(build) / Path(source).with_suffix('.o')
    (root / obj).parent.mkdir(parents=True, exist_ok=True)
    command = [compiler, '-mcpu=cortex-m3', '-mthumb', '-save-temps=obj', '-MD', '-MP',
               '-Wa,--MD,' + obj.with_suffix('.gas.d').as_posix()]
    if source.endswith('.c'):
        _Run([compiler, '-mcpu=cortex-m3', '-mthumb', '-std=c11', '-MD', '-MP', '-MF', obj.with_suffix('.d').as_posix(),
              '-MT', obj.as_posix(), '-S', source, '-o', obj.with_suffix('.s').as_posix()], root)
        _ArtifactModule_Get().AssemblerSource_Prepare(root, {'sources': [source]}, source, build)
        _Run([compiler, '-mcpu=cortex-m3', '-mthumb', '-x', 'assembler',
              '-Wa,--MD,' + obj.with_suffix('.gas.d').as_posix(), '-c', obj.with_suffix('.s').as_posix(), '-o', obj.as_posix()], root)
    else:
        _Run([*command, '-x', 'assembler-with-cpp', '-c', source, '-o', obj.as_posix()], root)
    return compiler, obj


@pytest.mark.parametrize('kind', ['c', 's'])
@pytest.mark.parametrize('directive', ['incbin', 'include'])
def test_real_arm_cpp_and_gas_union_rejects_external_files(tmp_path, kind, directive):
    root = tmp_path / 'target'; root.mkdir()
    source = 'probe.' + kind
    external = tmp_path / 'outside data.txt'
    (root / source).write_text(_Source_Get(kind, directive, external.as_posix()), encoding='utf8')
    graph = {'sources': [source] if kind == 'c' else [], 'asm_sources': [source] if kind == 's' else []}
    module = _ArtifactModule_Get(); objects = []
    for value in (17, 29):
        external.write_bytes(bytes([value]) if directive == 'incbin' else f'.byte {value}\n'.encode())
        compiler, obj = _Compile(root, source)
        cpp = (root / obj.with_suffix('.d')).read_text()
        gas = (root / obj.with_suffix('.gas.d')).read_text()
        assert 'outside' not in cpp and 'outside' in gas
        with pytest.raises(ValueError, match='escaped copied target'):
            module.DependencyClosure_Validate(root, graph, compiler)
        objects.append((root / obj).read_bytes())
    assert objects[0] != objects[1], 'the real assembler must consume the changed external bytes'


@pytest.mark.parametrize('kind', ['c', 's'])
@pytest.mark.parametrize('build', ['build', 'build/analysis'])
def test_frozen_local_nested_assembler_dependencies_are_accepted(tmp_path, kind, build):
    source = 'probe.' + kind
    (tmp_path / 'asset.txt').write_bytes(b'\x11')
    (tmp_path / 'nested.txt').write_text('.include "leaf.txt"\n')
    (tmp_path / 'leaf.txt').write_text('.incbin "asset.txt"\n')
    (tmp_path / source).write_text(_Source_Get(kind, 'include', 'nested.txt'), encoding='utf8')
    compiler, obj = _Compile(tmp_path, source, build=build)
    graph = {'sources': [source] if kind == 'c' else [], 'asm_sources': [source] if kind == 's' else []}
    _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, graph, compiler, build_dir=build, source=source)
    gas = (tmp_path / obj.with_suffix('.gas.d')).read_text()
    assert all(name in gas for name in ('nested.txt', 'leaf.txt', 'asset.txt'))
    make = (tmp_path / obj.with_suffix('.deps.mk')).read_text()
    assert all(name in make for name in ('nested.txt', 'leaf.txt', 'asset.txt'))
    assert obj.with_suffix('.s').as_posix() in make


@pytest.mark.parametrize('failure', ['missing_gas', 'wrong_object', 'missing_input', 'other_build_input', 'temp_input', 'stale_object'])
def test_gas_evidence_is_bound_to_one_declared_object_and_saved_input(tmp_path, failure):
    (tmp_path / 'probe.c').write_text('int Probe(void) {return 0;}\n')
    compiler, obj = _Compile(tmp_path, 'probe.c')
    gas = tmp_path / obj.with_suffix('.gas.d')
    text = gas.read_text()
    reason = {'missing_gas': 'evidence missing', 'wrong_object': 'target differs',
              'missing_input': 'omit the exact', 'other_build_input': 'unexpected build-output',
              'temp_input': 'escaped copied target', 'stale_object': 'older than'}[failure]
    if failure == 'missing_gas':
        gas.unlink()  # This test's generated manifest only.
    elif failure == 'wrong_object':
        gas.write_text(text.replace('build/probe.o:', 'build/unrelated.o:'))
    elif failure == 'missing_input':
        gas.write_text('build/probe.o:\n')
    elif failure in {'other_build_input', 'temp_input'}:
        alternative = tmp_path / 'build/other.s' if failure == 'other_build_input' else tmp_path.parent / (tmp_path.name + '-temp.s')
        alternative.write_text('/* independent input */\n')
        gas.write_text(text.replace('build/probe.s', alternative.as_posix()))
    else:
        source = tmp_path / 'probe.c'; later = (tmp_path / obj).stat().st_mtime_ns + 1_000_000_000
        os.utime(source, ns=(later, later))
    with pytest.raises(ValueError, match=reason):
        _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, {'sources': ['probe.c']}, compiler)


def test_nested_assembler_include_cannot_hide_external_incbin(tmp_path):
    root = tmp_path / 'target'; root.mkdir()
    external = tmp_path / 'outside.txt'; external.write_bytes(b'\x11')
    (root / 'nested.txt').write_text('.incbin "' + external.as_posix() + '"\n')
    (root / 'probe.s').write_text(_Source_Get('s', 'include', 'nested.txt'))
    compiler, _ = _Compile(root, 'probe.s')
    with pytest.raises(ValueError, match='escaped copied target'):
        _ArtifactModule_Get().DependencyClosure_Validate(root, {'sources': [], 'asm_sources': ['probe.s']}, compiler)


def test_make_uses_validated_union_for_incremental_rebuild_and_rejects_before_link(tmp_path, monkeypatch):
    compiler = _ArmCompiler_Get()
    make = shutil.which('mingw32-make') or shutil.which('make')
    if make is None:
        candidate = Path('D:/msys64/ucrt64/bin/mingw32-make.exe')
        make = str(candidate) if candidate.is_file() else None
    if make is None:
        pytest.skip('GNU Make unavailable; incremental integration NOT PROVEN')
    (tmp_path / 'Core/Src').mkdir(parents=True)
    (tmp_path / 'Generated').mkdir(); (tmp_path / 'Tools').mkdir()
    for name in ('check_ground.py', 'ground_artifact_contract.py'):
        (tmp_path / 'Tools' / name).write_bytes((PAYLOAD / 'Tools' / name).read_bytes())
    source = 'Core/Src/probe.c'
    (tmp_path / source).write_text(_Source_Get('c', 'incbin', 'asset.txt'))
    asset = tmp_path / 'asset.txt'; asset.write_bytes(b'\x11')
    graph = {'sources': [source], 'asm_sources': []}
    (tmp_path / 'Generated/ground_source_graph.json').write_text(json.dumps(graph))
    profile = SimpleNamespace(mcu_flags=('-mcpu=cortex-m3', '-mthumb'), linker_script='unused.ld')
    (tmp_path / 'Makefile').write_text(_Makefile_Render((source,), (), (), (), profile, 'arm-none-eabi-'))
    import sys
    monkeypatch.setenv('PATH', str(Path(compiler).parent) + os.pathsep + os.environ['PATH'])
    command = [make, '-f', 'Makefile', 'build/Core/Src/probe.o', 'CC=' + Path(compiler).name, 'PYTHON=' + sys.executable]
    _Run(command, tmp_path)
    obj = tmp_path / 'build/Core/Src/probe.o'; before = obj.read_bytes()
    asset.write_bytes(b'\x1d')
    # -W exercises Make's dependency propagation for the asset, not a blanket -B.
    _Run([*command, '-W', 'asset.txt'], tmp_path)
    assert obj.read_bytes() != before
    # Even an already linked target must recheck both manifests before Make can
    # report success; removing evidence cannot hide behind current timestamps.
    elf = tmp_path / 'build/ground.elf'; elf.write_bytes(b'prior test artifact')
    gas = obj.with_suffix('.gas.d'); recorded = gas.read_bytes(); gas.unlink()
    whole = [make, '-f', 'Makefile', 'build/ground.elf', 'CC=' + Path(compiler).name, 'PYTHON=' + sys.executable]
    rejected = _Run(whole, tmp_path, expected=1)
    assert 'evidence missing' in rejected.stdout + rejected.stderr
    gas.write_bytes(recorded)
    outside = tmp_path.parent / (tmp_path.name + '-outside.txt'); outside.write_bytes(b'\x33')
    (tmp_path / source).write_text(_Source_Get('c', 'incbin', outside.as_posix()))
    result = _Run([*command, '-W', source], tmp_path, expected=1)
    assert 'escaped copied target' in result.stdout + result.stderr
    assert not obj.exists(), '.DELETE_ON_ERROR must not leave a rejected object publishable'
    # Repeating all/object must retry and fail, not reuse the failed object's timestamp.
    _Run(command, tmp_path, expected=1)


def test_source_label_preparation_does_not_discard_inline_assembly_dependencies(tmp_path):
    (tmp_path / 'Core').mkdir()
    external = tmp_path.parent / (tmp_path.name + '-outside.txt'); external.write_bytes(b'\x11')
    source = 'Core/probe.c'
    (tmp_path / source).write_text(_Source_Get('c', 'incbin', external.as_posix()))
    compiler, obj = _Compile(tmp_path, source)
    assembly = (tmp_path / obj.with_suffix('.s')).read_text()
    assert '.file "Core/probe.c"' in assembly
    assert external.as_posix() in assembly
    with pytest.raises(ValueError, match='escaped copied target'):
        _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, {'sources': [source]}, compiler)


def test_declared_c_and_asm_cannot_share_dependency_or_object_outputs(tmp_path):
    with pytest.raises(ValueError, match='collide on an object path'):
        _ArtifactModule_Get().DependencyClosure_Validate(tmp_path, {'sources': ['Core/probe.c'], 'asm_sources': ['Core/probe.s']})


@pytest.mark.parametrize('path_form', ['absolute', 'traversal'])
def test_assembler_preparation_cannot_rewrite_payload_outside_build(tmp_path, path_form):
    payload = tmp_path / 'probe.s'; payload.write_text('.file "probe.c"\n')
    source = (tmp_path / 'probe.c').as_posix() if path_form == 'absolute' else '../probe.c'
    with pytest.raises(ValueError, match='invalid build evidence path'):
        _ArtifactModule_Get().AssemblerSource_Prepare(tmp_path, {'sources': [source]}, source, 'build')
    assert payload.read_text() == '.file "probe.c"\n'
