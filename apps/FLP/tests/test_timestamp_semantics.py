from pathlib import Path

import pytest

from silverstar_flp.core.dataset import DecodedRecord, FlightDatasetBuilder
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.decoder_profiles import DecoderProfileError, ProjectSemantics, RecordCatalog
from tests.test_decoder_profiles import _CatalogDocument_Build, _SemanticsDocument_Build


def _ChannelTimes_Build(times, *, record_name="ESTIMATOR", view_extra=None, field_extra=None):
    catalog = _CatalogDocument_Build()
    fields = [{"name": name, "type": "u64", **(field_extra or {})} for name in times]
    fields += [
        {"name": name, "type": "f32", "count": 3} for name in ("position_enu_m", "velocity_enu_mps")
    ]
    size = sum((8 if f["type"] == "u64" else 4) * f.get("count", 1) for f in fields)
    catalog["records"] = [
        {"id": "0x60", "version": 0, "name": record_name, "payload_size": size, "fields": fields}
    ]
    semantics = _SemanticsDocument_Build()
    semantics["record_views"] = [
        {
            "record": record_name,
            "columns": ["position_enu_m", "velocity_enu_mps"],
            **(view_extra or {}),
        }
    ]
    bound = ProjectSemantics.FromDocument(semantics).Catalog_Bind(
        RecordCatalog.FromDocument(catalog)
    )
    payload = {**times, "position_enu_m": (1.0, 2.0, 3.0), "velocity_enu_mps": (4.0, 5.0, 6.0)}
    definitions = bound.ChannelDefinitions_Get(record_name, payload)
    builder = FlightDatasetBuilder()
    builder.Record_Add(
        DecodedRecord(0x60, record_name, 0, size, 1, 30000, 0, payload, 0), definitions
    )
    data = builder.Build(
        source_path=Path("SYNTHETIC_time.BIN"),
        file_size=0,
        header={},
        diagnostics=ParserDiagnostics(),
    )
    return [series.timestamp_us.tolist() for series in data.series.values()], definitions


@pytest.mark.parametrize(
    "names",
    [("baro_timestamp_us", "gnss_timestamp_us"), ("gnss_timestamp_us", "baro_timestamp_us")],
)
def test_ambiguous_state_timestamps_use_header_independent_of_order(names):
    times, definitions = _ChannelTimes_Build(dict(zip(names, (17000, 25000), strict=True)))
    assert times == [[30000], [30000]]
    assert all(d.timestamp_field is None for d in definitions)


@pytest.mark.parametrize(
    "name",
    [
        "IMU_NATIVE",
        "GNSS_NATIVE",
        "BARO_NATIVE",
        "HW_QUAT_NATIVE",
        "IMU_CORRECTED",
        "GNSS_MEASUREMENT",
        "BARO_MEASUREMENT",
    ],
)
def test_primary_sample_timestamp_is_preserved(name):
    times, _ = _ChannelTimes_Build(
        {"sample_timestamp_us": 17000, "receive_timestamp_us": 25000}, record_name=name
    )
    assert times == [[17000], [17000]]


@pytest.mark.parametrize("name", ["PURE_INS", "KF6_DIAGNOSTIC", "KF6_FULL_P"])
def test_state_without_payload_timestamp_keeps_header(name):
    times, _ = _ChannelTimes_Build({}, record_name=name)
    assert times == [[30000], [30000]]


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"measurement_timestamp_us": 17000}, 17000),
        ({"interval_end_timestamp_us": 17000, "receive_timestamp_us": 25000}, 17000),
        ({"receive_timestamp_us": 17000}, 17000),
        ({"receive_timestamp_us": 17000, "other_timestamp_us": 25000}, 30000),
    ],
)
def test_unique_candidate_and_increment_endpoint(payload, expected):
    times, _ = _ChannelTimes_Build(payload, record_name="INERTIAL_INCREMENT")
    assert times == [[expected], [expected]]


def test_explicit_view_timestamp_overrides_primary_sample():
    times, definitions = _ChannelTimes_Build(
        {"sample_timestamp_us": 17000, "receive_timestamp_us": 25000},
        view_extra={"timestamp_field": "receive_timestamp_us"},
    )
    assert times == [[25000], [25000]]
    assert all(d.timestamp_field == "receive_timestamp_us" for d in definitions)


@pytest.mark.parametrize("explicit", ["missing_timestamp_us", "position_enu_m", None, 3, ""])
def test_invalid_explicit_view_timestamp_is_rejected(explicit):
    with pytest.raises(DecoderProfileError, match="decoder_record_view_timestamp_field_invalid"):
        _ChannelTimes_Build(
            {"sample_timestamp_us": 17000}, view_extra={"timestamp_field": explicit}
        )


@pytest.mark.parametrize("field_extra", [{"type": "f32"}, {"count": 2}, {"scale": 0.001}])
def test_explicit_timestamp_must_be_scalar_unscaled_integer(field_extra):
    with pytest.raises(DecoderProfileError, match="decoder_record_view_timestamp_field_invalid"):
        _ChannelTimes_Build(
            {"sample_timestamp_us": 17000},
            view_extra={"timestamp_field": "sample_timestamp_us"},
            field_extra=field_extra,
        )
