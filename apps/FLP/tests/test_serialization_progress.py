import numpy as np

from silverstar_flp.core.artifacts import _Encoder
from silverstar_flp.core.context import TaskContext


def test_serialization_reports_completed_container_items(tmp_path):
    directory = tmp_path / 'generation'
    directory.mkdir()
    reports = []
    encoder = _Encoder(directory, TaskContext(progress_callback=lambda value, code: reports.append((value, code))))
    values = tuple({'array': np.arange(32) + index} for index in range(3))
    encoder.Encode(values)
    completed = [(value, code) for value, code in reports if code.startswith('progress.artifact.objects|')]
    assert any(0 < value < 1 for value, _code in completed)
    assert completed[-1] == (1.0, 'progress.artifact.objects|3|3')
    assert all(a[0] <= b[0] for a, b in zip(completed, completed[1:]))
