"""Staged wire boundary tests; root-owned JSON is the only layout authority."""
from copy import deepcopy
from dataclasses import replace
from importlib import import_module
import json
from pathlib import Path
import struct

import pytest

from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.catalog import RecordLayout
from silverstar_flp.decoder_profiles.errors import DecoderProfileError


def _Contract_Get():
    root = next(p for p in Path(__file__).resolve().parents if (p / "AGENTS.md").is_file())
    return json.loads((root / "contracts/navigation_fusion_timing_records_v2.json").read_text("utf8"))


def _Api_Get():
    return import_module("silverstar_flp.decoder_profiles.fusion_timing_records")


def _Layout_Create(record):
    # Contract offset is a byte address. Catalog offset means a value transform,
    # so it MUST NOT be passed to FieldLayout as a transform.
    fields = [{k: f[k] for k in ("name", "type", "count")}
              for f in record["v1_fields"] + record["appended_fields"]]
    return RecordLayout.FromDocument({"id": record["record_id"],
        "version": record["record_version"], "name": record["name"],
        "payload_size": record["payload_size"], "fields": fields}, 0)


def _Record_Create(name, mode=0):
    contract = _Contract_Get()
    definition = next(r for r in contract["records"] if r["name"] == name)
    payload = {f["name"]: (0 if f["count"] == 1 else [0] * f["count"])
               for f in definition["v1_fields"] + definition["appended_fields"]}
    flags = contract["timing_flags"]
    mask = flags["SOURCE_RESOLVED"] | flags["APPLICATION_EPOCH_VALID"] | flags["TRUSTED_SOURCE"]
    payload.update(sample_timestamp_us=1_200_000, receive_timestamp_us=1_490_000,
        source_id=1 if name == "BARO_MEASUREMENT" else 0,
        calibration_generation=7, fusion_timing_mode=mode)
    if name == "GNSS_MEASUREMENT":
        payload.update(sequence=12, replay_epoch=3, replay_generation=999,
            estimator_present_timestamp_us=1_500_000,
            position_usable=1, fusion_allowed=1, valid_group_mask=15,
            position_variance_m2=[1, 1, 1], velocity_variance_m2ps2=[1, 1, 1])
        for prefix in ("position", "velocity"):
            payload[prefix + "_measurement_timestamp_us"] = 1_200_000
            payload[prefix + "_source_timestamp_us"] = 1_200_000
            payload[prefix + "_application_timestamp_us"] = 1_500_000 if mode == 0 else 1_200_000
            payload[prefix + "_timing_flags"] = mask
            payload[prefix + "_execution_result"] = 0
            payload[prefix + "_replay_result"] = 255 if mode == 0 else 0
    else:
        payload.update(measurement_timestamp_us=1_200_000,
            application_timestamp_us=1_500_000 if mode == 0 else 1_200_000,
            timing_flags=mask, execution_result=0)
        if name == "BARO_MEASUREMENT":
            payload.update(source_timestamp_us=1_200_000,
                estimator_present_timestamp_us=1_500_000,
                sequence=12, replay_epoch=3, replay_generation=999,
                measurement_timestamp_trusted=1, variance_m2=1, valid_mask=1,
                replay_result=255 if mode == 0 else 0)
        else:
            payload.update(evaluation_timestamp_us=1_500_000, epoch=3, group=2,
                source_sequence=12, physically_valid=1, admitted=1,
                base_variance=[1, 1], effective_variance=[1, 1],
                quality_scale=1, consistency_scale=1, robust_scale=1)
    return DecodedRecord(definition["record_id"], name, 2, definition["payload_size"],
                          500, 1_500_000, 0, payload, 100)


@pytest.mark.parametrize('component,name', [
    ('silverstar.algorithm.estimator.kf6', 'BARO_MEASUREMENT'),
    ('silverstar.algorithm.estimator.eskf15', 'ESKF15_MEASUREMENT'),
])
@pytest.mark.parametrize('execution', [0, 1, 2, 3, 4, 5, 6, 7])
def test_exact_log_open_keeps_honest_fault_records_readable_and_source_bytes_immutable(tmp_path, component, name, execution):
    from silverstar_flp.decoder_profiles import DecoderProfileCache
    from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
    from silverstar_flp.plugins.registry import builtin_registry
    from tests.test_decoder_profiles import (_CatalogDocument_Build, _PackageFiles_Build,
        _Package_Write, _DescriptorPayload_Build, _CalibrationNonePayload_Build)
    from tests.test_fusion_timing_contract import _TimingDocument
    from tests.sslog_synthetic import SyntheticSslogBuilder, Event_Payload
    catalog = _CatalogDocument_Build()
    contract = _Contract_Get()
    for definition in contract['records']:
        catalog['records'].append(dict(id=definition['record_id'], version=2,
            name=definition['name'], payload_size=definition['payload_size'],
            fields=[{k: f[k] for k in ('name', 'type', 'count')}
                    for f in definition['v1_fields'] + definition['appended_fields']]))
    files, hashes = _PackageFiles_Build(catalog_document=catalog, semantics_document=_TimingDocument(component))
    package, _ = _Package_Write(tmp_path / 'exact.ssdecoder', files=files)
    record = _Record_Create(name)
    payload = dict(record.payload)
    payload['execution_result'] = execution
    if execution not in (0, 6):
        payload.update(application_timestamp_us=0, timing_flags=5)
    if execution == 2:
        payload['measurement_timestamp_us' if name == 'ESKF15_MEASUREMENT' else 'source_timestamp_us'] = 1
    definition = next(r for r in contract['records'] if r['name'] == name)
    raw = bytearray(definition['payload_size'])
    formats = {'u8': 'B', 'u32': 'I', 'u64': 'Q', 'f32': 'f'}
    for field in definition['v1_fields'] + definition['appended_fields']:
        values = [payload[field['name']]] if field['count'] == 1 else payload[field['name']]
        struct.pack_into('<' + formats[field['type']] * field['count'], raw, field['offset'], *values)
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1d, _DescriptorPayload_Build(hashes), 999_997)
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), 999_998)
    builder.Record_Add(0x02, Event_Payload(0x03), 1_000_000)
    builder.Record_Add(definition['record_id'], bytes(raw), 1_500_000, record_version=2)
    path = builder.File_Write(tmp_path / 'input.sslog')
    before = (path.read_bytes(), package.read_bytes())
    coordinator = LogOpenCoordinator(builtin_registry(), cache=DecoderProfileCache(tmp_path / 'cache'))
    request = LogOpenRequest(log_path=path, decoder_package_path=package)
    for _ in range(2):  # Cold parsing and cached result both preserve this boundary.
        dataset = coordinator.Open(request).dataset
        opened = dataset.Records_Get(name)[0]
        assert opened.payload['execution_result'] == execution
        assert opened.payload['application_timestamp_us'] == payload['application_timestamp_us']
        assert (path.read_bytes(), package.read_bytes()) == before


@pytest.mark.parametrize("definition", _Contract_Get()["records"], ids=lambda r: r["name"])
def test_exact_layout_decodes_at_contract_offsets_and_preserves_prefix(definition):
    layout = _Layout_Create(definition)
    _Api_Get().FusionTimingLayout_Validate(layout)
    raw = bytearray(definition["payload_size"])
    formats = {"u8": "B", "u32": "I", "u64": "Q", "f32": "f"}
    expected = {}
    for index, field in enumerate(definition["v1_fields"] + definition["appended_fields"]):
        values = [index + 1] * field["count"]
        struct.pack_into("<" + formats[field["type"]] * field["count"], raw, field["offset"], *values)
        expected[field["name"]] = values[0] if field["count"] == 1 else tuple(values)
    original = bytes(raw)
    decoded = layout.Decode(original)
    assert decoded == expected
    assert bytes(raw) == original
    v1 = replace(layout, record_version=1, payload_size=definition["v1_payload_size"],
                 fields=layout.fields[:len(definition["v1_fields"])]).Decode(original[:definition["v1_payload_size"]])
    assert v1 == {f["name"]: decoded[f["name"]] for f in definition["v1_fields"]}


@pytest.mark.parametrize("name", [r["name"] for r in _Contract_Get()["records"]])
def test_runtime_validates_without_mutating_records(name):
    record = _Record_Create(name)
    before = deepcopy(dict(record.payload))
    operations = _Api_Get().FusionTimingOperations_Get(record, declared_mode=0)
    assert operations
    for operation in operations:
        assert operation.source_us == 1_200_000
        assert operation.application_us == operation.present_us == 1_500_000
        assert operation.identity.calibration_generation == 7
        assert operation.identity.source_sequence == 12
        assert operation.identity.mission_epoch == 3
    assert dict(record.payload) == before


@pytest.mark.parametrize("field,value", [
    ("fusion_timing_mode", 2), ("fusion_timing_mode", True),
    ("timing_flags", 0x80), ("timing_flags", 15),  # trusted and fallback together
    ("timing_reserved", 1), ("execution_result", 255), ("execution_result", 8),
    ("application_timestamp_us", 1_200_000), ("source_id", 2),
])
def test_current_rejects_wrong_mode_flags_result_epoch_and_baro_namespace(field, value):
    record = _Record_Create("BARO_MEASUREMENT")
    mutated = replace(record, payload={**record.payload, field: value})
    with pytest.raises(DecoderProfileError, match="fusion_timing_"):
        _Api_Get().FusionTimingOperations_Get(mutated, declared_mode=0)


def test_current_replay_sentinel_is_not_execution_success_or_nis_acceptance():
    record = _Record_Create("BARO_MEASUREMENT")
    rejected = replace(record, payload={**record.payload, "update_result": 2, "nis": 100.0})
    operation, = _Api_Get().FusionTimingOperations_Get(rejected, declared_mode=0)
    assert operation.execution_result == 0
    assert operation.application_us == 1_500_000
    with pytest.raises(DecoderProfileError, match="fusion_timing_"):
        _Api_Get().FusionTimingOperations_Get(
            replace(record, payload={**record.payload, "replay_result": 0}), declared_mode=0)


def test_legacy_numeric_error_accepts_unknown_application_epoch_without_claiming_no_attempt():
    record = _Record_Create("BARO_MEASUREMENT", mode=1)
    payload = {**record.payload, "execution_result": 6, "replay_result": 6,
               "application_timestamp_us": 0, "timing_flags": 5, "update_result": 4}
    operation, = _Api_Get().FusionTimingOperations_Get(replace(record, payload=payload), declared_mode=1)
    assert operation.application_us is None
    assert operation.execution_result == 6
    # Deliberately no attempted=False assertion: the contract forbids that inference.


def test_honestly_recorded_stale_rejection_remains_decodable():
    record = _Record_Create("BARO_MEASUREMENT")
    payload = {**record.payload, "source_timestamp_us": 900_000,
               "measurement_timestamp_us": 900_000, "execution_result": 2,
               "application_timestamp_us": 0, "timing_flags": 5, "update_result": 3}
    operation, = _Api_Get().FusionTimingOperations_Get(replace(record, payload=payload), declared_mode=0)
    assert operation.source_us == 900_000
    assert operation.application_us is None
    assert operation.execution_result == 2


def test_header_sequence_and_replay_generation_do_not_define_source_identity():
    record = _Record_Create("BARO_MEASUREMENT")
    api = _Api_Get()
    first, = api.FusionTimingOperations_Get(record, declared_mode=0)
    same_source, = api.FusionTimingOperations_Get(replace(record, record_sequence=999,
        payload={**record.payload, "replay_generation": 1234}), declared_mode=0)
    assert same_source.identity == first.identity
    new_generation, = api.FusionTimingOperations_Get(replace(record,
        payload={**record.payload, "calibration_generation": 8}), declared_mode=0)
    assert new_generation.identity != first.identity


@pytest.mark.parametrize("field", ["source_sequence", "calibration_generation", "source_id", "epoch"])
def test_eskf_current_missing_identity_never_uses_header_or_native_guess(field):
    record = _Record_Create("ESKF15_MEASUREMENT")
    payload = dict(record.payload)
    del payload[field]
    with pytest.raises(DecoderProfileError, match="fusion_timing_"):
        _Api_Get().FusionTimingOperations_Get(replace(record, payload=payload), declared_mode=0)


@pytest.mark.parametrize("change", ["field_type", "field_order", "scale", "version", "payload_size"])
def test_catalog_identity_requires_exact_fields_not_just_name_and_length(change):
    definition = _Contract_Get()["records"][0]
    layout = _Layout_Create(definition)
    fields = list(layout.fields)
    if change == "field_type":
        fields[0] = replace(fields[0], data_type="f64")
    elif change == "field_order":
        fields[0], fields[1] = fields[1], fields[0]
    elif change == "scale":
        fields[0] = replace(fields[0], scale=.001)
    layout = replace(layout, fields=tuple(fields),
        record_version=3 if change == "version" else 2,
        payload_size=204 if change == "payload_size" else layout.payload_size)
    with pytest.raises(DecoderProfileError, match="fusion_timing_"):
        _Api_Get().FusionTimingLayout_Validate(layout)
