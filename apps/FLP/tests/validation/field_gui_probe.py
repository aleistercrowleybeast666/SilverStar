"""Local synthetic-only native Qt evidence. Never connects serial or opens user logs.

Run from the worktree: python .../field_gui_probe.py flp|gshc OUTPUT_DIRECTORY
Screenshots include only this process's windows. Default platform is Windows.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
ROOT = Path(__file__).resolve().parents[4]
APP_NAME = sys.argv[1]
OUTPUT = Path(sys.argv[2]).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
WIDTH = int(sys.argv[3]) if len(sys.argv) > 3 else 1280
HEIGHTS = (int(sys.argv[4]),) if len(sys.argv) > 4 else (720, 900)
app_root = ROOT / "apps" / APP_NAME.upper()
sys.path[:0] = [str(app_root / "src"), str(app_root)]

import numpy as np
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

app = QApplication([])
app.setFont(QFont("Microsoft YaHei", 9))
observations = []


def pump():
    # Bounded, test-process event processing; does not drive other Windows apps.
    limit = time.monotonic() + .3
    while time.monotonic() < limit:
        app.processEvents()
        time.sleep(.01)


def capture(window, name):
    pump()
    qt_path = OUTPUT / (name + "_qt.png")
    assert window.grab().save(str(qt_path))
    observations.append({"name": name, "requested_window": [WIDTH, int(name.split("_")[-1])],
                         "actual_window": [window.width(), window.height()],
                         "native_capture": False, "qt_capture": str(qt_path),
                         "native_capture_limitation": "QScreen capture includes occluding windows; sky capture tool not exposed"})


if APP_NAME == "gshc":
    from services.i18n import I18n
    from services.preferences import Theme
    from services.state_model import FlightControllerState, EventHistory, FlightEvent
    from protocol.common import AirStatusId
    from ui.main_window import MainWindow
    from processing.flight_log_processor import FlightData, TimedVector
    from processing.flight_plotter import FlightPlotter, PlotterConfig

    settings = QSettings(str(OUTPUT / "gshc.ini"), QSettings.Format.IniFormat)
    window = MainWindow(I18n(settings))
    state, events = FlightControllerState(), EventHistory()
    state.mission_first_time_ms = 1000
    window.bind_runtime_model(state, events)
    window.show()
    for language, theme in (("en_US", "light"), ("zh_CN", "dark")):
        window.i18n.set_language(language)
        window._apply_theme(Theme(theme), persist=True)
        window.retranslate_ui()
        for height in HEIGHTS:
            window.resize(WIDTH, height)
            window.pages.setCurrentWidget(window.horizontal_trajectory_widget)
            state.live_plot.clear()
            state.horizontal_trajectory.Clear()
            window.refresh_plots()
            capture(window, f"GSHC_empty_{language}_{height}")
            for index in range(51):
                t = index * .2
                state.live_plot.append(t, (0, 0, 0), (100*np.sin(t/4), 10*t, 50*np.sin(t/5)))
                state.horizontal_trajectory.Sample_Append(
                    1 + t, (100*np.sin(t/4), 10*t, 50*np.sin(t/5)))
                if index == 20:
                    state.horizontal_trajectory.Deploy_Observe(5)
                    events.append(FlightEvent(1, int(AirStatusId.PARACHUTE_DEPLOY),
                                             "PARACHUTE_DEPLOY", 5000, 0, 0, 0))
                if index % 5 == 0:
                    window.refresh_plots()
                    app.processEvents()
            capture(window, f"GSHC_horizontal_{language}_{height}")
            assert len(window.plot_widgets) == 6
            window.pages.setCurrentWidget(window.flight_page)
            capture(window, f"GSHC_six_curves_{language}_{height}")
        data = FlightData(0, None, 4000, 10000, OUTPUT / "SYNTHETIC_ONLY.jsonl")
        data.pos = [TimedVector(t, (100*np.sin(t/4), 10*t, 50*np.sin(t/5)), round(t*1000))
                    for t in np.arange(0, 10.01, .2)]
        plotter = FlightPlotter(PlotterConfig(language=window.i18n.language, theme=window.theme))
        plotter.page_range = (2, 8)
        plotter.plot_horizontal_trajectory(OUTPUT / f"GSHC_horizontal_export_{language}.png", data)
    window.close()
    reopened = MainWindow(I18n(settings))
    assert reopened.i18n.language.value == "zh_CN" and reopened.theme.value == "dark"
    reopened.close()
    observations.append({"gshc_preference_reopen": True})
else:
    from silverstar_flp.core.project import ProjectDocument, Project_Load
    from silverstar_flp.core.path_preferences import PathPreferences
    from silverstar_flp.plugins.container_packages import TrustedContainerPluginManager
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.plugins.api.algorithm import ReplayRequest, ReplayMode
    from silverstar_flp.core.dataset import TimeSeries
    from silverstar_flp.ui.main_window import MainWindow
    from silverstar_flp.export.service import FlightExporter, ExportOptions
    from tests.synthetic_parameter_navigation import NavigationPair_Open

    settings = QSettings(str(OUTPUT / "flp.ini"), QSettings.Format.IniFormat)
    pair = NavigationPair_Open(OUTPUT / "SYNTHETIC_pair", flight_samples=1001)
    registry = builtin_registry()
    with patch("silverstar_flp.ui.main_window.QSettings", return_value=settings):
        window = MainWindow(registry, path_preferences=PathPreferences(OUTPUT / "paths.json"),
                            plugin_manager=TrustedContainerPluginManager(OUTPUT / "plugins"))
    window._LogOpenResult_Set(pair, ProjectDocument())
    page = window.replay_page
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.sf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    page._parameter_widgets["gain_ve"].setValue(.4)
    configuration = page.Configuration_Get()
    plugin = registry.Algorithm_Get("silverstar.algorithm.sf6")
    result = plugin.run(pair.dataset, ReplayRequest(mode=ReplayMode.WHAT_IF,
                                                   parameters=configuration["actual_values"]))
    window._Replay_ResultSet(result)
    entry = window._replay_store.Entries_Get()[-1]
    window._AnalysisSource_Set(entry.source_id)
    window.show()
    for language, theme in (("en_US", "light"), ("zh_CN", "dark")):
        window.Language_Apply(language)
        window.Theme_Apply(theme)
        for height in HEIGHTS:
            window.resize(WIDTH, height)
            window.navigation_list.setCurrentRow(2)
            window.flight_page.tabs.setCurrentWidget(window.flight_page.horizontal_trajectory_widget)
            window.flight_page.TimeRange_Set(3_000_000, 9_000_000)
            capture(window, f"FLP_horizontal_{language}_{height}")
            window.flight_page.horizontal_trajectory_widget.Trajectory_Set(
                __import__("silverstar_flp.core.horizontal_trajectory", fromlist=["HorizontalTrajectory_Build"])
                .HorizontalTrajectory_Build([], []))
            capture(window, f"FLP_empty_{language}_{height}")
            window.flight_page._HorizontalTrajectory_Refresh()
            window.flight_page.tabs.setCurrentIndex(5)
            capture(window, f"FLP_preserved_3d_{language}_{height}")
            window.navigation_list.setCurrentRow(1)
            page.parameter_group_combo.setCurrentIndex(
                page.parameter_group_combo.findData("parameter_group.sf6_gain"))
            capture(window, f"FLP_SF6_parameters_{language}_{height}")
            page.scroll_area.ensureWidgetVisible(page._parameter_widgets["gain_pu"])
            capture(window, f"FLP_SF6_gains_scrolled_{language}_{height}")
            page.scroll_area.verticalScrollBar().setValue(0)
        manifest = FlightExporter().export(pair.dataset, OUTPUT / f"FLP_export_{language}",
            replay_store=window._replay_store, options=ExportOptions(language=language, ui_theme=theme,
                page_mode="Current View", current_range=(2, 8),
                include_full_covariance_keyframes=False, include_attitude_gif=False,
                include_trajectory_3d=False))
        assert not manifest.failures, manifest.failures
    window._project.project_path = OUTPUT / "SF6_what_if.ssflp"
    window._Project_Write(window._project.project_path)
    loaded = Project_Load(window._project.project_path)
    window._Project_SetDirty(False)
    window.close()
    with patch("silverstar_flp.ui.main_window.QSettings", return_value=settings):
        reopened = MainWindow(registry, path_preferences=PathPreferences(OUTPUT / "paths.json"),
                              plugin_manager=TrustedContainerPluginManager(OUTPUT / "plugins"))
    reopened._LogOpenResult_Set(pair, loaded)
    reopened._AnalysisSource_Restore()
    deadline = time.monotonic() + 20
    while reopened._active_worker is not None and time.monotonic() < deadline:
        pump()
    assert reopened._active_worker is None
    assert reopened._replay_store.ActiveSource_Get().algorithm_id == "silverstar.algorithm.sf6"
    restored = reopened.replay_page.Configuration_Get()
    assert restored["algorithm_id"] == "silverstar.algorithm.sf6"
    assert restored["actual_values"]["gain_ve"] == .4
    assert plugin.run(pair.dataset, ReplayRequest(mode=restored["mode"],
                         parameters=restored["actual_values"])).fidelity.value == "APPROXIMATE"
    reopened._Project_SetDirty(False)
    reopened.close()
    observations.append({"flp_sf6_project_reopen": True,
                         "saved_configuration": restored})

report = {"qt_platform": app.platformName(), "observations": observations,
          "scope": "synthetic inputs only; actual native Qt windows; no hardware qualification",
          "computer_use_tool": "skill read; node_repl/sky entry point not exposed in this runtime",
          "artifact_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in OUTPUT.glob("*.png")}}
(OUTPUT / "gui_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
app.quit()
