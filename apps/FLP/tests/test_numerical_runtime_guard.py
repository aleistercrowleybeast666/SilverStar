"""Known bad runtime must fail before GUI construction, parsing or numerical replay."""

import pytest
from silverstar_flp.core import runtime
from silverstar_flp.plugins.api.algorithm import ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry


@pytest.mark.parametrize("version", ["2.4.0", "2.4.0+local"])
def test_bad_numpy_release_rejected_with_interpreter_and_remedy(monkeypatch, version):
    monkeypatch.setattr(runtime.np, "__version__", version)
    with pytest.raises(RuntimeError, match="numpy_version_unsafe") as caught:
        runtime.NumericalRuntime_Validate()
    assert "2.4.1" in str(caught.value) and "Python:" in str(caught.value)


@pytest.mark.parametrize("version", ["2.0.0", "2.3.5", "2.4.1", "2.5.3"])
def test_unaffected_supported_release_is_allowed(monkeypatch, version):
    monkeypatch.setattr(runtime.np, "__version__", version)
    runtime.NumericalRuntime_Validate()


@pytest.mark.parametrize(
    "algorithm", ["silverstar.algorithm.kf6", "silverstar.algorithm.estimator.eskf15"]
)
def test_direct_replay_rejects_bad_runtime_before_accessing_dataset(monkeypatch, algorithm):
    monkeypatch.setattr(runtime.np, "__version__", "2.4.0")
    with pytest.raises(RuntimeError, match="numpy_version_unsafe"):
        builtin_registry().Algorithm_Get(algorithm).run(None, ReplayRequest())


def test_gui_rejects_bad_runtime_before_qapplication(monkeypatch, capsys):
    from silverstar_flp.app.application import main

    monkeypatch.setattr(runtime.np, "__version__", "2.4.0")
    assert main([]) == 2
    assert "numpy_version_unsafe" in capsys.readouterr().err


def test_cli_rejects_bad_runtime_before_opening_input(monkeypatch, capsys):
    from silverstar_flp.cli import main

    monkeypatch.setattr(runtime.np, "__version__", "2.4.0")
    assert main(["inspect", "missing.sslog", "--auto-find"]) == 2
    assert "numpy_version_unsafe" in capsys.readouterr().err
