"""Real ESKF plugin, selected-source GUI, bias plots and independent export."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from silverstar_flp.core.analysis_source import ChannelResolver, ReplayResultStore
from silverstar_flp.core.context import TaskCancelledError, TaskContext
from silverstar_flp.core.i18n import Translator
from silverstar_flp.export.service import ExportLanguage, ExportOptions, FlightExporter
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.ui.pages.state_estimation import StateEstimationPage
from silverstar_flp.ui.theme import Theme_Apply
from tests.synthetic_parameter_navigation import NavigationPair_Open


def test_real_eskf_bias_gui_and_frozen_explicit_export(qtbot, tmp_path):
    dataset = NavigationPair_Open(tmp_path / "input", flight_samples=201).dataset
    registry = builtin_registry()
    plugin = registry.Algorithm_Get("silverstar.algorithm.estimator.eskf15")
    result = plugin.run(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF))
    assert result.fidelity == ReplayFidelity.APPROXIMATE
    assert not result.missing_inputs
    assert result.channels["eskf15.covariance.diagonal"].values.shape[1] == 15
    assert result.channels["eskf15.covariance.upper_triangle"].values.shape[1] == 120
    store = ReplayResultStore()
    entry = store.Result_Add(result, algorithm_name="ESKF_15")
    assert store.ActiveSource_Set(entry.source_id)
    application = QApplication.instance()
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    if font_id >= 0:
        application.setFont(QFont(QFontDatabase.applicationFontFamilies(font_id)[0], 10))
    page = StateEstimationPage(Translator("en_US"), registry)
    qtbot.addWidget(page)
    page.Dataset_Set(dataset, ChannelResolver(dataset, store))
    page.resize(1000, 700)
    page.show()
    assert page.state_group_combo.count() == 5
    assert page.nis_measurement_combo.count() == 5
    page.state_group_combo.setCurrentIndex(page.state_group_combo.findData("gyro_bias"))
    application.processEvents()
    assert len(page.state_estimate_plot.listDataItems()) == 3
    assert len(page.covariance_plot.listDataItems()) == 3
    assert page.navigation_health_label.text()
    for theme in ("light", "dark"):
        Theme_Apply(application, theme)
        page.Theme_Apply(theme)
        for language in ("en_US", "zh_CN"):
            page.Language_Apply(Translator(language))
            application.processEvents()
            assert page.grab().save(str(tmp_path / f"eskf15_bias_{theme}_{language}.png"))
    # Export an explicit ESKF run while the live UI selection remains recorded.
    store.ActiveSource_Set(ReplayResultStore.RECORDED_SOURCE_ID)
    switched = []

    def SwitchDuringExport(progress, _code):
        if progress > 0 and not switched:
            store.ActiveSource_Set(entry.source_id)
            page.Dataset_Set(dataset, ChannelResolver(dataset, store))
            switched.append(progress)

    manifest = FlightExporter(registry).export(
        dataset,
        tmp_path / "export",
        replay_store=store,
        context=TaskContext(progress_callback=SwitchDuringExport),
        options=ExportOptions(
            source_mode="explicit",
            source_id=entry.source_id,
            language=ExportLanguage.EN,
            include_overview=False,
            include_diagnostics=False,
            include_events=False,
            include_csv=True,
            include_plots=True,
            include_full_covariance_keyframes=False,
            include_trajectory_3d=False,
            include_attitude_gif=False,
        ),
    )
    assert not manifest.failures
    assert switched and store.ActiveSource_Get().source_id == entry.source_id
    names = [path.name for path in manifest.files]
    assert any("Gyro_Bias_Estimate" in name for name in names)
    assert any("Accel_Bias_Estimate" in name for name in names)
    assert any("Gyro_Bias_Std_1Sigma" in name for name in names)
    audit = json.loads(manifest.ManifestPath_Get().read_text(encoding="utf8"))
    assert audit["replay_results"][0]["algorithm_id"] == plugin.metadata.plugin_id
    selected = tuple(
        name
        for name in FlightExporter._SourceChannels_Get(ChannelResolver(dataset, store))
        if " / " in name and name.endswith(("navigation.position_enu", "navigation.velocity_enu"))
    )
    assert len(selected) == 2
    options = ExportOptions(
        source_mode="explicit",
        source_id=entry.source_id,
        selected_channels=selected,
        include_overview=False,
        include_diagnostics=False,
        include_events=False,
        include_csv=True,
        include_plots=False,
        include_full_covariance_keyframes=False,
        include_trajectory_3d=False,
        include_attitude_gif=False,
    )
    cancelled = TaskContext()

    def CancelDuringExport(progress, _code):
        if progress > 0:
            cancelled.Cancel_Request()

    cancelled.progress_callback = CancelDuringExport
    with pytest.raises(TaskCancelledError):
        FlightExporter(registry).export(
            dataset, tmp_path / "cancelled", replay_store=store, options=options, context=cancelled
        )
    resumed = FlightExporter(registry).export(
        dataset,
        tmp_path / "restarted",
        replay_store=store,
        options=replace(options, language=ExportLanguage.ZH),
        context=TaskContext(),
    )
    assert not resumed.failures
    assert len([p for p in resumed.files if p.suffix == ".csv"]) == 2
    assert all(p.parent.name == "CSV_ZH" for p in resumed.files if p.suffix == ".csv")
    page.close()
