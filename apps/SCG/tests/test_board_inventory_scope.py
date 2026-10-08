from silverstar_fccg.project import resources


def test_hardware_snapshot_is_shared_only_within_transaction(monkeypatch):
    manifest = object()
    reads = []

    def read(value):
        snapshot = object()
        reads.append((value, snapshot))
        return snapshot

    monkeypatch.setattr(resources, '_BoardHardwareInventory_Read', read)
    outside = resources.BoardHardwareInventory_Get(manifest)
    with resources.BoardInventory_ReadScope():
        first = resources.BoardHardwareInventory_Get(manifest)
        with resources.BoardInventory_ReadScope():
            assert resources.BoardHardwareInventory_Get(manifest) is first
        assert resources.BoardHardwareInventory_Get(manifest) is first
    with resources.BoardInventory_ReadScope():
        second = resources.BoardHardwareInventory_Get(manifest)
        assert second is not first
    assert resources.BoardHardwareInventory_Get(manifest) not in (outside, first, second)
    assert len(reads) == 4


def test_failed_hardware_read_is_not_cached_and_scope_retires(monkeypatch):
    calls = []

    def read(value):
        calls.append(value)
        if len(calls) == 1:
            raise ValueError('unreadable hardware inventory')
        return object()

    monkeypatch.setattr(resources, '_BoardHardwareInventory_Read', read)
    import pytest
    with pytest.raises(ValueError), resources.BoardInventory_ReadScope():
        resources.BoardHardwareInventory_Get(object())
    resources.BoardHardwareInventory_Get(object())
    assert len(calls) == 2
