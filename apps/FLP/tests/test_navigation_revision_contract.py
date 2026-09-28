from __future__ import annotations

from dataclasses import replace

import pytest

from silverstar_flp.analysis.navigation_policy import FusionSupervisor, NavigationHealth
from silverstar_flp.decoder_profiles import DecoderProfileError, DecoderProfilePackage
from silverstar_flp.decoder_profiles.eskf15_records import Eskf15Records_Adapt
from silverstar_flp.plugins.algorithms.eskf15.plugin import Native_PhysicalMask
from tests.test_decoder_profiles import (
    _ContainerMap_Get,
    _Package_Write,
    _PackageFiles_Build,
    _SemanticsDocument_Build,
)
from tests.test_eskf15_records import _Parts


@pytest.mark.parametrize("revision", [1, 4, -1, True, "3"])
def test_unknown_or_untyped_quality_revision_is_rejected(tmp_path, revision):
    semantics = _SemanticsDocument_Build()
    semantics["metadata_declarations"] = {
        "navigation_replay": {"gnss_integrity_revision": revision},
    }
    files, _ = _PackageFiles_Build(semantics_document=semantics)
    package, _ = _Package_Write(tmp_path / "unsupported.ssdecoder", files=files)
    with pytest.raises(DecoderProfileError, match="gnss_integrity_revision_unsupported"):
        DecoderProfilePackage.Load(package, container_plugins=_ContainerMap_Get())


def test_navigation_fusion_event_keeps_group_state_reason_and_actual_fusion_age():
    event = replace(
        _Parts()[0],
        record_type=0x02,
        record_name="EVENT",
        record_version=0,
        payload={"event_id": 0x2F, "arg0": 3 | (6 << 8) | (18 << 16), "arg1": 10500},
    )
    channels, errors = Eskf15Records_Adapt({"EVENT": (event,)})
    assert not errors
    assert channels["navigation.fusion.group3.state"].values.tolist() == [6]
    assert channels["navigation.fusion.group3.reason"].values.tolist() == [18]
    assert channels["navigation.fusion.group3.age"].values.tolist() == [10500]


def test_fix4_requires_explicit_supported_and_valid_fix_ok():
    raw = dict(
        supported_fields=1023,
        valid_fields=1023,
        fix_type=4,
        fix_ok=1,
        online=1,
        velocity_valid_mask=7,
        horizontal_accuracy_m=1.0,
        vertical_accuracy_m=2.0,
        speed_accuracy_mps=0.1,
    )
    assert Native_PhysicalMask(raw) == 15
    for field in ("supported_fields", "valid_fields"):
        assert Native_PhysicalMask({**raw, field: 1021}) == 0


def test_model_mismatch_is_latched_until_explicit_new_navigation_epoch():
    supervisor = FusionSupervisor(1_000_000)
    supervisor.Decision_Record(
        0, 1_100_000, physically_valid=True, result=5, nis=0.1, gain_norm=0, evaluation_us=1_150_000
    )
    supervisor.Decision_Record(
        0, 1_200_000, physically_valid=True, result=0, nis=0.1, gain_norm=1, evaluation_us=1_250_000
    )
    assert supervisor.groups[0].last_successful_fusion_us == 1_250_000
    assert supervisor.Health_Get(1_300_000) == NavigationHealth.INVALID
    assert FusionSupervisor(1_300_000).Health_Get(1_300_001) == NavigationHealth.WARMUP


def test_source_switch_same_receive_time_is_distinct_outer_evidence():
    supervisor = FusionSupervisor(1_000_000)
    for source in (0, 1):
        assert supervisor.Decision_Record(
            0, 1_100_000, physically_valid=True, result=0, nis=0.1, gain_norm=1, source=source
        )
    assert not supervisor.Decision_Record(
        0, 1_100_000, physically_valid=True, result=0, nis=0.1, gain_norm=1, source=1
    )
    assert supervisor.groups[0].accepted == 2
