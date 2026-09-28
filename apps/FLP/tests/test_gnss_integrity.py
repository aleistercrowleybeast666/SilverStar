from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from silverstar_flp.analysis.geodesy import GeoLocal_ToEnu
from silverstar_flp.analysis.gnss_integrity_stream import GnssIntegrityStream_Build
from silverstar_flp.analysis.gnss_vertical_consistency import GnssVerticalConsistency_Build
from silverstar_flp.core.dataset import DecodedRecord, FlightDataset
from silverstar_flp.core.diagnostics import ParserDiagnostics
from silverstar_flp.export.service import ExportLanguage, ExportTheme, FlightExporter


def Dataset_Build(
    *, velocity_e=1.0, position_e_rate=1.0, noise=False,
    gap=False, invalid_pos_u=False, invalid_vel_en=False, position_usable=1,
    invalid_pos_en_range=None,
):
    origin = dict(gnss_origin_latitude_e7=0, gnss_origin_longitude_e7=0,
                  gnss_origin_height_mm=0, origin_valid_flags=1)
    initial = DecodedRecord(0, "INITIAL_STATE", 1, 0, 0, 0, 0, origin, 0)
    east_per_e7 = GeoLocal_ToEnu(
        np.array([0]), np.array([1]), np.array([0]), (0, 0, 0)
    )[0, 0]
    native = []
    for index in range(501):
        if gap and 225 <= index <= 240:
            continue
        t = index * 40_000
        east = position_e_rate * (t * 1e-6)
        if noise and index == 300:
            east += 4.0
        payload = dict(
            source_descriptor_id=1, instance_id=0,
            sample_timestamp_us=t, sequence=index,
            latitude_e7=0, longitude_e7=round(east / east_per_e7),
            ellipsoid_height_mm=0, velocity_enu_mps=(velocity_e, 0.0, 0.0),
            valid_group_mask=(0x0F & (~2 if invalid_pos_u else 0x0F)
                              & (~4 if invalid_vel_en else 0x0F)
                              & (~1 if invalid_pos_en_range is not None
                                 and invalid_pos_en_range[0] <= index <= invalid_pos_en_range[1]
                                 else 0x0F)),
            velocity_valid_mask=7, position_usable=position_usable,
            measurement_timestamp_trusted=1,
            horizontal_accuracy_m=1.0, vertical_accuracy_m=2.0,
            speed_accuracy_mps=.1, satellite_count=15,
        )
        native.append(DecodedRecord(0, "GNSS_NATIVE", 1, 0, index + 1,
                                    t, 0, payload, 0))
    return FlightDataset(
        Path("synthetic.bin"), 0, {}, ParserDiagnostics(),
        {"INITIAL_STATE": (initial,), "GNSS_NATIVE": tuple(native)}, {},
    )



def test_horizontal_and_vertical_native_consistency_have_independent_evidence():
    dataset = Dataset_Build()
    horizontal = GnssIntegrityStream_Build(dataset)
    vertical = GnssVerticalConsistency_Build(dataset)
    assert np.nanmax(horizontal.closure_norm_m) < .03
    assert np.nanmax(np.abs(vertical.error_m)) < 1e-6
    assert vertical.chain_reset.sum() == 1


def test_vertical_signed_error_and_short_position_loss_preserve_reference():
    dataset = Dataset_Build()
    native = []
    for record in dataset.Records_Get("GNSS_NATIVE"):
        index = int(record.payload["sequence"])
        payload = dict(record.payload)
        payload["ellipsoid_height_mm"] = round(index * 40 + (1000 if index >= 300 else 0))
        payload["velocity_enu_mps"] = (1.0, 0.0, 1.0)
        if 275 <= index <= 281:
            payload["valid_group_mask"] &= ~2
        native.append(replace(record, payload=payload))
    dataset = replace(dataset, records={**dataset.records, "GNSS_NATIVE": tuple(native)})
    result = GnssVerticalConsistency_Build(dataset)
    assert np.isnan(result.error_m[277])
    assert result.chain_reset.sum() == 1
    assert result.error_m[282] == pytest.approx(0, abs=.002)
    assert result.error_m[350] == pytest.approx(1.0, abs=.002)


def test_vertical_velocity_chain_gap_resets_reference_without_changing_horizontal():
    dataset = Dataset_Build(gap=True)
    vertical = GnssVerticalConsistency_Build(dataset)
    horizontal = GnssIntegrityStream_Build(dataset)
    assert vertical.chain_reset.sum() == 2
    assert np.isfinite(vertical.error_m[-1])
    assert horizontal.chain_reset.sum() == 1
    assert np.nanmax(np.abs(vertical.error_m)) < 1e-6


def test_invalid_origin_is_rejected_by_both_diagnostics():
    dataset = Dataset_Build()
    invalid = replace(dataset.initial_state, payload={
        **dataset.initial_state.payload, "origin_valid_flags": 0,
    })
    dataset = replace(dataset, records={**dataset.records, "INITIAL_STATE": (invalid,)})
    with pytest.raises(ValueError, match="gnss_origin_unavailable"):
        GnssIntegrityStream_Build(dataset)
    with pytest.raises(ValueError, match="gnss_origin_unavailable"):
        GnssVerticalConsistency_Build(dataset)


@pytest.mark.parametrize("language", (ExportLanguage.EN, ExportLanguage.ZH))
def test_integrity_export_has_exactly_three_current_pages(tmp_path, language):
    dataset = Dataset_Build()
    horizontal = GnssIntegrityStream_Build(dataset)
    vertical = GnssVerticalConsistency_Build(dataset)
    exporter = FlightExporter()
    for kind in ("GNSS_Horizontal_Consistency_Error",
                 "GNSS_Vertical_Consistency_Error", "GNSS_Receiver_Information"):
        path = tmp_path / f"{kind}.png"
        exporter._GnssIntegrityPlot_Write(
            dataset, horizontal, kind, path, language, ExportTheme.LIGHT,
            0.0, 20.0, {}, vertical,
        )
        assert path.is_file() and path.stat().st_size > 1000


@pytest.mark.parametrize("theme", ("light", "dark"))
@pytest.mark.parametrize("language", ("en_US", "zh_CN"))
@pytest.mark.parametrize("font_scale", (1, 2))
def test_integrity_gui_three_combo_views_and_shared_time_range(theme, language, font_scale):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QTabWidget

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.gnss_integrity import GnssIntegrityPage

    app = QApplication.instance() or QApplication([])
    page = GnssIntegrityPage(Translator(language))
    font = page.font()
    font.setPointSize(max(8, font.pointSize() * font_scale))
    page.setFont(font)
    page.Theme_Apply(theme)
    page.Dataset_Set(Dataset_Build())
    page.resize(1000, 700)
    page.show()
    app.processEvents()
    assert page.display_combo.count() == page.pages.count() == 3
    assert [page.display_combo.itemData(index) for index in range(3)] == [
        "horizontal", "vertical", "receiver",
    ]
    assert not page.findChildren(QTabWidget)
    assert len(page.closure_plot.listDataItems()) == 1
    assert len(page.vertical_plot.listDataItems()) == 1
    assert len(page.quality_plot.listDataItems()) == 2
    assert len(page.satellite_plot.listDataItems()) == 1
    assert "Offline" in page.status_label.text() or "离线" in page.status_label.text()
    page.TimeRange_Set(3.0, 8.0)
    for plot in page.plots:
        low, high = plot.getViewBox().viewRange()[0]
        assert abs(low - 3.0) < 1e-6 and abs(high - 8.0) < 1e-6
    page.display_combo.setCurrentIndex(1)
    assert page.pages.currentIndex() == 1
    assert "KF6" in page.vertical_note.text()
    page.Language_Apply(Translator("zh_CN"))
    assert page.display_combo.currentText() == "垂直一致性"
    page.close()


def test_integrity_status_labels_recorded_event_separately_from_offline_replay():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.ui.gnss_integrity import GnssIntegrityPage

    app = QApplication.instance() or QApplication([])
    dataset = Dataset_Build()
    page = GnssIntegrityPage(Translator("en_US"))
    page.Dataset_Set(dataset)
    page.TimeRange_Set(0.0, 2.0)
    assert "Offline diagnostic state" in page.status_label.text()
    event = DecodedRecord(0, "EVENT", 1, 0, 1, 1_000_000, 0, {
        "event_id": 0x2E, "arg0": 1 << 8,
    }, 0)
    dataset = replace(dataset, records={**dataset.records, "EVENT": (event,)})
    page.Dataset_Set(dataset)
    page.TimeRange_Set(0.0, 2.0)
    assert page.status_label.text() == "Recorded current state: SUSPECT"
    page.close()
    app.processEvents()
