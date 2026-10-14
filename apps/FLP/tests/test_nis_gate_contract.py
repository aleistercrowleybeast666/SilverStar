from pathlib import Path
import ctypes as ct
import json
import os
import shutil
import subprocess
import numpy as np
import pytest
from tests.eskf15_c_bridge import CCore
from silverstar_flp.plugins.algorithms.eskf15.filter import EskfState, Eskf15Filter

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def actual_eskf_library(tmp_path_factory):
    directory = tmp_path_factory.mktemp("nis-gates-c")
    source = Path(os.environ.get("SILVERSTAR_NIS_ESKF_BASELINE", ROOT / "apps/SCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15"))
    common = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Common"
    compiler = shutil.which("gcc")
    assert compiler, "Actual Host GCC is required for this gate test"
    dll = directory / "nis-gates.dll"
    command = [compiler, "-shared", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static-libgcc",
               "-I" + str(source / "Inc"), "-I" + str(common / "Inc"),
               str(source / "Src/navigation_eskf.c"), str(common / "Src/silverstar_assert.c"),
               "-lm", "-o", str(dll)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (directory / "compile.json").write_text(json.dumps({"command":command,"exit_code":result.returncode,"output":result.stdout+result.stderr},indent=2),encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return ct.CDLL(str(dll))


@pytest.mark.parametrize("mask,z,expected", [(0,4.,1),(1,4.,0),(0,10.,2),(2,10.,1),(3,10.,0)])
def test_explicit_switches_match_actual_c_without_infinite_thresholds(actual_eskf_library, mask,z,expected):
    state = EskfState(covariance=np.eye(15))
    c = CCore(actual_eskf_library, state)
    c.config.nis_disabled_mask = mask
    before = bytes(c.state)
    result,outcome = c.Update(1,[z],[1.],np.zeros(3),np.zeros(3))
    python = Eskf15Filter(state)
    reference = python.Measurement_Apply("position",(2,),np.array([z]),np.array([1.]),
        soft=6.635,hard=10.828,max_scale=4.,soft_enabled=not bool(mask&1),hard_enabled=not bool(mask&2))
    assert result == expected
    assert int(reference.result) == expected
    # C ESKF preserves its existing post-soft innovation solve/reporting stage;
    # Python retains the original gate-input NIS. Neither is dimension-normalized.
    assert math_isclose(reference.nis,z*z/2.)
    expected_report = z*z/(1.+float(outcome.variance[0])) if expected != 2 else z*z/2.
    assert math_isclose(outcome.nis,expected_report)
    if expected == 2:
        assert bytes(c.state) == before
    assert c.config.soft[0] > 0 and np.isfinite(c.config.hard[0])


def math_isclose(a,b):
    return abs(a-b) <= max(1e-6,abs(b)*1e-6)


@pytest.mark.parametrize("mask,observation",[(3,float("nan")),(4,4.)])
def test_disable_never_bypasses_invalid_input_or_invalid_mask(actual_eskf_library,mask,observation):
    c = CCore(actual_eskf_library,EskfState(covariance=np.eye(15)))
    c.config.nis_disabled_mask=mask
    before=bytes(c.state)
    result,_=c.Update(1,[observation],[1.],np.zeros(3),np.zeros(3))
    assert result == 3
    assert bytes(c.state) == before


def test_original_eskf_hard_equality_remains_strict_greater(actual_eskf_library):
    c=CCore(actual_eskf_library,EskfState(covariance=np.eye(15)))
    c.config.soft[0],c.config.hard[0]=6.,8.
    result,outcome=c.Update(1,[4.],[1.],np.zeros(3),np.zeros(3))
    assert result == 1  # Gate-input NIS == hard (8) is not rejected.
    assert math_isclose(outcome.nis, 16./(1.+8./6.))
