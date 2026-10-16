"""Disabled placeholders and explicit experimental actual configuration."""

import json
import math
import struct
import zlib
from pathlib import Path

import pytest
from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameters_Resolve,
    AlgorithmParametersHeader_Render,
)
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.gnss_reacquisition import (
    CAPS,
    FIELDS,
    OWNER,
    WIRE,
    GnssReacquisitionConfiguration_Resolve,
    GnssReacquisitionDeclaration_Get,
)
from silverstar_fccg.project.reference import ReferenceProject_Create


def experimental_values():
    values = dict.fromkeys(("gnss_recovery_" + name for name in FIELDS), 0)
    synthetic = {
        "enabled": 1,
        "loss_gap_ms": 1000,
        "stable_span_ms": 120,
        "maximum_interval_ms": 100,
        "cooldown_ms": 500,
        "stable_count": 3,
        "reject_count": 2,
        "confirmation_count": 2,
        "maximum_attempts": 8,
        "uniform_scale": 2.0,
        "clock_jitter_ms": 10,
        "horizontal_acceleration_limit_mps2": 30.0,
        "vertical_acceleration_limit_mps2": 30.0,
        "closure_sigma": 3.0,
        **dict.fromkeys(CAPS, 1000000.0),
    }
    values.update({"gnss_recovery_" + name: value for name, value in synthetic.items()})
    return values


def test_wire_contract_is_exact_and_all_fields_affect_identity():
    root = Path(__file__).resolve().parents[3]
    contract = json.loads(
        (root / "contracts/navigation_gnss_reacquisition_v1.json").read_text(
            encoding="utf8"
        )
    )
    assert tuple(contract["configuration_wire"]["order"]) == FIELDS
    assert contract["configuration_wire"]["format"] == WIRE.format
    assert contract["configuration_wire"]["size"] == WIRE.size == 104
    values = experimental_values()
    config = GnssReacquisitionConfiguration_Resolve(values)
    assert config.enabled and config.identity == zlib.crc32(config.wire)
    assert struct.unpack(WIRE.format, config.wire) == tuple(
        value for _, value in config.values
    )
    for name in FIELDS:
        changed = dict(values)
        key = "gnss_recovery_" + name
        if name == "enabled":
            changed[key] = 0
        elif name == "uniform_scale":
            changed[key] = 1.9
        elif name == "maximum_interval_ms":
            changed[key] = 99
        else:
            changed[key] += 1
        candidate = GnssReacquisitionConfiguration_Resolve(changed)
        assert candidate.wire != config.wire and candidate.identity != config.identity


@pytest.mark.parametrize(
    "name,value",
    [
        ("enabled", True),
        ("enabled", 2),
        ("loss_gap_ms", 100),
        ("stable_span_ms", 0),
        ("maximum_interval_ms", 0),
        ("maximum_interval_ms", 501),
        ("cooldown_ms", 0),
        ("stable_count", 1),
        ("stable_count", 256),
        ("reject_count", 0),
        ("confirmation_count", 0),
        ("maximum_attempts", 0),
        ("maximum_attempts", 256),
        ("uniform_scale", 1.0),
        ("uniform_scale", 2.01),
        ("uniform_scale", math.nan),
        ("clock_jitter_ms", 101),
        ("clock_jitter_ms", -1),
        ("horizontal_acceleration_limit_mps2", 0.0),
        ("vertical_acceleration_limit_mps2", math.inf),
        ("closure_sigma", 0.0),
        *[(name, 0.0) for name in CAPS],
    ],
)
def test_active_incomplete_or_invalid_policy_rejected(name, value):
    values = experimental_values()
    values["gnss_recovery_" + name] = value
    with pytest.raises(ValueError):
        GnssReacquisitionConfiguration_Resolve(values)


def test_disabled_default_and_generated_actual_identity(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.strategies["estimator"] = OWNER
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    values = model.algorithm_parameters[OWNER]
    assert all(values["gnss_recovery_" + name] == 0 for name in FIELDS)
    declaration = GnssReacquisitionDeclaration_Get(model, builtin_catalog)
    assert declaration["enabled"] is False
    assert bytes.fromhex(declaration["configuration_wire_hex"]) == bytes(WIRE.size)
    assert "SYSTEM_ESKF_GNSS_RECOVERY_ENABLED 0" in AlgorithmParametersHeader_Render(
        model, builtin_catalog
    )
    values["gnss_recovery_enabled"] = 1
    with pytest.raises(ValueError, match="explicit positive"):
        AlgorithmParameters_Resolve(model, builtin_catalog)
    values.update(experimental_values())
    with pytest.raises(
        ValueError, match="end-to-end acceptance evidence is incomplete"
    ):
        GnssReacquisitionDeclaration_Get(model, builtin_catalog)
    expected = GnssReacquisitionConfiguration_Resolve(values)
    assert declaration["configuration_id"] != expected.identity
    assert f"0x{expected.identity:08X}UL" in AlgorithmParametersHeader_Render(
        model, builtin_catalog
    )
    assert builtin_catalog.Component_Get(OWNER).version == "0.4.0"
    from silverstar_fccg.generator.render import GeneratedFiles_Render
    from silverstar_fccg.project.validation import Project_Validate

    assert any(
        "end-to-end acceptance evidence is incomplete" in issue.message
        for issue in Project_Validate(model, builtin_catalog).issues
    )
    model.protocols["logging"] = None
    with pytest.raises(
        ValueError, match="end-to-end acceptance evidence is incomplete"
    ):
        GeneratedFiles_Render(model, builtin_catalog, None)
    values["gnss_recovery_enabled"] = 0
    model.component_provenance[OWNER] = {"files": {"unproven.c": "0" * 64}}
    with pytest.raises(ValueError, match="preserved provenance"):
        GnssReacquisitionDeclaration_Get(model, builtin_catalog)
