from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtCore import QSettings

from silverstar_flp.core.context import TaskCancelledError, TaskContext
from silverstar_flp.core.i18n import Translator
from silverstar_flp.plugins.algorithms.kf6.diagnostics import (
    DiagnosticResult_Export,
    Kf6DiagnosticOptions,
)
from silverstar_flp.plugins.algorithms.kf6.field_analysis import LatencySweep_Run
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.algorithms.pure_ins.plugin import PureInsAlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.main_window import MainWindow
from silverstar_flp.ui.pages.replay import ReplayPage
from tests.synthetic_parameter_navigation import NavigationPair_Open, SyntheticOperations_Attach
from tests.test_gui_smoke import _ProjectIdentity_Set
from tests.test_kf6_field_analysis import Measurement_Create


@pytest.fixture
def diagnostic_dataset(tmp_path):
    opened = NavigationPair_Open(tmp_path / "pair", flight_samples=401)
    base = opened.dataset
    records = []
    baro = []
    for i in range(90):
        t = base.start_timestamp_us + (i + 1) * 40000
        r = Measurement_Create(t, i + 1, (0.1, -0.1, 0.3))
        records.append(
            replace(
                r,
                valid_flags=3,
                payload={
                    **r.payload,
                    "position_usable": 1,
                    "position_enu_m": (0.2, -0.1, 2),
                    "position_variance_m2": (2.25, 2.25, 6.25),
                },
            )
        )
        baro.append(
            replace(
                r,
                record_name="BARO_MEASUREMENT",
                valid_flags=4,
                payload={
                    "sample_timestamp_us": t,
                    "receive_timestamp_us": t,
                    "sequence": i + 1,
                    "valid_mask": 1,
                    "relative_altitude_m": -0.4,
                    "variance_m2": 25.0,
                },
            )
        )
    return SyntheticOperations_Attach(replace(
        base,
        records={
            **base.records,
            "GNSS_MEASUREMENT": tuple(records),
            "BARO_MEASUREMENT": tuple(baro),
        },
    ))


def test_effective_override_real_skip_reset_and_input_immutability(diagnostic_dataset, tmp_path):
    ds = diagnostic_dataset
    plugin = Kf6AlgorithmPlugin()
    request = ReplayRequest()
    before = hashlib.sha256(ds.source_path.read_bytes()).hexdigest()
    recorded = dict(plugin.recorded_parameters(ds))
    baseline = plugin.run(ds, request)
    neutral = plugin.run(ds, request, analysis_options=Kf6DiagnosticOptions())
    np.testing.assert_array_equal(
        baseline.channels["kf6.state"].values, neutral.channels["kf6.state"].values
    )
    override = plugin.run(
        ds,
        request,
        analysis_options=Kf6DiagnosticOptions(
            baro_effective_sigma_m=2, gnss_position_vertical_disabled=True
        ),
    )
    assert override.provenance == "Analysis-only"
    assert baseline.provenance != "Analysis-only"
    groups = override.diagnostics["gnss_group_results"]
    assert sum(groups[1]) == 0 and sum(groups[0]) > 0
    assert override.diagnostics["gnss_group_nis"][1]["count"] == 0
    weights = override.diagnostics["offline_diagnostics"]["measurement_weights"]
    assert weights[4]["firmware_R"]["median"] == 25
    assert weights[4]["effective_R"]["median"] == 4
    assert weights[1]["effective_R"] is None
    attempts = override.channels["kf6.measurement_attempt_mask"].values.astype(int) & 4 != 0
    np.testing.assert_allclose(override.channels["kf6.measurement_r.baro"].values[attempts], 4)
    np.testing.assert_array_equal(
        baseline.channels["kf6.state"].values[:, [0, 1, 3, 4]],
        override.channels["kf6.state"].values[:, [0, 1, 3, 4]],
    )
    assert not np.array_equal(
        baseline.channels["kf6.state"].values[:, 2], override.channels["kf6.state"].values[:, 2]
    )
    restored = plugin.run(ds, request)
    np.testing.assert_array_equal(
        baseline.channels["kf6.state"].values, restored.channels["kf6.state"].values
    )
    assert dict(plugin.recorded_parameters(ds)) == recorded
    assert all(r.payload["variance_m2"] == 25 for r in ds.Records_Get("BARO_MEASUREMENT"))
    assert hashlib.sha256(ds.source_path.read_bytes()).hexdigest() == before
    path = tmp_path / "diagnostic.json"
    DiagnosticResult_Export(path, override.diagnostics["offline_diagnostics"])
    saved = json.loads(path.read_text())
    assert saved["diagnostic_result"]["mode"] == "analysis_only"
    assert saved["diagnostic_result"]["analysis_only_overrides"]["baro_effective_sigma_m"] == 2
    with pytest.raises(FileExistsError):
        DiagnosticResult_Export(path, {})


def test_latency_synthetic_known_shift_and_cancellation(diagnostic_dataset):
    ds = diagnostic_dataset
    pure = PureInsAlgorithmPlugin().run(ds, ReplayRequest())
    series = pure.channels["navigation.velocity_enu"]
    t = series.timestamp_us.astype(np.int64)
    records = []
    for i, stamp in enumerate(t[::4]):
        delayed = [np.interp(stamp - 80000, t, series.values[:, axis]) for axis in range(3)]
        records.append(Measurement_Create(int(stamp), i + 1, delayed))
    ds = replace(
        ds, records={**ds.records, "GNSS_MEASUREMENT": tuple(records), "BARO_MEASUREMENT": ()}
    )
    ds = SyntheticOperations_Attach(ds)
    progress = []
    context = TaskContext(progress_callback=lambda p, _: progress.append(p))
    scan = LatencySweep_Run(
        ds, ReplayRequest(), context=context, analysis_options=Kf6DiagnosticOptions()
    )
    assert abs(scan["best_shift_ms"] + 80) <= 5
    assert scan["score_best"] < scan["score_zero_ms"]
    assert progress == sorted(progress) and progress[-1] == 1
    plugin = Kf6AlgorithmPlugin()
    zero = plugin.run(ds, ReplayRequest())
    moved = plugin.run(
        ds, ReplayRequest(), analysis_options=Kf6DiagnosticOptions(velocity_shift_ms=-80)
    )
    assert not np.array_equal(zero.channels["kf6.state"].values, moved.channels["kf6.state"].values)
    context.Cancel_Request()
    with pytest.raises(TaskCancelledError):
        LatencySweep_Run(ds, ReplayRequest(), context=context)


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_replay_product_removes_legacy_diagnostics_page(qtbot, language, diagnostic_dataset):
    page = ReplayPage(Translator(language), builtin_registry())
    qtbot.addWidget(page)
    page.Dataset_Set(diagnostic_dataset)
    assert not hasattr(page, "diagnostics_panel")
    assert not hasattr(page, "tabs")
    page.algorithm_combo.setCurrentIndex(
        page.algorithm_combo.findData("silverstar.algorithm.kf6")
    )
    assert page.mode_combo.count() == 3
    assert all(page.mode_combo.itemData(index) != "integrity_assisted"
               for index in range(page.mode_combo.count()))
    request = page._Request_Get()
    assert request.mode == ReplayMode.RECORDED_CONFIGURATION
    assert page.Configuration_Get()["mode"] == ReplayMode.RECORDED_CONFIGURATION.value


def test_project_excludes_analysis_only_diagnostics(
    qtbot, monkeypatch, tmp_path, diagnostic_dataset
):
    import silverstar_flp.ui.main_window as module

    monkeypatch.setattr(
        module, "QSettings",
        lambda *a: QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    window = MainWindow(builtin_registry())
    monkeypatch.setattr(window, "_ProjectChanges_Confirm", lambda: True)
    qtbot.addWidget(window)
    window._Dataset_Set(diagnostic_dataset)
    _ProjectIdentity_Set(window, diagnostic_dataset.source_path, tmp_path)
    page = window.replay_page
    page.algorithm_combo.setCurrentIndex(
        page.algorithm_combo.findData("silverstar.algorithm.kf6")
    )
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page._parameter_widgets["gnss_position_std_vertical"].setValue(4)
    result = Kf6AlgorithmPlugin().run(
        diagnostic_dataset,
        ReplayRequest(),
        analysis_options=Kf6DiagnosticOptions(baro_effective_sigma_m=2),
    )
    window._Replay_ResultSet(result)
    assert page._ActualValues_Get()["gnss_position_std_vertical"] == 4
    project_path = tmp_path / "test.ssflp"
    window._Project_Write(project_path)
    text = project_path.read_text()
    assert "baro_effective_sigma" not in text
    assert "analysis_only" not in text
    assert len(json.loads(text)["replay_configurations"]) == 1
    assert list(tmp_path.rglob("*.ssdecoder"))
