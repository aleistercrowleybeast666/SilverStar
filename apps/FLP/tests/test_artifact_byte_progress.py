import numpy as np
import pytest

from silverstar_flp.core.artifacts import Artifact_Write, Artifact_Read, FileHash_Get
from silverstar_flp.core.context import TaskContext, TaskCancelledError


def test_hash_reports_actual_bytes(tmp_path):
    path = tmp_path / 'input.bin'
    path.write_bytes(b'x' * (3 * 1024 * 1024 + 7))
    reports = []
    FileHash_Get(path, TaskContext(progress_callback=lambda value, code: reports.append((value, code))), quantified=True)
    assert len(reports) >= 4
    assert reports[-1][0] == 1
    assert '|3145735|3145735' in reports[-1][1]


def test_array_compression_reports_chunks_and_cancels_before_publication(tmp_path):
    context = TaskContext()
    reports = []
    def report(value, code):
        reports.append((value, code))
        if code.startswith('progress.artifact.array_write|'):
            context.Cancel_Request()
    context.progress_callback = report
    with pytest.raises(TaskCancelledError):
        Artifact_Write(tmp_path / 'cancel.ssflp', np.arange(400000, dtype='float64'), {}, context)
    assert not (tmp_path / 'cancel.ssflp').exists()


@pytest.mark.parametrize('order', ['C', 'F', 'strided'])
def test_chunked_save_read_preserves_npy_layout_and_fine_progress(tmp_path, order):
    value = np.arange(800000, dtype='float64').reshape(400000, 2)
    if order == 'F':
        value = np.asfortranarray(value)
    elif order == 'strided':
        value = value[::2]
    reports = []
    context = TaskContext(progress_callback=lambda number, code: reports.append((number, code)))
    path = tmp_path / 'array.ssflp'
    ref = Artifact_Write(path, value, {}, context)
    np.testing.assert_array_equal(Artifact_Read(path, ref, {}), value)
    writes = [code for _, code in reports if code.startswith('progress.artifact.array_write|')]
    assert len(writes) >= 3
    numbers = [number for number, _ in reports]
    assert numbers == sorted(numbers) and max(numbers) < 1
