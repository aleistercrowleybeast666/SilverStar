import pytest
from PySide6.QtWidgets import QLabel

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.plugins.recommendations import SensorRecommendations_Parse
from silverstar_fccg.project.algorithm_parameters import AlgorithmParameterOwners_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile


KF = "silverstar.algorithm.estimator.kf6"


@pytest.mark.parametrize("sigma", [1.0, 2.5, 5.0])
def test_advisory_does_not_clamp_saved_generated_values(tmp_path, workspace_root, sigma):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("Advisory")
    model.algorithm_parameters[KF]["baro_std_m"] = sigma
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    loaded = service.Project_Open(project / "SilverStar.ssproject")
    assert loaded.algorithm_parameters[KF]["baro_std_m"] == sigma
    header = (project / "Generated/Inc/project_algorithm_parameters.h").read_text()
    assert f"{sigma:.9e}f" in header


def test_old_owner_missing_fields_preserves_legacy_behavior(workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("Legacy")
    values = model.algorithm_parameters[KF]
    for key in ("gnss_position_measurement_delay_ms", "gnss_velocity_measurement_delay_ms",
                "baro_measurement_delay_ms", "baro_std_m", "gnss_velocity_vertical_scale"):
        del values[key]
    model = ProjectConfiguration_Reconcile(model, service.catalog).model
    values = model.algorithm_parameters[KF]
    assert values["gnss_velocity_measurement_delay_ms"] == 0
    assert values["baro_std_m"] == 5.0
    assert values["gnss_velocity_vertical_scale"] == 1.0
    values["baro_std_m"] = 1.0
    assert ProjectConfiguration_Reconcile(model, service.catalog).model.algorithm_parameters[KF]["baro_std_m"] == 1.0


def test_delay_domain_is_static_capacity(workspace_root):
    service = FccgService(workspace_root)
    owner = service.catalog.Component_Get(KF)
    parameters = {p.parameter_id: p for p in owner.algorithm_parameters}
    for key in ("gnss_position_measurement_delay_ms", "gnss_velocity_measurement_delay_ms", "baro_measurement_delay_ms"):
        parameter = parameters[key]
        for value in (0, 100, 200, 250, 270, 300, 550):
            assert parameter.Value_Resolve(value) == value
        for value in (-1, 551, 1.5, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                parameter.Value_Resolve(value)


def test_recommendation_ui_is_advisory(qapp, workspace_root):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.ui.pages.algorithm_parameters import AlgorithmParametersPage

    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("AdvisoryUi")
    model.algorithm_parameters[KF]["baro_std_m"] = 1.0
    device = service.catalog.Component_Get("silverstar.device.imu.jy901b")
    recommendations = SensorRecommendations_Parse(device.metadata["sensor_recommendations"])
    page = AlgorithmParametersPage(Translator("zh_CN"))
    page.Configuration_Set(AlgorithmParameterOwners_Get(model, service.catalog), model.algorithm_parameters, recommendations)
    assert page.editors[(KF, "baro_std_m")].value() == 1.0
    assert any("1.5" in label.text() and "JY901B" in label.text() for label in page.findChildren(QLabel))
    page.deleteLater()


@pytest.mark.parametrize("value", [False, "bad", [None], [{"value": 1.5}]])
def test_malformed_advisory_is_rejected(value):
    with pytest.raises(ValueError):
        SensorRecommendations_Parse(value)
