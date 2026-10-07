"""Small thresholds reproduce the real flat-record limit without large inputs."""
from dataclasses import replace
import gzip
import json
from types import MappingProxyType

import numpy as np
import pytest

from silverstar_flp.core import artifacts, record_blocks
from silverstar_flp.core.artifacts import Artifact_Read, Artifact_Verify, Artifact_Write, FileHash_Get
from silverstar_flp.core.dataset import DecodedRecord


def _Records(count=64):
    records = []
    for row in range(count):
        array = np.asarray([row, -row], dtype=np.int16)
        array.setflags(write=False)
        payload = {f"value_{column}": float(row + column) for column in range(8)}
        payload.update(vector=(row * .1, row * .2, row * .3), numpy_scalar=np.float32(row),
                       raw_payload=bytes([row % 256]) * (row % 5),
                       status="ready" if row % 2 else "waiting", optional=None if row % 3 else float(row),
                       frozen=MappingProxyType({"gain": row + 1}), mutable={"gain": row + 2},
                       list_value=[row, row + 1], array=array)
        records.append(DecodedRecord(1, "SAMPLE", 2, 64, row, 1_000_000 + row * 4000,
                                     1, payload, 100 + row * 80))
    return tuple(records)


def _Rewrite(path, reference, transform):
    manifest = path.parent / reference["path"]
    data = json.loads(gzip.decompress(manifest.read_bytes()))
    transform(data, manifest.parent)
    manifest.write_bytes(gzip.compress(json.dumps(data).encode()))
    reference["sha256"] = FileHash_Get(manifest)


def test_flat_limit_failure_then_column_blocks_preserve_all_typed_frozen_records(tmp_path, monkeypatch):
    records = _Records()
    path = tmp_path / "project.ssflp"
    monkeypatch.setattr(artifacts, "MAX_NODES", 2200)
    monkeypatch.setattr(artifacts, "MAX_OBJECTS", 2200)
    with pytest.raises(ValueError, match="artifact_structure_limit"):
        # The legacy flat list/tuple encoder visits the same fields per record.
        Artifact_Write(path, list(records), {})
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ROWS", 32)
    reference = Artifact_Write(path, records, {})
    restored = Artifact_Read(path, reference, {})
    assert len(restored) == len(records) and repr(restored) == repr(records)
    for first, second in zip(records, restored):
        assert type(second) is DecodedRecord
        assert isinstance(second.payload, MappingProxyType)
        assert isinstance(second.payload["frozen"], MappingProxyType)
        assert type(second.payload["mutable"]) is dict
        assert type(second.payload["numpy_scalar"]) is np.float32
        np.testing.assert_array_equal(first.payload["array"], second.payload["array"])
        assert not second.payload["array"].flags.writeable
        with pytest.raises(TypeError):
            second.payload["value_0"] = 9


@pytest.mark.parametrize("budget", ["MAX_OBJECTS", "MAX_LIVE_BYTES", "MAX_MANIFEST_BYTES", "MAX_RECORD_BLOCKS"])
def test_multiple_blocks_cannot_reset_cumulative_budgets(tmp_path, monkeypatch, budget):
    from silverstar_flp.core.context import TaskContext
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ROWS", 32)
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, _Records(), {})
    manifest = json.loads(gzip.decompress((path.parent / reference["path"]).read_bytes()))
    specs = manifest["payload"]["record_blocks"]
    directory = (path.parent / reference["path"]).parent
    raw_main = len(gzip.decompress((path.parent / reference["path"]).read_bytes()))
    single = []
    for spec in specs:
        decoder = artifacts._Decoder(directory, manifest["arrays"], TaskContext(), allow_records=True, json_bytes=raw_main)
        decoder.RecordBlocks_Read([spec])
        single.append(decoder)
    # Each block individually fits the chosen budget; the full sum must fail.
    if budget == "MAX_RECORD_BLOCKS":
        monkeypatch.setattr(artifacts, budget, 1)
    elif budget == "MAX_MANIFEST_BYTES":
        monkeypatch.setattr(artifacts, budget, raw_main + max(spec["raw_bytes"] for spec in specs) + 1)
    else:
        attribute = "object_count" if budget == "MAX_OBJECTS" else "live_bytes"
        monkeypatch.setattr(artifacts, budget, max(getattr(decoder, attribute) for decoder in single) + 10)
    for spec in specs:
        artifacts._Decoder(directory, manifest["arrays"], TaskContext(), allow_records=True,
                           json_bytes=raw_main).RecordBlocks_Read([spec])
    with pytest.raises(ValueError, match="limit|large|record_blocks_invalid"):
        Artifact_Read(path, reference, {})
    with pytest.raises(ValueError, match="limit|large|record_blocks_invalid"):
        Artifact_Verify(path, reference, {})


@pytest.mark.parametrize("fault", ["missing", "corrupt", "traversal", "expanded_size", "count"])
def test_record_block_admission_rejects_damage_and_hostile_references(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ROWS", 32)
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, _Records(), {})
    def damage(manifest, directory):
        spec = manifest["payload"]["record_blocks"][0]
        if fault == "missing":
            (directory / spec["name"]).unlink()
        elif fault == "corrupt":
            (directory / spec["name"]).write_bytes(b"corrupt")
        elif fault == "traversal":
            spec["name"] = "../payload.records.json.gz"
        elif fault == "expanded_size":
            spec["raw_bytes"] += 1
        else:
            spec["count"] -= 1
    _Rewrite(path, reference, damage)
    for operation in (Artifact_Read, Artifact_Verify):
        with pytest.raises((ValueError, OSError)):
            operation(path, reference, {})


def test_storage_version_one_remains_readable(tmp_path):
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, {"values": np.arange(5)}, {})
    _Rewrite(path, reference, lambda manifest, _: manifest.update(version=1))
    np.testing.assert_array_equal(Artifact_Read(path, reference, {})["values"], np.arange(5))


def test_save_verifies_without_full_reader_and_explicit_reopen_uses_reader(tmp_path, monkeypatch):
    from tests.test_project_artifact_boundaries import _SmallRun
    from silverstar_flp.core.project import Project_Load, Project_Save, ProjectResults_Load
    from silverstar_flp.core.parse_cache import DatasetCache_Read
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ROWS", 8)
    opened, document, store = _SmallRun(tmp_path)
    original = artifacts._Artifact_Load
    with monkeypatch.context() as scoped:
        def bounded(*args, **kwargs):
            assert kwargs["verify_only"], "Save must not build a full decoded copy"
            return original(*args, **kwargs)
        scoped.setattr(artifacts, "_Artifact_Load", bounded)
        Project_Save(document, document.project_path, dataset=opened.dataset, replay_store=store)
    loaded = Project_Load(document.project_path)
    restored = DatasetCache_Read(loaded.project_path, loaded.parse_artifact,
        opened.dataset.metadata["parse_identity"], opened.dataset.source_path)
    assert repr(restored.records) == repr(opened.dataset.records)
    assert restored.data_quality == opened.dataset.data_quality
    assert restored.diagnostics.to_dict() == opened.dataset.diagnostics.to_dict()
    assert len(ProjectResults_Load(loaded).Entries_Get()) == 1


@pytest.mark.parametrize("fault", ["array", "block", "reference"])
def test_one_use_verified_write_receipt_cannot_mask_corruption(tmp_path, monkeypatch, fault):
    from tests.test_project_artifact_boundaries import _SmallRun
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ROWS", 8)
    opened, document, _ = _SmallRun(tmp_path)
    reference = Artifact_Write(document.project_path, opened.dataset,
                               opened.dataset.metadata["parse_identity"])
    directory = (document.project_path.parent / reference["path"]).parent
    if fault == "array":
        next(directory.glob("*.npy.gz")).write_bytes(b"corrupt")
    elif fault == "block":
        next(directory.glob("*.records.json.gz")).write_bytes(b"corrupt")
    else:
        reference["path"] = "../untrusted/manifest.json.gz"
    with pytest.raises(ValueError, match="receipt"):
        Artifact_Read(document.project_path, reference, opened.dataset.metadata["parse_identity"])
    assert reference.payload is None
    assert reference.context is None and reference.files == ()


def test_wide_record_blocks_reduce_rows_before_any_array_publication(tmp_path, monkeypatch):
    records = _Records(4)
    wide = np.arange(2500, dtype=np.float64)
    wide.setflags(write=False)
    records = tuple(replace(record, payload={**record.payload, "array": wide + index})
                    for index, record in enumerate(records))
    monkeypatch.setattr(record_blocks, "RECORD_BLOCK_ALLOC_BYTES", 50_000)
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, records, {})
    restored = Artifact_Read(path, reference, {})
    assert len(restored) == 4
    for first, second in zip(records, restored):
        np.testing.assert_array_equal(first.payload["array"], second.payload["array"])


@pytest.mark.parametrize("bits", [
    [0x8000000000000000, 0x0000000000000000],
    [0x0000000000000000, 0x8000000000000000],
    [0x7ff8000000000042, 0x7ff8000000000042],
    [0xfff8000000000042, 0x7ff8000000000043],
])
def test_python_float_record_payload_preserves_signed_zero_and_nan_bits(tmp_path, bits):
    values = np.asarray(bits, dtype=np.uint64).view(np.float64)
    records = tuple(replace(record, payload={"value": float(value)})
                    for record, value in zip(_Records(2), values))
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, records, {})
    restored = Artifact_Read(path, reference, {})
    actual = np.asarray([record.payload["value"] for record in restored], dtype=np.float64).view(np.uint64)
    np.testing.assert_array_equal(actual, np.asarray(bits, dtype=np.uint64))


@pytest.mark.parametrize("payloads", [
    [{"a": 1.0}, {"b": 2.0}],
    [{"a": 1.0, "b": 2.0}, {"b": 3.0, "a": 4.0}],
    [{}, {"a": None}],
    [{"nested": {"a": 1}}, {"nested": {"b": 2}}],
])
def test_record_payload_key_set_and_insertion_order_roundtrip(tmp_path, payloads):
    records = tuple(replace(record, payload=payload) for record, payload in zip(_Records(2), payloads))
    path = tmp_path / "project.ssflp"
    reference = Artifact_Write(path, records, {})
    restored = Artifact_Read(path, reference, {})
    assert repr(restored) == repr(records)
    for first, second in zip(records, restored):
        assert tuple(second.payload) == tuple(first.payload)
        assert dict(second.payload) == dict(first.payload)
        for key in set(first.payload) ^ {"a", "b"}:
            assert (key in second.payload) == (key in first.payload)
