from __future__ import annotations

import json
import re
import shutil
import tomllib
import zipfile
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel
from silverstar_fccg import __version__
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.version import (
    SILVERSTAR_BUILD_ID,
    SILVERSTAR_CORE_COMPONENT_ID,
    SILVERSTAR_LOG_BUILD_TAG,
    SILVERSTAR_PLATFORM_VERSION,
    SILVERSTAR_SYSTEM_PROFILE_ID,
)
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.generator.log_decoder_profile import (
    LogDecoderPackage_Verify,
)
from silverstar_fccg.generator.render import (
    GeneratedFiles_Render,
    LogDecoderProfile_Render,
    MetadataFiles_Render,
)
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.hardware.platform import (
    DetectedMcuFacts,
    PlatformMatch_Resolve,
    PlatformMatchError,
)
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.manifest import (
    PluginManifest_Parse,
    PluginManifestError,
)
from silverstar_fccg.project.configuration import (
    ProjectConfiguration_Reconcile,
)
from silverstar_fccg.project.lifecycle import ProjectReadiness_Inspect
from silverstar_fccg.project.logging import (
    LoggingProfile_Reconcile,
    LogPolicyLevel,
    ProtocolLogDefinitions_Get,
)
from silverstar_fccg.project.model import (
    PROJECT_FORMAT_VERSION,
    HardwareConfiguration,
    ProjectModel_Parse,
    ProjectModelError,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.pages.components import FlightConfigurationPage

CALIBRATION_COMPONENT = "silverstar.algorithm.calibration"
CALIBRATION_RECORD = "FLIGHT_LOG_RECORD_CALIBRATION_RESULT"
F407_MCU = "silverstar.mcu.stm32f407vet6"
H743_FIXTURE_MCU = "fixture.mcu.stm32h743zit6"
H743_FIXTURE_FAMILY = "fixture.mcu_family.stm32h7"
H743_FIXTURE_BOARD = "fixture.board.stm32h743"
H743_FIXTURE_OS = "fixture.os.freertos_h743"
H743_FIXTURE_STORAGE = "fixture.device.storage_sdio_h743"


def _LegacyProjectData_Get(
    builtin_catalog: PluginCatalog,
    calibration: list[str],
) -> dict:
    data = ReferenceProject_Create(
        "LegacyPreRelease", catalog=builtin_catalog
    ).Dictionary_Get()
    data["project"]["firmware_version"] = "0.0.9"
    data["project"]["build_target"] = "SilverStar_0_0_9"
    data["components"]["core"] = "silverstar.core.0_0_9"
    data["modes"]["calibration"] = list(calibration)
    for selection in data["protocols"].values():
        if selection is not None:
            selection["version"] = "0.0.9"
            selection["manifest_sha256"] = "0" * 64
    data["hardware"]["platform_version"] = "0.0.9"
    data["hardware"]["platform_manifest_sha256"] = "0" * 64
    return data


def _OldCoreProvenance_Get() -> dict[str, object]:
    return {
        "version": "0.0.9",
        "source": "builtin",
        "manifest_id": "silverstar.core.0_0_9",
        "payload_digest": "0" * 64,
        "files": {},
    }


def _H743Catalog_Create(
    tmp_path: Path,
    workspace_root: Path,
) -> tuple[PluginCatalog, Path]:
    installed_root = tmp_path / "plugins" / "installed"
    family_source = (
        workspace_root / "plugins" / "builtin" / "silverstar_mcu_family_stm32f4"
    )
    family_package = installed_root / H743_FIXTURE_FAMILY.replace(".", "_")
    shutil.copytree(family_source, family_package)
    family_manifest_path = family_package / "plugin.json"
    family_data = json.loads(family_manifest_path.read_text(encoding="utf-8"))
    family_data["id"] = H743_FIXTURE_FAMILY
    family_data["name"] = "Synthetic STM32H7 family backend fixture"
    family_data["metadata"]["family"] = "STM32H7"
    family_data["platform"]["match_rules"][0]["family_pattern"] = "STM32H7*"
    family_manifest_path.write_text(
        json.dumps(family_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_mcu_stm32f407vet6"
    )
    package = installed_root / "fixture_mcu_stm32h743zit6"
    shutil.copytree(source, package)
    target_root = package / "payload" / "Targets"
    shutil.move(
        target_root / "SilverStar_F407",
        target_root / "SilverStar_H743_Test",
    )
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix.casefold() in {
            ".c",
            ".h",
            ".json",
            ".ld",
            ".md",
            ".mk",
            ".s",
        }:
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("SilverStar_F407", "SilverStar_H743_Test"),
                encoding="utf-8",
            )
    manifest_path = package / "plugin.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["id"] = H743_FIXTURE_MCU
    data["metadata"]["platform_family_id"] = H743_FIXTURE_FAMILY
    for requirement in data["requires"]["components"]:
        if requirement["id"] == "silverstar.mcu_family.stm32f4":
            requirement["id"] = H743_FIXTURE_FAMILY
    data["name"] = "Fixture STM32H743ZIT6 Platform"
    data["class"] = "stm32h7_test_fixture"
    data["description"] = (
        "Test-only alternate Platform fixture; it is not a production support claim."
    )
    data["provides"] = [
        "mcu.cortex_m7",
        "platform.fixture_stm32h7",
        "memory.ccmram",
        "hardware_provider.stm32_cubemx",
    ]
    data["metadata"]["mcu_model"] = "STM32H743ZIT6"
    data["metadata"]["display_names"] = {
        "zh_CN": "测试用 STM32H743ZIT6",
        "en_US": "Fixture STM32H743ZIT6",
    }
    data["platform"]["build_target"]["profile"] = (
        "SilverStar_H743_Test"
    )
    data["platform"]["match_rules"] = [
        {
            "vendor": "STM32",
            "exact_part": "STM32H743ZIT6",
            "family_pattern": "STM32H7*",
            "package_pattern": "LQFP144",
            "core_pattern": "*M7*",
            "priority": 100,
            "specificity": 1000,
            "verification": "experimental",
        }
    ]
    family_data["platform"]["support"] = {
        "level": "experimental",
        "limitations": [
            "Test fixture only; no firmware, hardware, flash or flight support claim"
        ],
    }
    family_manifest_path.write_text(
        json.dumps(family_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    board_source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_board_silverstar_0_5"
    )
    board_package = installed_root / "fixture_board_stm32h743"
    shutil.copytree(board_source, board_package)
    board_manifest_path = board_package / "plugin.json"
    board_data = json.loads(board_manifest_path.read_text(encoding="utf-8"))
    board_data["id"] = H743_FIXTURE_BOARD
    board_data["name"] = "Fixture STM32H743 Board"
    board_data["description"] = (
        "Test-only board fixture; it is not a production support claim."
    )
    for requirement in board_data["requires"]["components"]:
        if requirement["id"] == F407_MCU:
            requirement["id"] = H743_FIXTURE_MCU
    board_data["board"]["compatible_mcus"] = [H743_FIXTURE_MCU]
    board_data["board"]["verified"] = False
    board_manifest_path.write_text(
        json.dumps(board_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    board_ioc = board_package / "payload" / "Flight_Controller0.5.ioc"
    ioc_text = board_ioc.read_text(encoding="utf-8")
    ioc_text = ioc_text.replace(
        "Mcu.CPN=STM32F407VET6", "Mcu.CPN=STM32H743ZIT6"
    ).replace(
        "Mcu.Family=STM32F4", "Mcu.Family=STM32H7"
    ).replace(
        "Mcu.Name=STM32F407V(E-G)Tx", "Mcu.Name=STM32H743ZIT6"
    ).replace(
        "Mcu.Package=LQFP100", "Mcu.Package=LQFP144"
    ).replace(
        "Mcu.UserName=STM32F407VETx",
        "Mcu.UserName=STM32H743ZIT6\nMcu.Core=ARM Cortex-M7",
    )
    board_ioc.write_text(ioc_text, encoding="utf-8")

    os_source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_os_freertos_11_3_0"
    )
    os_package = installed_root / "fixture_os_freertos_h743"
    shutil.copytree(os_source, os_package)
    os_target_root = os_package / "payload" / "Targets"
    shutil.move(
        os_target_root / "SilverStar_F407",
        os_target_root / "SilverStar_H743_Test",
    )
    for path in sorted(os_package.rglob("*")):
        if path.is_file() and path.suffix.casefold() in {
            ".c",
            ".h",
            ".json",
            ".md",
            ".mk",
        }:
            text = path.read_text(encoding="utf-8")
            path.write_text(
                text.replace("SilverStar_F407", "SilverStar_H743_Test"),
                encoding="utf-8",
            )
    os_manifest_path = os_package / "plugin.json"
    os_data = json.loads(os_manifest_path.read_text(encoding="utf-8"))
    os_data["id"] = H743_FIXTURE_OS
    os_data["name"] = "Fixture FreeRTOS for STM32H743"
    os_data["description"] = (
        "Test-only target-routing fixture; it is not a production support claim."
    )
    for requirement in os_data["requires"]["components"]:
        if requirement["id"] == F407_MCU:
            requirement["id"] = H743_FIXTURE_MCU
    os_manifest_path.write_text(
        json.dumps(os_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    storage_source = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_device_storage_sd_sdio_fatfs"
    )
    storage_package = installed_root / "fixture_storage_sdio_h743"
    shutil.copytree(storage_source, storage_package)
    storage_manifest_path = storage_package / "plugin.json"
    storage_data = json.loads(
        storage_manifest_path.read_text(encoding="utf-8")
    )
    storage_data["id"] = H743_FIXTURE_STORAGE
    storage_data["name"] = "Fixture SDIO Storage for STM32H743"
    storage_data["description"] = (
        "Test-only dependency fixture; it is not a production support claim."
    )
    for requirement in storage_data["requires"]["components"]:
        if requirement["id"] == F407_MCU:
            requirement["id"] = H743_FIXTURE_MCU
    storage_manifest_path.write_text(
        json.dumps(storage_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    catalog = PluginCatalog(
        workspace_root / "plugins" / "builtin",
        installed_root,
    )
    catalog.Scan()
    return catalog, manifest_path


def _CustomH743Model_Get(catalog: PluginCatalog):
    model = ReferenceProject_Create("AlternateTarget", catalog=catalog)
    model.board = H743_FIXTURE_BOARD
    model.mcu_family = H743_FIXTURE_FAMILY
    model.mcu = H743_FIXTURE_MCU
    model.os = H743_FIXTURE_OS
    model.protocols["logging"] = None
    model.device_instances = [
        (
            replace(instance, plugin=H743_FIXTURE_STORAGE)
            if instance.plugin == "silverstar.device.storage.sd_sdio_fatfs"
            else instance
        )
        for instance in model.device_instances
    ]
    model.resource_assignments = {}
    return ProjectConfiguration_Reconcile(model, catalog).model


def _F407ComposedManifestData_Get(workspace_root: Path) -> dict[str, object]:
    """Use the same family/exact platform composition as the catalog loader."""
    builtin = workspace_root / "plugins" / "builtin"
    exact = json.loads(
        (builtin / "silverstar_mcu_stm32f407vet6" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    family = json.loads(
        (builtin / "silverstar_mcu_family_stm32f4" / "plugin.json").read_text(
            encoding="utf-8"
        )
    )
    exact["platform"] = {**family["platform"], **exact["platform"]}
    return exact


def test_platform_release_has_one_runtime_version_truth(
    workspace_root: Path,
) -> None:
    assert __version__ == SILVERSTAR_PLATFORM_VERSION == "0.1.0"
    assert SILVERSTAR_BUILD_ID == "SilverStar_0_1_0"
    assert SILVERSTAR_CORE_COMPONENT_ID == "silverstar.core.0_1_0"
    assert SILVERSTAR_LOG_BUILD_TAG == "SILV0100"
    assert len(SILVERSTAR_LOG_BUILD_TAG.encode("ascii")) == 8
    assert SILVERSTAR_SYSTEM_PROFILE_ID == 0x0000000C
    packaging = tomllib.loads((workspace_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert packaging["project"]["dynamic"] == ["version"]
    assert packaging["tool"]["setuptools"]["dynamic"]["version"]["attr"] == (
        "silverstar_fccg.app.version.__version__"
    )

    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(
            (workspace_root / "plugins" / "builtin").glob(
                "*/plugin.json"
            )
        )
    ]
    manifest_ids = {manifest["id"] for manifest in manifests}
    assert len(manifests) == len(manifest_ids)
    assert {
        "silverstar.algorithm.alignment.vector_constraints",
        "silverstar.algorithm.alignment.external_attitude_source",
    } <= manifest_ids
    for manifest in manifests:
        expected = (
            "11.3.0"
            if manifest["id"] == "silverstar.os.freertos_11_3_0"
            else "0.1.0"
        )
        assert manifest["version"] == expected
        if manifest["type"] == "protocol":
            contribution = manifest["protocol"]
            assert contribution["firmware_version"] == "0.1.0"
            assert contribution["documentation_version"] == "0.1.0"
            profiles = next(iter(contribution["profiles"].values()))
            assert {profile["version"] for profile in profiles} == {"0.0"}

    assert not (
        workspace_root / "plugins" / "builtin" / "silverstar_core_0_0_9"
    ).exists()
    assert (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "docs"
        / "SilverStar_0_0_12.md"
    ).is_file()


def test_new_project_and_generated_identity_are_consistently_0_0_12(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create("VersionTruth", catalog=builtin_catalog)
    assert model.format_version == PROJECT_FORMAT_VERSION
    assert model.identity.firmware_version == "0.1.0"
    assert model.identity.build_target == "SilverStar_0_1_0"
    assert model.core == "silverstar.core.0_1_0"
    assert model.build.target_profile == "SilverStar_F407"

    graph = SourceGraph_Resolve(model, builtin_catalog)
    generated = GeneratedFiles_Render(model, builtin_catalog, graph)
    metadata = MetadataFiles_Render(model, builtin_catalog, graph)
    saved = ProjectModel_Parse(json.loads(metadata["SilverStar.ssproject"]))
    assert saved.identity == model.identity
    assert saved.core == model.core
    assert saved.build.target_profile == "SilverStar_F407"
    assert "TARGET_PROFILE ?= SilverStar_F407" in metadata[
        "Makefile"
    ].decode("utf-8")
    assert "Targets/SilverStar_F407/target.mk" in metadata

    semantics = json.loads(
        generated["Generated/project_semantics.json"].decode("utf-8")
    )
    assert semantics["firmware_version"] == "0.1.0"
    assert semantics["target"] == "SilverStar_F407"
    assert any(
        lock["component"] == "silverstar.core.0_1_0"
        and lock["version"] == "0.1.0"
        for lock in semantics["component_locks"]
    )

    package = LogDecoderProfile_Render(model, builtin_catalog)
    manifest = LogDecoderPackage_Verify(package.content)
    assert manifest["package_schema"] == {
        "id": "silverstar.ssdecoder.package-schema/1.2",
        "major": 1,
        "minor": 2,
    }
    assert manifest["firmware_version"] == "0.1.0"
    assert manifest["fccg_version"] == "0.1.0"
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        decoder_readme = archive.read("README.md").decode("utf-8")
    assert "not a whitelist" in decoder_readme
    assert "NONE/identity" in decoder_readme


def test_official_format12_core_migrates_on_open_generate_save_reopen(
    tmp_path: Path, workspace_root: Path,
) -> None:
    service = FccgService(workspace_root)
    original = service.ReferenceProject_Create("LegacyCore")
    data = original.Dictionary_Get()
    data["project"]["firmware_version"] = "0.0.10"
    data["project"]["build_target"] = "SilverStar_0_0_10"
    data["components"]["core"] = "silverstar.core.0_0_10"
    old_root = tmp_path / "legacy_input"
    old_root.mkdir()
    (old_root / "SilverStar.ssproject").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    migrated = service.Project_Open(old_root)
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.identity.firmware_version == "0.1.0"
    assert migrated.core == "silverstar.core.0_1_0"
    fresh_root = tmp_path / "revision_0_0_12"
    service.Project_Save(migrated, fresh_root)
    reopened = service.Project_Open(fresh_root)
    assert reopened.identity.firmware_version == "0.1.0"
    assert reopened.core == "silverstar.core.0_1_0"
    assert (fresh_root / "LogDecoder.ssdecoder").exists() or any(
        fresh_root.glob("*.ssdecoder")
    )
    assert (fresh_root / "Generated" / "project_semantics.json").is_file()

    unknown = original.Dictionary_Get()
    unknown["project"]["firmware_version"] = "0.0.10"
    unknown["project"]["build_target"] = "SilverStar_0_0_10"
    unknown["components"]["core"] = "custom.core.0_0_10"
    parsed = ProjectModel_Parse(unknown)
    assert parsed.core == "custom.core.0_0_10"


def test_architecture_gate_accepts_current_and_rejects_old_patch(
    workspace_root: Path,
) -> None:
    core = workspace_root / "plugins" / "builtin" / "silverstar_core_0_1_0" / "payload"
    checker = (core / "Tools" / "check_architecture.ps1").read_text(encoding="utf-8")
    assert "-Pattern 'SILVERSTAR_VERSION_MINOR\\s+1'" in checker
    pattern = r"SILVERSTAR_VERSION_MINOR\s+1"
    current = (core / "System" / "User" / "system_user_config.h").read_text(
        encoding="utf-8"
    )
    assert re.search(pattern, current)
    assert not re.search(pattern, current.replace(
        "SILVERSTAR_VERSION_MINOR     1", "SILVERSTAR_VERSION_MINOR     0"
    ))


def test_generated_firmware_version_macros_match_product_version(
    workspace_root: Path,
) -> None:
    config = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
        / "System"
        / "User"
        / "system_user_config.h"
    ).read_text(encoding="utf-8")
    assert re.search(r"#define\s+SILVERSTAR_VERSION_MAJOR\s+0\b", config)
    assert re.search(r"#define\s+SILVERSTAR_VERSION_MINOR\s+1\b", config)
    assert re.search(r"#define\s+SILVERSTAR_VERSION_PATCH\s+0\b", config)
    assert re.search(r"#define\s+SILVERSTAR_VERSION_BUILD\s+0\b", config)
    assert re.search(
        r'#define\s+SILVERSTAR_LOG_BUILD_TAG\s+"SILV0100"', config
    )
    assert re.search(
        r"#define\s+SYSTEM_PROFILE_ID\s+0x0000000CUL\b", config
    )


@pytest.mark.parametrize(
    ("legacy", "expected"),
    (
        (["Existing"], []),
        (["Existing", "OneFace"], ["OneFace"]),
        (["Existing", "SixFace"], ["SixFace"]),
        (
            ["Existing", "OneFace", "SixFace"],
            ["OneFace", "SixFace"],
        ),
    ),
)
def test_current_pre_release_calibration_migration_is_deterministic(
    builtin_catalog: PluginCatalog,
    legacy: list[str],
    expected: list[str],
) -> None:
    migrated = ProjectModel_Parse(
        _LegacyProjectData_Get(builtin_catalog, legacy)
    )
    assert migrated.format_version == PROJECT_FORMAT_VERSION
    assert migrated.identity.firmware_version == "0.1.0"
    assert migrated.identity.build_target == "SilverStar_0_1_0"
    assert migrated.core == "silverstar.core.0_1_0"
    assert migrated.modes["calibration"] == expected

    reconciled = ProjectConfiguration_Reconcile(
        migrated, builtin_catalog
    ).model
    assert reconciled.build.target_profile == "SilverStar_F407"
    assert all(
        selection is None
        or (
            selection.version == "0.1.0"
            and selection.manifest_sha256
            == builtin_catalog.Component_Get(
                selection.component
            ).ManifestSha256_Get()
        )
        for selection in reconciled.protocols.values()
    )
    serialized = reconciled.Dictionary_Get()
    assert "Existing" not in json.dumps(serialized)


def test_pre_release_migration_rejects_duplicates_and_unknowns_strictly(
    builtin_catalog: PluginCatalog,
) -> None:
    duplicate = _LegacyProjectData_Get(
        builtin_catalog, ["Existing", "OneFace", "OneFace"]
    )
    with pytest.raises(ProjectModelError, match="duplicate"):
        ProjectModel_Parse(duplicate)

    unknown = ProjectModel_Parse(
        _LegacyProjectData_Get(
            builtin_catalog, ["Existing", "ThirdPartyCalibration"]
        )
    )
    assert unknown.modes["calibration"] == ["ThirdPartyCalibration"]
    validation = Project_Validate(unknown, builtin_catalog)
    assert not validation.valid
    assert any(issue.code == "mode_option" for issue in validation.issues)


def test_generated_pre_release_payload_is_blocked_and_marked_stale(
    tmp_path: Path,
    builtin_catalog: PluginCatalog,
) -> None:
    data = _LegacyProjectData_Get(builtin_catalog, ["Existing"])
    data["component_provenance"] = {
        "silverstar.core.0_0_9": _OldCoreProvenance_Get()
    }
    project_file = tmp_path / "SilverStar.ssproject"
    project_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    migrated = ProjectModel_Parse(data)
    marker = migrated.reference_provenance["pre_release_migration"]
    assert marker["requires_new_output_directory"] is True
    validation = Project_Validate(migrated, builtin_catalog)
    assert any(
        issue.code == "pre_release_rebuild_required"
        for issue in validation.issues
    )
    readiness = ProjectReadiness_Inspect(
        migrated, tmp_path, builtin_catalog
    )
    assert "SilverStar.ssproject:pre_release_rebuild_required" in (
        readiness.stale
    )


def test_calibration_manifest_gui_and_defaults_use_empty_selection(
    qapp,
    workspace_root: Path,
    builtin_catalog: PluginCatalog,
) -> None:
    del qapp
    manifest = builtin_catalog.Component_Get(CALIBRATION_COMPONENT)
    selection = manifest.selection
    assert selection is not None
    assert selection.required is False
    assert selection.allow_none is True
    assert selection.allow_multiple is True
    assert selection.options == ("OneFace", "SixFace")
    assert selection.default == ()
    assert selection.aggregate_symbol == (
        "SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK"
    )
    assert "Existing" not in selection.options

    model = ReferenceProject_Create("CalibrationGui", catalog=builtin_catalog)
    assert model.modes["calibration"] == []
    service = FccgService(workspace_root)
    views = service.ComponentViews_Get("zh_CN")
    page = FlightConfigurationPage(Translator("zh_CN"))
    page.Configuration_Set(
        views,
        model.strategies,
        model.modes,
        model.mode_parameters,
    )
    checks = page.mode_checks["calibration"]
    assert [check.property("selectionOption") for check in checks] == [
        "OneFace",
        "SixFace",
    ]
    assert not any(check.isChecked() for check in checks)
    assert all("现有校准" not in check.text() for check in checks)
    notes = [
        label.text()
        for label in page.findChildren(QLabel)
        if label.property("secondaryText") is True
    ]
    assert any("恒等校正" in note and "仍记录" in note for note in notes)


@pytest.mark.parametrize(
    ("selected", "expected_expression"),
    (
        ([], "0U"),
        (
            ["OneFace"],
            "(SYSTEM_CALIBRATION_CAPABILITY_ONE_FACE)",
        ),
        (
            ["SixFace"],
            "(SYSTEM_CALIBRATION_CAPABILITY_SIX_FACE)",
        ),
        (
            ["OneFace", "SixFace"],
            "(SYSTEM_CALIBRATION_CAPABILITY_ONE_FACE | SYSTEM_CALIBRATION_CAPABILITY_SIX_FACE)",
        ),
    ),
)
def test_calibration_four_selection_combinations_round_trip_and_render(
    builtin_catalog: PluginCatalog,
    selected: list[str],
    expected_expression: str,
) -> None:
    model = ReferenceProject_Create(
        "CalibrationCombination", catalog=builtin_catalog
    )
    model.modes["calibration"] = list(selected)
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert model.modes["calibration"] == selected
    reparsed = ProjectModel_Parse(model.Dictionary_Get())
    assert reparsed.modes["calibration"] == selected
    graph = SourceGraph_Resolve(model, builtin_catalog)
    generated = GeneratedFiles_Render(model, builtin_catalog, graph)
    header = generated[
        "Generated/Inc/project_flight_config.h"
    ].decode("utf-8")
    line = next(
        value
        for value in header.splitlines()
        if value.startswith(
            "#define SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK"
        )
    )
    assert line.split(None, 2)[2] == expected_expression

    semantics = json.loads(
        generated["Generated/project_semantics.json"].decode("utf-8")
    )
    assert semantics["modes"]["calibration"] == selected
    assert "Existing" not in json.dumps(semantics["modes"])
    assert CALIBRATION_COMPONENT in semantics["algorithms"]
    assert "System/Calibration/Src/system_calibration.c" in graph.sources
    assert "APP/Src/imu_sample_bus.c" in graph.sources
    assert "APP/Src/flight_task.c" in graph.sources


def test_none_calibration_initialization_and_required_record_contract(
    workspace_root: Path,
    builtin_catalog: PluginCatalog,
) -> None:
    core = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_core_0_1_0"
        / "payload"
    )
    app_tasks = (core / "APP" / "Src" / "app_tasks.c").read_text(
        encoding="utf-8"
    )
    assert "SystemCalibration_Init();" in app_tasks
    calibration = (core / "System/Calibration/Src/system_calibration.c").read_text(
        encoding="utf-8"
    )
    assert "SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK == 0U" in calibration
    assert "SystemCalibration_NoneReadySet();" in calibration
    assert "SystemIndicator_Init();" in app_tasks
    assert "AppTasksInitResult_CalibrationInitFailed" in (
        core / "APP" / "Inc" / "app_tasks.h"
    ).read_text(encoding="utf-8")

    model = ReferenceProject_Create(
        "RequiredCalibrationResult", catalog=builtin_catalog
    )
    definition = next(
        item
        for item in ProtocolLogDefinitions_Get(model, builtin_catalog)
        if item.record == CALIBRATION_RECORD
    )
    assert definition.record_id == "0x17"
    assert definition.version == 0
    assert definition.payload_size == 72
    assert definition.default_stream.policy == "EVENT"
    assert definition.level == LogPolicyLevel.REQUIRED
    assert definition.producer_components == (
        "silverstar.core.flight_task",
    )

    stream_index = next(
        index
        for index, item in enumerate(model.logging_streams)
        if item.record == CALIBRATION_RECORD
    )
    model.logging_streams[stream_index] = replace(
        model.logging_streams[stream_index], enabled=False
    )
    LoggingProfile_Reconcile(model, builtin_catalog)
    assert next(
        item for item in model.logging_streams if item.record == CALIBRATION_RECORD
    ).enabled

    schema = json.loads(
        (
            workspace_root
            / "plugins"
            / "builtin"
            / "silverstar_protocol_logging_sslog_0_0"
            / "payload"
            / "Protocol"
            / "SSLOG"
            / "schema"
            / "sslog_schema.json"
        ).read_text(encoding="utf-8")
    )
    record = next(
        item
        for item in schema["records"]
        if item["name"] == "CALIBRATION_RESULT"
    )
    assert record["id"] == "0x17"
    assert record["version"] == 0
    assert record["payload_size"] == 72
    assert [field["name"] for field in record["fields"]] == [
        "source_id",
        "virtual_imu_id",
        "mode",
        "state",
        "ready",
        "completed_face_mask",
        "samples",
        "reject_count",
        "retry_count",
        "start_sequence",
        "accel_bias_mps2",
        "accel_scale",
        "gyro_bias_radps",
        "gyro_scale",
    ]


def test_logging_disabled_removes_logger_but_keeps_identity_correction(
    builtin_catalog: PluginCatalog,
) -> None:
    model = ReferenceProject_Create(
        "NoLoggingIdentityCorrection", catalog=builtin_catalog
    )
    model.protocols["logging"] = None
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "System/Calibration/Src/system_calibration.c" in graph.sources
    assert "APP/Src/imu_sample_bus.c" in graph.sources
    assert "APP/Src/logger_task.c" not in graph.sources
    assert "Protocol/SSLOG/Src/sslog_protocol.c" not in graph.sources
    header = GeneratedFiles_Render(model, builtin_catalog, graph)[
        "Generated/Inc/project_flight_config.h"
    ].decode("utf-8")
    assert re.search(
        r"#define\s+SILVERSTAR_PROTOCOL_LOGGING_ENABLED\s+0U\b",
        header,
    )
    assert re.search(
        r"#define\s+SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK\s+0U\b",
        header,
    )


def test_f407_target_profile_is_manifest_owned_and_tamper_detected(
    builtin_catalog: PluginCatalog,
) -> None:
    platform = builtin_catalog.Component_Get(F407_MCU)
    assert platform.platform is not None
    assert platform.platform.build_target_profile == "SilverStar_F407"

    model = ReferenceProject_Create("TargetLock", catalog=builtin_catalog)
    model.build = replace(model.build, target_profile="Tampered_Target")
    validation = Project_Validate(model, builtin_catalog)
    assert not validation.valid
    issue = next(
        item for item in validation.issues if item.code == "target_profile_lock"
    )
    assert "SilverStar_F407" in issue.message
    reconciled = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert reconciled.build.target_profile == "SilverStar_F407"


@pytest.mark.parametrize(
    "invalid",
    (
        "",
        "1LeadingDigit",
        "SilverStar H743",
        "../SilverStar_H743",
        "SilverStar/H743",
        "SilverStar\\H743",
        "SilverStar_$(H743)",
        "SilverStar_H743\nall:",
    ),
)
def test_mcu_manifest_rejects_missing_or_unsafe_target_profiles(
    invalid: str,
    workspace_root: Path,
) -> None:
    manifest_path = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_mcu_stm32f407vet6"
        / "plugin.json"
    )
    data = _F407ComposedManifestData_Get(workspace_root)
    data["platform"]["build_target"]["profile"] = invalid
    with pytest.raises(
        PluginManifestError,
        match=r"platform\.build_target\.profile",
    ):
        PluginManifest_Parse(data, manifest_path, source="installed")


def test_mcu_manifest_requires_target_and_non_mcu_cannot_declare_platform(
    workspace_root: Path,
) -> None:
    manifest_path = (
        workspace_root
        / "plugins"
        / "builtin"
        / "silverstar_mcu_stm32f407vet6"
        / "plugin.json"
    )
    missing = _F407ComposedManifestData_Get(workspace_root)
    del missing["platform"]["build_target"]
    with pytest.raises(PluginManifestError, match="build_target"):
        PluginManifest_Parse(missing, manifest_path, source="installed")

    wrong_type = _F407ComposedManifestData_Get(workspace_root)
    wrong_type["id"] = "fixture.algorithm.invalid_platform"
    wrong_type["type"] = "algorithm"
    with pytest.raises(
        PluginManifestError,
        match="MCU and MCU family plugins must declare a platform contract",
    ):
        PluginManifest_Parse(wrong_type, manifest_path, source="installed")


def test_synthetic_h743_target_flows_through_match_project_and_renderers(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    catalog, manifest_path = _H743Catalog_Create(tmp_path, workspace_root)
    manifest = catalog.Component_Get(H743_FIXTURE_MCU)
    assert manifest.manifest_path == manifest_path.resolve()
    assert manifest.platform is not None
    assert manifest.platform.build_target_profile == "SilverStar_H743_Test"
    match = PlatformMatch_Resolve(
        DetectedMcuFacts(
            vendor="STM32",
            part="STM32H743ZIT6",
            family="STM32H7",
            package="LQFP144",
            core="ARM Cortex-M7",
            provider="stm32_cubemx",
        ),
        catalog,
    )
    assert match.selected.component_id == H743_FIXTURE_MCU

    model = _CustomH743Model_Get(catalog)
    assert model.mcu == H743_FIXTURE_MCU
    assert model.build.target_profile == "SilverStar_H743_Test"
    assert Project_Validate(model, catalog).valid
    graph = SourceGraph_Resolve(model, catalog)
    generated = GeneratedFiles_Render(model, catalog, graph)
    metadata = MetadataFiles_Render(model, catalog, graph)
    assert "Targets/SilverStar_H743_Test/target.mk" in metadata
    assert "TARGET_PROFILE ?= SilverStar_H743_Test" in metadata[
        "Makefile"
    ].decode("utf-8")
    assert "SilverStar_H743_Test" in metadata[".vscode/tasks.json"].decode(
        "utf-8"
    )
    assert "SilverStar_H743_Test" in metadata[".eide/eide.yml"].decode(
        "utf-8"
    )
    semantics = json.loads(
        generated["Generated/project_semantics.json"].decode("utf-8")
    )
    assert semantics["target"] == "SilverStar_H743_Test"
    assert semantics["hardware"]["matched_mcu_platform"] == H743_FIXTURE_MCU

    model.board = "silverstar.board.silverstar_0_5"
    model.hardware = HardwareConfiguration(
        mode="board_plugin", source_kind="verified_builtin"
    )
    model.resource_assignments = {}
    f407 = ProjectConfiguration_Reconcile(model, catalog).model
    assert f407.mcu == F407_MCU
    assert f407.build.target_profile == "SilverStar_F407"


def test_synthetic_target_conflict_is_rejected(
    tmp_path: Path,
    workspace_root: Path,
) -> None:
    catalog, _manifest_path = _H743Catalog_Create(tmp_path, workspace_root)
    original = catalog.Component_Get(H743_FIXTURE_MCU)
    duplicate = replace(
        original,
        component_id="fixture.mcu.stm32h743zit6_duplicate",
        name="Duplicate H743 test target",
    )

    class MatchCatalog:
        def Type_Get(self, component_type: str):
            return (
                (original, duplicate)
                if component_type == "mcu"
                else ()
            )

    with pytest.raises(PlatformMatchError, match="ambiguous"):
        PlatformMatch_Resolve(
            DetectedMcuFacts(
                vendor="STM32",
                part="STM32H743ZIT6",
                family="STM32H7",
                package="LQFP144",
                core="ARM Cortex-M7",
                provider="stm32_cubemx",
            ),
            MatchCatalog(),  # type: ignore[arg-type]
        )
