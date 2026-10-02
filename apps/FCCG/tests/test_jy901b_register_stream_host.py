"""Actual generated driver with bounded UART queue and clock fault injection."""
from test_jy901b_boot_probe_host import _CompilerCommand, _CompileAndRun, _ProjectGet


def test_generated_jy901b_register_stream_and_deadline(tmp_path, workspace_root):
    project = _ProjectGet(tmp_path, workspace_root)
    command = _CompilerCommand(project) + [
        '-I', str(project), '-ffunction-sections', '-fdata-sections',
        '-Wl,--gc-sections',
    ]
    command += [str(project / source) for source in (
        'Common/Src/common_ringbuf.c', 'Common/Src/silverstar_assert.c',
        'Generated/Src/project_resources.c',
    )]
    command += [str(workspace_root / 'tests/fixtures/jy901b_register_stream_host.c'), '-lm']
    _CompileAndRun(command, project, tmp_path / 'register-stream.exe')
