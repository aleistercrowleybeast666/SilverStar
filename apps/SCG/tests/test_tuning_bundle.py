"""Cross-product strict transaction and generated-C consumer regression."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from silverstar_fccg.project.algorithm_parameters import AlgorithmParametersHeader_Render
from silverstar_fccg.project.function_parameters import ParameterProfileError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.tuning_bundle import (
    TuningBundle_Apply, TuningBundle_ControlHeaderRender, TuningBundle_Digest,
    TuningBundle_Preview, TuningBundle_Read, TuningBundle_Validate,
)


FIXTURES = Path(__file__).parent / "fixtures/tuning_bundle_v1"


def test_real_treediagram_bundle_preview_apply_to_generated_owner(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    before = deepcopy(model.Dictionary_Get())
    bundle = TuningBundle_Read(FIXTURES / "kf6-pid.sstuning.json")
    preview = TuningBundle_Preview(model, builtin_catalog, bundle)
    assert not preview["control_deployable"]
    assert any(row["shared"] and row["parameter_id"] == "gravity_mps2" for row in preview["changes"])
    assert model.Dictionary_Get() == before
    candidate = TuningBundle_Apply(model, builtin_catalog, bundle)
    assert model.Dictionary_Get() == before
    header = AlgorithmParametersHeader_Render(candidate, builtin_catalog)
    assert "SYSTEM_INS_GRAVITY_MPS2 9.806650162e+00f" in header
    assert "SYSTEM_KF_GRAVITY_MPS2 9.806650162e+00f" in header


@pytest.mark.parametrize("case", ["identity", "unknown", "bool", "shared", "deployable", "digest"])
def test_bundle_bad_contract_never_partially_applies(builtin_catalog, case):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    before = deepcopy(model.Dictionary_Get())
    bundle = TuningBundle_Read(FIXTURES / "kf6-pid.sstuning.json")
    if case == "identity":
        bundle["profiles"][-1]["manifest_sha256"] = "0"*64
    elif case == "unknown":
        bundle["profiles"][-1]["parameters"][0]["unknown"] = 1
    elif case == "bool":
        bundle["profiles"][-1]["parameters"][0]["value"] = True
    elif case == "shared":
        next(row for row in bundle["profiles"][-1]["parameters"] if row["id"] == "gravity_mps2")["value"] = 9.7
    elif case == "deployable":
        bundle["control_research"]["deployable"] = True
    if case != "digest":
        bundle["content_sha256"] = TuningBundle_Digest(bundle)
    else:
        bundle["run_id"] = "changed"
    with pytest.raises(ValueError):
        TuningBundle_Apply(model, builtin_catalog, bundle)
    assert model.Dictionary_Get() == before


def test_bundle_strict_duplicate_and_size(tmp_path):
    path = tmp_path / "bad.sstuning.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ParameterProfileError, match="duplicate"):
        TuningBundle_Read(path)
    path.write_text(" "*1048577, encoding="utf-8")
    with pytest.raises(ParameterProfileError, match="size"):
        TuningBundle_Read(path)


def test_lqr_shape_and_gain_identity():
    bundle = TuningBundle_Read(FIXTURES / "kf6-lqr.sstuning.json")
    bundle["control_research"]["design"]["k"][0][0] += 1
    bundle["content_sha256"] = TuningBundle_Digest(bundle)
    with pytest.raises(ParameterProfileError, match="gain_mismatch"):
        TuningBundle_Validate(bundle)


def test_lqr_forged_stability_summary_is_recomputed():
    bundle = TuningBundle_Read(FIXTURES / "kf6-lqr.sstuning.json")
    bundle["control_research"]["design"]["a"][0][0] = 10
    bundle["content_sha256"] = TuningBundle_Digest(bundle)
    with pytest.raises(ParameterProfileError, match="closed_loop"):
        TuningBundle_Validate(bundle)


@pytest.mark.parametrize("kind", ["pid", "lqr"])
def test_generated_research_config_consumed_by_actual_c(tmp_path, workspace_root, kind):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Actual C compiler unavailable")
    bundle = TuningBundle_Read(FIXTURES / f"kf6-{kind}.sstuning.json")
    (tmp_path / "project_control_research.h").write_text(TuningBundle_ControlHeaderRender(bundle), encoding="utf-8")
    if kind == "pid":
        body = "ControlPidConfig config = ProjectControl_PidConfigGet(); ControlPidContext state; float output; if (ControlPid_Start(&state,&config)!=CONTROL_PID_OK) return 1; if(ControlPid_Step(&state,&config,0.01f,0.0f,config.sample_period_s,&output)!=CONTROL_PID_OK) return 2; printf(\"%.9g %.9g\\n\",(double)config.kp,(double)output);"
    else:
        body = "ControlLqrConfig config = ProjectControl_LqrConfigGet(); float error[2]={0.01f,0.02f},output; if(ControlLqr_Step(&config,error,&output)!=CONTROL_LQR_OK) return 1; printf(\"%.9g %.9g\\n\",(double)config.gain[0],(double)output);"
    source = tmp_path / "consumer.c"
    source.write_text('#include <stdio.h>\n#include "project_control_research.h"\nint main(void){'+body+'return 0;}\n', encoding="utf-8")
    root = workspace_root / f"plugins/builtin/silverstar_algorithm_control_{kind}/payload/Algorithm/Control/{kind.upper()}"
    binary = tmp_path / "consumer.exe"
    command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2", "-fanalyzer",
        "-I"+str(root/"Inc"), "-I"+str(tmp_path), str(root/f"Src/control_{kind}.c"), str(source), "-lm", "-o", str(binary)]
    result = subprocess.run(command,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(binary)],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    actual, output = map(float,result.stdout.split())
    parameters = bundle["control_research"]["parameters"]
    if kind == "pid":
        assert actual == parameters["kp"] == 3.25
        assert output == pytest.approx(parameters["kp"]*.01+parameters["ki"]*.01*parameters["sample_period_s"], abs=1e-7)
    else:
        assert actual == pytest.approx(parameters["k_angle"], abs=1e-7)
        assert output == pytest.approx(-parameters["k_angle"]*.01-parameters["k_rate"]*.02, abs=1e-7)
