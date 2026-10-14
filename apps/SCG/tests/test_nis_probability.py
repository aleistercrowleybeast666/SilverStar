from pathlib import Path
import json
import math
import pytest

from silverstar_fccg.core.nis_probability import (
    ChiSquareCdf_Get, ChiSquareQuantile_Get, NisInput_Create, NisInput_Resolve)

ROOT = Path(__file__).resolve().parents[3]
VECTORS = json.loads((ROOT / "contracts/nis_probability_v1.json").read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: f"df{v['df']}-p{v['probability']}")
def test_chi_square_authoritative_tail_reference(vector):
    expected = vector["threshold"]
    actual = ChiSquareQuantile_Get(vector["probability"], vector["df"])
    assert math.isclose(actual, expected, rel_tol=3e-11, abs_tol=1e-290)
    assert math.isclose(ChiSquareCdf_Get(actual, vector["df"]), vector["cdf"],
                        rel_tol=3e-11, abs_tol=3e-15)


@pytest.mark.parametrize("bad", [0.0, 1.0, -1.0, 1.01, float("nan"), float("inf"), True, None, [], {}])
def test_invalid_probability_fails_closed(bad):
    with pytest.raises(ValueError):
        ChiSquareQuantile_Get(bad, 2)


@pytest.mark.parametrize("bad", [0, -1, 257, True, 2.0, None])
def test_df_is_residual_integer_not_state_guess(bad):
    ChiSquareQuantile_Get(0.95, 1)  # Warm cache must not let bool df bypass validation.
    with pytest.raises(ValueError):
        ChiSquareQuantile_Get(0.95, bad)


def test_legacy_extreme_numeric_remains_finite_and_identical():
    value = 10000.0
    assert ChiSquareCdf_Get(value, 1) == 1.0
    assert NisInput_Resolve(value, 1) == value
    with pytest.raises(ValueError):
        NisInput_Create(1.0, 1)


def test_explicit_units_version_and_df_contract():
    value = NisInput_Create(0.95, 2)
    assert math.isclose(NisInput_Resolve(value, 2), 5.991464547107979, rel_tol=1e-12)
    for field, bad in [("unit", "percent"), ("schema_id", "unknown"), ("degrees_of_freedom", 6)]:
        corrupt = {**value, field: bad}
        with pytest.raises(ValueError):
            NisInput_Resolve(corrupt, 2)


def test_apps_share_exact_conversion_source_and_reference_vectors():
    a = ROOT / "apps/SCG/src/silverstar_fccg/core/nis_probability.py"
    b = ROOT / "apps/FLP/src/silverstar_flp/core/nis_probability.py"
    assert a.read_bytes() == b.read_bytes()


from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameters_Resolve
from silverstar_fccg.ui.nis_editor import NisProbabilityEditor

KF = "silverstar.algorithm.estimator.kf6"


def test_scg_untouched_numeric_and_edited_probability_roundtrip(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    legacy = 9.210123456789
    model.algorithm_parameters[KF]["nis_2d_soft"] = legacy
    old = model.Dictionary_Get()
    assert old["format_version"] < 18
    loaded = ProjectModel_Parse(old)
    assert loaded.algorithm_parameters[KF]["nis_2d_soft"] == legacy
    primary = NisInput_Create(0.95, 2)
    model.algorithm_parameters[KF]["nis_2d_soft"] = primary
    saved = model.Dictionary_Get()
    assert saved["format_version"] == 18
    assert ProjectModel_Parse(saved).algorithm_parameters[KF]["nis_2d_soft"] == primary
    groups = AlgorithmParameters_Resolve(model, builtin_catalog)
    actual = next(p["value"] for g in groups if g["component"] == KF
                  for p in g["parameters"] if p["id"] == "nis_2d_soft")
    assert math.isclose(actual, 5.991464547107979, rel_tol=1e-7)
    saved["format_version"] = 17
    with pytest.raises(ProjectModelError):
        ProjectModel_Parse(saved)


def test_scg_soft_hard_order_and_target_rounding(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    model.algorithm_parameters[KF]["nis_2d_soft"] = NisInput_Create(0.9999, 2)
    model.algorithm_parameters[KF]["nis_2d_hard"] = NisInput_Create(0.95, 2)
    with pytest.raises(ValueError):
        AlgorithmParameters_Resolve(model, builtin_catalog)


def test_scg_extreme_numeric_display_is_not_a_disable_switch(qapp):
    widget = NisProbabilityEditor(1, 0.001, 10000.0, "en_US")
    widget.setValue(10000.0)
    assert widget.percent.value() == 100.0
    assert widget.Input_Get() == 10000.0
    assert widget.value() == 10000.0
    widget._Probability_Change(100.0)
    assert not widget.InputValid_Is()
    with pytest.raises(ValueError):
        widget.Input_Get()


import hashlib
from silverstar_fccg.generator.kf6_identity import (
    ESKF_COMPONENT, ESKF_NIS_PATHS, EskfNisIdentity_Validate)


def test_eskf_gate_contract_preserves_user_source_and_requires_fresh_upgrade(tmp_path):
    current={"files": {}}
    for relative in ESKF_NIS_PATHS:
        p=tmp_path/relative
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(b"owned current source\n")
        current["files"][relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    previous={"components": {ESKF_COMPONENT: current}}
    EskfNisIdentity_Validate(tmp_path,previous,current)
    edited=tmp_path/ESKF_NIS_PATHS[0]
    edited.write_bytes(b"user edited header\n")
    before=edited.read_bytes()
    with pytest.raises(ValueError,match="NOT PROVEN"):
        EskfNisIdentity_Validate(tmp_path,previous,current)
    assert edited.read_bytes()==before
    with pytest.raises(ValueError,match="without ownership"):
        EskfNisIdentity_Validate(tmp_path,{},current)
    # A new upstream contract cannot be used to label preserved old source.
    changed={"files": {**current["files"], ESKF_NIS_PATHS[-1]: "0"*64}}
    edited.write_bytes(b"owned current source\n")
    with pytest.raises(ValueError,match="fresh separately named"):
        EskfNisIdentity_Validate(tmp_path,previous,changed)


def test_scg_rejects_invalid_primary_units_df_and_rounded_equal_pair(builtin_catalog):
    model=ReferenceProject_Create(catalog=builtin_catalog)
    for change in [{"unit":"percent"},{"schema_id":"unknown"},{"degrees_of_freedom":6},
                   {"probability":1.0},{"probability":float("nan")}]:
        model.algorithm_parameters[KF]["nis_2d_soft"]={**NisInput_Create(.95,2),**change}
        with pytest.raises(ValueError):
            AlgorithmParameters_Resolve(model,builtin_catalog)
    model.algorithm_parameters[KF]["nis_2d_soft"]=NisInput_Create(.95,2)
    model.algorithm_parameters[KF]["nis_2d_hard"]=NisInput_Create(.95+1e-10,2)
    with pytest.raises(ValueError,match="target precision"):
        AlgorithmParameters_Resolve(model,builtin_catalog)


def test_scg_readout_is_the_actual_float32_while_legacy_input_is_preserved(qapp):
    import struct
    widget=NisProbabilityEditor(1,.001,10000.,"en_US")
    widget.setValue(6.635)
    assert widget.Input_Get()==6.635
    actual=struct.unpack("<f",struct.pack("<f",6.635))[0]
    assert f"{actual:.9g}" in widget.readout.text()


def test_scg_flp_same_probability_produces_identical_target_bits(builtin_catalog,qapp,monkeypatch):
    import struct
    monkeypatch.syspath_prepend(str(ROOT/"apps/FLP/src"))
    from silverstar_flp.ui.nis_editor import NisProbabilityEditor as FlpNisEditor
    definitions={p.parameter_id:p for p in builtin_catalog.Component_Get(KF).algorithm_parameters}
    for df in (1,2,3):
        definition=definitions[f"nis_{df}d_soft"]
        for probability in (.95,.99,.999,1.-1e-10):
            primary=NisInput_Create(probability,df)
            expected=definition.Value_Resolve(primary)
            scg=NisProbabilityEditor(df,.001,10000.,"en_US")
            flp=FlpNisEditor(df,.001,10000.,"en_US")
            scg.setValue(primary)
            flp.setValue(primary)
            assert struct.pack("<f",scg.value())==struct.pack("<f",flp.value())==struct.pack("<f",expected)
            assert scg.Input_Get()==flp.Input_Get()==primary
