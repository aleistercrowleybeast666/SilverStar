from types import SimpleNamespace
import math
import pytest
from silverstar_flp.core.dataset import DecodedRecord
from silverstar_flp.decoder_profiles.semantic_adapter import _Events_Adapt


def decode(event_id, word, update=71, **declaration):
    package = SimpleNamespace(semantics=SimpleNamespace(raw_metadata={
        "event_catalog": {"observed": {"event_id": event_id, **declaration}} if declaration else {}}))
    record = DecodedRecord(6, "EVENT", 0, 12, 1, 12345678, 0,
                           {"event_id": event_id, "arg0": word, "arg1": update}, 20)
    return _Events_Adapt({"EVENT": (record,)}, package)["EVENT"][0]


@pytest.mark.parametrize("index", range(4))
def test_declared_rotation_preserves_hamilton_axis_and_original_words(index):
    word = (index << 30)
    event = decode(0x34, word, name="MAG_ROTATION_ADOPTED", argument_encoding="hamilton_smallest3_s10_v1")
    expected = tuple(float(axis == index) for axis in range(4))
    assert event.payload["rotation_q_wxyz"] == expected
    assert (event.timestamp_us, event.payload["arg0"], event.payload["rotation_update_id"]) == (12345678, word, 71)


def test_rotation_sign_sentinel_and_package_identity():
    encoding = dict(name="MAG_ROTATION_ESTIMATE", argument_encoding="hamilton_smallest3_s10_v1")
    negative_z = ((-511) & 0x3FF) << 20
    event = decode(0x33, negative_z, **encoding)
    assert event.payload["rotation_q_wxyz"] == pytest.approx((math.sqrt(.5), 0, 0, -math.sqrt(.5)))
    assert decode(0x33, 512, **encoding).payload["rotation_encoding_valid"] is False
    assert "rotation_q_wxyz" not in decode(0x33, negative_z).payload
    assert "rotation_q_wxyz" not in decode(0x33, negative_z, **(encoding | {"argument_encoding": "future"})).payload
    assert "rotation_q_wxyz" not in decode(0x34, negative_z, **encoding).payload


def test_quality_keeps_absent_residual_distinct_from_zero():
    declaration = dict(name="MAG_ROTATION_QUALITY", argument_encoding="mag_rotation_quality_v1")
    first = decode(0x36, 9 | (0xFFFF << 8) | (18 << 24), **declaration).payload
    assert (first["rotation_quality_code"], first["rotation_sample_count"], first["rotation_relative_residual"]) == (9, 18, None)
    assert decode(0x36, 9, **declaration).payload["rotation_relative_residual"] == 0.0


def test_display_uses_frame_and_quality_names_from_matched_dictionary():
    declared = decode(0x34, 0, name="MAG_ROTATION_ADOPTED", argument_encoding="hamilton_smallest3_s10_v1",
                      frame_from="calibrated_mag_sensor", frame_to="selected_imu_body").payload
    assert "calibrated_mag_sensor → selected_imu_body" in declared["rotation_display"]
    quality = decode(0x36, 3, name="MAG_ROTATION_QUALITY", argument_encoding="mag_rotation_quality_v1",
                     quality_codes={"3": "accepted"}).payload
    assert "3 (accepted)" in quality["rotation_display"]
