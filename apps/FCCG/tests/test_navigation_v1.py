import json
import zipfile
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.render import LogDecoderProfile_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.logging import LoggingProfile_AvailabilityTransitionApply
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from tools import import_reference_components as importer

ROOT = Path(__file__).resolve().parents[1]
ESKF = "silverstar.algorithm.estimator.eskf15"


def test_eskf_actual_parameters_match_shared_contract():
    contract = json.loads((ROOT.parents[1] / "contracts/navigation_v1.json").read_text(encoding="utf-8"))
    plugin = json.loads((ROOT / "plugins/builtin/silverstar_algorithm_estimator_eskf15/plugin.json").read_text(encoding="utf-8"))
    actual = {item["id"]: {key: item[key] for key in ("type", "default", "unit", "representation", "min", "max")}
              for item in plugin["algorithm_parameters"]["parameters"]}
    assert actual == contract["eskf15"]["parameters"]
    assert len(actual) == 35
    assert plugin["metadata"]["algorithm_revision"] == contract["eskf15"]["revision"]
    assert plugin["metadata"]["gnss_integrity_revision"] == contract["quality_policy_revision"] == 3


def test_eskf_source_graph_and_logging_transition(builtin_catalog):
    previous = ReferenceProject_Create("JointNavigation", catalog=builtin_catalog)
    model = deepcopy(previous)
    model.strategies["estimator"] = ESKF
    LoggingProfile_AvailabilityTransitionApply(previous, model, builtin_catalog)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert Project_Validate(model, builtin_catalog).valid
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert any("ESKF15/Src/navigation_eskf_backend.c" in path for path in graph.sources)
    assert any("Algorithm/Common/Src/navigation_quality.c" in path for path in graph.sources)
    assert not any("Estimator/KF6/" in path for path in graph.sources)
    assert "SYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_ESKF15" in graph.defines
    assert "SYSTEM_BUILD_ESTIMATOR_ENABLED=0U" in graph.defines
    states = {item.record: item.enabled for item in model.logging_streams}
    for record in ("ESKF15_STATE", "ESKF15_INITIAL_STATE", "ESKF15_INITIAL_P_PART", "ESKF15_BODY_INPUT", "ESKF15_MEASUREMENT"):
        assert states["FLIGHT_LOG_RECORD_" + record]
    package = LogDecoderProfile_Render(model, builtin_catalog)
    assert LogDecoderPackage_Verify(package.content)["required_flp_minimum_version"] == "0.1.0"
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        semantics = json.loads(archive.read("project_semantics.json"))
    assert semantics["metadata_declarations"]["navigation_replay"]["gnss_integrity_revision"] == 3
    assert any(owner["component"] == ESKF for owner in semantics["firmware_algorithm_parameters"])


def test_reference_import_preserves_only_explicit_owned_packages():
    packages = importer._WorkspaceOwnedPackages_Get(set())
    identities = {item["manifest"]["id"] for item in packages}
    assert ESKF in identities
    assert "silverstar.device.imu.bmi323" in identities
    assert "silverstar.device.gnss.neo_m8n" in identities
    assert "silverstar.core.0_1_0" not in identities
    assert all(item["workspace_owned_package"] for item in packages)
    assert not importer._WorkspaceOwnedPackages_Get(identities)


def test_navigation_runtime_ownership_survives_reference_import(monkeypatch):
    monkeypatch.setattr(importer, "_ManifestValues_Get", lambda *_arguments: [])
    packages = importer._Components_Get(Path("unused"), {"commit": "fixture", "snapshot_digest": "fixture"})
    by_id = {item["manifest"]["id"]: item for item in packages}
    core = by_id["silverstar.core.0_1_0"]["fccg_owned_files"]
    for relative in (
        "APP/Inc/ins_task.h", "APP/Src/ins_task.c", "APP/Src/estimator_task.c",
        "APP/Src/flight_task.c", "APP/Src/logger_bus.c", "APP/Src/logger_task.c",
        "Interfaces/Inc/system_device_types.h", "Interfaces/Inc/system_imu_if.h",
        "Interfaces/Inc/system_navigation_backend.h", "Modules/Src/telemetry_service.c",
        "System/Inc/system_configuration_types.h", "System/Inc/system_navigation_health.h",
        "System/Src/system_navigation_health.c", "System/Src/system_startup.c",
        "System/Calibration/Inc/system_calibration.h", "System/Calibration/Src/system_calibration.c",
        "Tests/Host/test_navigation_quality_supervisor.c", "Tests/Host/test_eskf_backend.c",
        "Tests/Host/test_estimator_preparation.c", "Tests/Host/storage_integrity/test_eskf_storage.h",
        "Tests/Host/test_lifecycle.c", "Tests/Host/test_system_startup.c",
        "Tools/check_firmware_artifact.ps1",
    ):
        assert relative in core
        assert (ROOT / core[relative]).is_file()
    air = by_id["silverstar.protocol.telemetry.air_m0"]["fccg_owned_files"]
    assert set(air) >= {"Protocol/Inc/air_protocol.h", "Protocol/Src/air_protocol.c"}
    mcu = by_id["silverstar.mcu.stm32f407vet6"]
    assert "Targets/SilverStar_F407/Inc/target_system_config.h" in mcu["fccg_owned_files"]
    assert mcu["manifest"]["metadata"]["device_build_capabilities"]
