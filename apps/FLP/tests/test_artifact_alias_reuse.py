import numpy as np
from silverstar_flp.core.artifacts import _Encoder
from silverstar_flp.core.context import TaskContext


def test_owned_immutable_alias_is_written_once_but_mutable_array_is_rehashed(tmp_path):
    directory = tmp_path/'generation'; directory.mkdir()
    encoder = _Encoder(directory, TaskContext())
    array = np.arange(20, dtype=np.float64); array.setflags(write=False)
    first = encoder.Encode(array)
    writes = encoder.array_bytes_written
    assert encoder.Encode(array) == first
    assert encoder.array_bytes_written == writes
    mutable = np.arange(20, dtype=np.float64)
    before = encoder.Encode(mutable)
    mutable[0] = 100
    after = encoder.Encode(mutable)
    assert after != before
    view = mutable.view(); view.setflags(write=False)
    before = encoder.Encode(view)
    mutable[0] = 200
    assert encoder.Encode(view) != before
    immutable_view = array.view()
    assert encoder.Encode(immutable_view) == first
    writes = encoder.array_bytes_written
    assert encoder.Encode(immutable_view) == first
    assert encoder.array_bytes_written == writes
