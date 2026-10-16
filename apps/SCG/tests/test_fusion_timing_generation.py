"""Timing actuals and wire records must describe the selected execution path."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from silverstar_fccg.generator.render import LogDecoderProfile_Render
from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameters_Reconcile,
    AlgorithmParameters_Resolve,
    AlgorithmParametersHeader_Render,
)
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.rate_plan import InertialRatePlan_Resolve
from silverstar_fccg.project.reference import ReferenceProject_Create


OWNERS = ("silverstar.algorithm.estimator.kf6", "silverstar.algorithm.estimator.eskf15")
APP = Path(__file__).resolve().parents[1]


def _model(catalog, owner):
    model = ReferenceProject_Create("FusionTiming", catalog=catalog)
    model.strategies["estimator"] = owner
    return ProjectConfiguration_Reconcile(model, catalog).model


@pytest.mark.parametrize("owner", OWNERS)
def test_default_and_missing_legacy_actual_remain_replay(builtin_catalog, owner):
    model = _model(builtin_catalog, owner)
    assert model.algorithm_parameters[owner]["fusion_timing_mode"] == 1
    del model.algorithm_parameters[owner]["fusion_timing_mode"]
    AlgorithmParameters_Reconcile(model, builtin_catalog)
    assert model.algorithm_parameters[owner]["fusion_timing_mode"] == 1
    header = AlgorithmParametersHeader_Render(model, builtin_catalog)
    assert "#define SYSTEM_FUSION_TIMING_MODE 1" in header


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize("mode", (0, 1))
def test_actual_declaration_and_rate_plan_agree(builtin_catalog, owner, mode):
    model = _model(builtin_catalog, owner)
    model.algorithm_parameters[owner]["fusion_timing_mode"] = mode
    package = LogDecoderProfile_Render(model, builtin_catalog)
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        semantics = json.loads(archive.read("project_semantics.json"))
    declaration = semantics["metadata_declarations"]["fusion_timing"]
    assert declaration == {
        "schema_id": "silverstar.navigation-fusion-timing/1", "revision": 1,
        "component": owner, "mode": mode,
        "source_time": "resolved_measurement_epoch",
        "application_time": "estimator_present" if mode == 0 else "legacy_algorithm_epoch",
        "evaluation_time": "estimator_present", "output_state_time": "estimator_present",
        "output_covariance_time": "estimator_present", "replays_history": mode == 1,
    }
    actual = next(x for x in semantics["firmware_algorithm_parameters"] if x["component"] == owner)
    assert next(x["value"] for x in actual["parameters"] if x["id"] == "fusion_timing_mode") == mode
    plan = InertialRatePlan_Resolve(model, builtin_catalog)
    assert plan.maximum_measurement_delay_ms == 270
    if mode == 0:
        assert (plan.replay_window_ms, plan.history_capacity,
                plan.required_history_steps, plan.maximum_replay_steps) == (0, 0, 0, 0)
    else:
        assert plan.replay_window_ms == 600
        assert plan.history_capacity > 0
        assert plan.maximum_replay_steps > 0


@pytest.mark.parametrize("owner", OWNERS)
@pytest.mark.parametrize("invalid", (-1, 3, True, 0.5, "0"))
def test_invalid_actual_never_emits_a_timing_claim(builtin_catalog, owner, invalid):
    model = _model(builtin_catalog, owner)
    model.algorithm_parameters[owner]["fusion_timing_mode"] = invalid
    with pytest.raises((TypeError, ValueError)):
        AlgorithmParameters_Resolve(model, builtin_catalog)
    with pytest.raises((TypeError, ValueError)):
        LogDecoderProfile_Render(model, builtin_catalog)


def test_ins_and_sf6_have_no_placeholder_timing_parameter(builtin_catalog):
    for owner in ("silverstar.algorithm.ins.coning2_sculling2", "silverstar.algorithm.estimator.sf6"):
        assert all(p.parameter_id != "fusion_timing_mode"
                   for p in builtin_catalog.Component_Get(owner).algorithm_parameters)


def test_only_measurement_records_advance_to_v2():
    base = APP / "plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG/schema"
    contract_path = APP.parents[1] / "contracts/navigation_fusion_timing_records_v2.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {record["name"]: record for record in contract["records"]}
    type_sizes = {"u8": 1, "u32": 4, "u64": 8, "f32": 4}
    for name in ("sslog_schema.json", "sslog_parser_metadata.json"):
        records = {r["name"]: r for r in json.loads((base / name).read_text(encoding="utf-8"))["records"]}
        assert {r["name"] for r in records.values() if r["version"] == 2} == set(expected)
        for record, authority in expected.items():
            item = records[record]
            assert (int(item["id"], 0), item["version"], item["payload_size"]) == (
                authority["record_id"], authority["record_version"], authority["payload_size"])
            offset = 0
            actual = []
            for field in item["fields"]:
                count = field.get("count", 1)
                actual.append({"name": field["name"], "type": field["type"],
                               "count": count, "offset": offset})
                offset += type_sizes[field["type"]] * count
            assert actual == authority["v1_fields"] + authority["appended_fields"]
            assert offset == authority["payload_size"]
