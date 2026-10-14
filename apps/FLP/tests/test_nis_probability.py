from pathlib import Path
import json
import math
import pytest

from silverstar_flp.core.nis_probability import (
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


from PySide6.QtWidgets import QApplication
from silverstar_flp.ui.nis_editor import NisProbabilityEditor


def test_flp_editor_preserves_legacy_and_probability_primary():
    app = QApplication.instance() or QApplication([])
    editor = NisProbabilityEditor(2, 0.001, 10000.0, "zh_CN")
    editor.setValue(9.210123456789)
    assert editor.value() == 9.210123456789
    assert editor.Input_Get() == 9.210123456789
    editor.percent.setValue(95.0)
    assert editor.Input_Get()["probability"] == 0.95
    assert math.isclose(editor.value(), 5.991464547107979, rel_tol=1e-7)
    editor.setValue(10000.0)
    assert editor.Input_Get() == 10000.0
    editor.NumericDisplay_Set(True)
    assert editor.percent.isHidden()
    assert "df = ?" in editor.readout.text()
    app.processEvents()


from silverstar_flp.core.i18n import Translator
from silverstar_flp.core.project import Project_Load, Project_Save, ReplayConfiguration_Validate
from silverstar_flp.core.nis_probability import RecordedNisDf_Get
from silverstar_flp.plugins.api.algorithm import ReplayMode
from silverstar_flp.plugins.registry import builtin_registry
from silverstar_flp.plugins.log_parsers.sslog0.plugin import Sslog0ParserPlugin
from silverstar_flp.ui.pages.replay import ReplayPage
from silverstar_flp.core.analysis_source import ReplayResultStore
from tests.parameter_fixtures import SyntheticParameters_Attach
from tests.sslog_synthetic import StationaryFlight_Build
from tests.test_project_export import _ProjectDocument_Build


@pytest.fixture
def probability_page(tmp_path):
    app=QApplication.instance() or QApplication([])
    raw=Sslog0ParserPlugin().parse(StationaryFlight_Build(tmp_path/"SYNTHETIC_nis_migration.BIN"))
    dataset=SyntheticParameters_Attach(raw,tmp_path/"package")
    page=ReplayPage(Translator("en_US"),builtin_registry())
    page.Dataset_Set(dataset,ReplayResultStore())
    page.algorithm_combo.setCurrentIndex(page.algorithm_combo.findData("silverstar.algorithm.kf6"))
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.WHAT_IF))
    yield page,dataset,app
    page.close()
    app.processEvents()


def test_probability_primary_project_roundtrip_and_source_bytes_immutable(probability_page,tmp_path):
    page,dataset,app=probability_page
    before=dataset.source_path.read_bytes()
    baseline=page.Configuration_Get()
    assert "nis_inputs" not in baseline
    page._parameter_widgets["nis_2d_soft"].percent.setValue(95.)
    page._parameter_widgets["nis_hard_enabled"].setChecked(False)
    saved=page.Configuration_Get()
    assert saved["nis_inputs"]["nis_2d_soft"]["probability"] == .95
    assert saved["actual_values"]["nis_hard_enabled"] == 0
    actual=saved["actual_values"]["nis_2d_soft"]
    doc=_ProjectDocument_Build(dataset.source_path,tmp_path/"probability.ssflp")
    doc.replay_configurations["draft"]=saved
    Project_Save(doc,doc.project_path)
    loaded=Project_Load(doc.project_path)
    page._Parameters_Reset()
    page.Configuration_Set(loaded.replay_configurations["draft"])
    assert page.Configuration_Get()["nis_inputs"]==saved["nis_inputs"]
    assert page.Configuration_Get()["actual_values"]["nis_2d_soft"]==actual
    page.Language_Apply(Translator("zh_CN"))
    assert page.Configuration_Get()["nis_inputs"]==saved["nis_inputs"]
    assert dataset.source_path.read_bytes()==before
    page.Configuration_Set(baseline)
    assert "nis_inputs" not in page.Configuration_Get()


@pytest.mark.parametrize("change",[{"unit":"percent"},{"schema_id":"2.0"},{"degrees_of_freedom":6},
    {"probability":0.0},{"probability":1.0},{"probability":float("nan")},{"probability":.99}])
def test_saved_probability_cannot_disagree_with_actual_value(probability_page,change):
    page,_,_=probability_page
    page._parameter_widgets["nis_2d_soft"].percent.setValue(95.)
    cfg=page.Configuration_Get()
    cfg["nis_inputs"]["nis_2d_soft"].update(change)
    with pytest.raises(ValueError):
        ReplayConfiguration_Validate(cfg)


def test_probability_invalid_draft_and_soft_hard_order_are_rejected(probability_page):
    page,_,_=probability_page
    page._parameter_widgets["nis_2d_soft"].percent.setValue(100.)
    with pytest.raises(ValueError):
        page.Configuration_Get()
    page._RuntimeParameters_Refresh()
    page.Language_Apply(Translator("zh_CN"))
    assert "NIS = ?" in page._parameter_widgets["nis_2d_soft"].readout.text()
    with pytest.raises(ValueError):
        page.Configuration_Get()
    page._Parameters_Reset()
    page._parameter_widgets["nis_2d_soft"].percent.setValue(99.999)
    page._parameter_widgets["nis_2d_hard"].percent.setValue(95.)
    with pytest.raises(ValueError):
        page.Configuration_Get()


def test_recorded_df_requires_versioned_raw_fraction_contract(probability_page):
    page,_,_=probability_page
    declaration={"schema_id":"silverstar.nis-gating/1.0","definition":"raw_r_transpose_S_inverse_r",
                 "probability_unit":"fraction","threshold_df":{"nis_2d_soft":2}}
    assert RecordedNisDf_Get(declaration,"nis_2d_soft")==2
    for corrupt in [{"schema_id":"unknown"},{"definition":"nis_divided_by_dimension"},
                    {"probability_unit":"percent"},{"threshold_df":{"nis_2d_soft":True}},
                    {"threshold_df":{"nis_2d_soft":2.0}}]:
        assert RecordedNisDf_Get({**declaration,**corrupt},"nis_2d_soft") is None
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.RECORDED_CONFIGURATION))
    editor=page._parameter_widgets["nis_2d_soft"]
    assert editor.percent.isHidden()
    assert "df = ?" in editor.readout.text()
    assert "nis_inputs" not in page.Configuration_Get()
