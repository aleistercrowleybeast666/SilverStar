from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path

import pytest

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.plugins.installer import PluginInstallError, PluginInstaller
from silverstar_fccg.plugins.manifest import PluginManifestError, PluginManifest_Load


def _Manifest_Get(component_id: str = "example.device.safe", dependency: str = "") -> dict:
    components = [{"id": dependency, "optional": False}] if dependency else []
    return {
        "schema_version": 0,
        "id": component_id,
        "name": "Safe Example",
        "type": "device",
        "class": "example",
        "instance_policy": {
            "project_max": 1,
            "same_plugin_multiple": False,
            "multi_instance_ready": False,
        },
        "physical_device": {
            "vendor": "Example",
            "model": "Safe Example",
            "chipset": "Example",
            "driver": "Example Driver",
        },
        "version": "1.0.0",
        "requires": {"components": components, "resources": [], "capabilities": []},
        "resources": {"provides": []},
        "provides": [],
        "build": {
            "sources": ["Source/example.c"],
            "asm_sources": [],
            "include_dirs": ["Source"],
            "defines": [],
        },
        "payload": {"roots": ["Source"]},
        "metadata": {"device_category": "sensor.temperature"},
    }


def _Archive_Create(
    path: Path,
    manifest: dict,
    *,
    traversal: bool = False,
    symlink: bool = False,
    duplicate_case: bool = False,
    special_file: bool = False,
) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest))
        archive.writestr("payload/Source/example.c", "int Example_ValueGet(void) { return 1; }\n")
        archive.writestr(
            "payload/Source/tool.py",
            "raise RuntimeError('plugin code must never execute')\n",
        )
        if traversal:
            archive.writestr("../escaped.txt", "escape")
        if symlink:
            info = zipfile.ZipInfo("payload/Source/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../../outside")
        if duplicate_case:
            archive.writestr("payload/source/EXAMPLE.c", "duplicate")
        if special_file:
            info = zipfile.ZipInfo("payload/Source/fifo")
            info.create_system = 3
            info.external_attr = (stat.S_IFIFO | 0o644) << 16
            archive.writestr(info, "not a regular file")


def _Package_Create(path: Path, manifest: dict) -> Path:
    source = path / "payload" / "Source"
    source.mkdir(parents=True)
    (source / "example.c").write_text("", encoding="utf-8")
    manifest_path = path / "plugin.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _Installer_Get(tmp_path: Path) -> tuple[PluginInstaller, PluginCatalog]:
    builtin = tmp_path / "builtin"
    installed = tmp_path / "installed"
    builtin.mkdir(parents=True)
    catalog = PluginCatalog(builtin, installed)
    catalog.Scan()
    return PluginInstaller(WorkspacePolicy(tmp_path), installed, catalog), catalog


def test_plugin_install_is_declarative_and_id_conflicts_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "safe.ssplugin"
    _Archive_Create(archive, _Manifest_Get())
    installer, catalog = _Installer_Get(tmp_path)
    manifest = installer.Install(archive)
    assert manifest.component_id == "example.device.safe"
    assert len(catalog.All_Get()) == 1
    assert not (tmp_path / "plugin-executed.marker").exists()
    with pytest.raises(PluginInstallError):
        installer.Install(archive)

    conflicting_archive = tmp_path / "conflicting.ssplugin"
    _Archive_Create(
        conflicting_archive, _Manifest_Get(component_id="example.device.conflicting")
    )
    with pytest.raises(PluginInstallError, match="payload conflicts"):
        installer.Install(conflicting_archive)

    removed = installer.Remove("example.device.safe")
    assert removed.component_id == "example.device.safe"
    assert catalog.All_Get() == ()
    assert not (tmp_path / "installed" / "example.device.safe").exists()
    with pytest.raises(PluginInstallError, match="Unknown component"):
        installer.Remove("example.device.safe")


@pytest.mark.parametrize(
    "attack", ["traversal", "symlink", "duplicate_case", "special_file"]
)
def test_plugin_zip_path_attacks_are_rejected(tmp_path: Path, attack: str) -> None:
    archive = tmp_path / f"{attack}.ssplugin"
    _Archive_Create(
        archive,
        _Manifest_Get(),
        traversal=attack == "traversal",
        symlink=attack == "symlink",
        duplicate_case=attack == "duplicate_case",
        special_file=attack == "special_file",
    )
    installer, _catalog = _Installer_Get(tmp_path)
    with pytest.raises(PluginInstallError):
        installer.Install(archive)
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_plugin_missing_dependency_and_bad_schema_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "dependency.ssplugin"
    _Archive_Create(archive, _Manifest_Get(dependency="missing.core"))
    installer, _catalog = _Installer_Get(tmp_path)
    with pytest.raises(PluginInstallError, match="Missing plugin dependency"):
        installer.Install(archive)

    bad = _Manifest_Get(component_id="INVALID ID")
    with pytest.raises(PluginManifestError):
        PluginManifest_Load(_Package_Create(tmp_path / "bad", bad))


def test_plugin_schema_types_capabilities_and_build_tokens_are_strict(
    tmp_path: Path,
) -> None:
    unknown = _Manifest_Get()
    unknown["unexpected"] = True
    with pytest.raises(PluginManifestError, match="Unknown manifest fields"):
        PluginManifest_Load(_Package_Create(tmp_path / "unknown", unknown))

    bad_boolean = _Manifest_Get(component_id="example.device.boolean")
    bad_boolean["requires"]["components"] = [
        {"id": "example.core", "optional": "false"}
    ]
    with pytest.raises(PluginManifestError, match="boolean"):
        PluginManifest_Load(_Package_Create(tmp_path / "boolean", bad_boolean))

    build_injection = _Manifest_Get(component_id="example.device.injection")
    build_injection["build"]["defines"] = ["SAFE\nall: malicious"]
    with pytest.raises(PluginManifestError, match="unsafe token"):
        PluginManifest_Load(_Package_Create(tmp_path / "injection", build_injection))

    capability_archive = tmp_path / "capability.ssplugin"
    capability = _Manifest_Get(component_id="example.device.capability")
    capability["requires"]["capabilities"] = ["missing.capability"]
    _Archive_Create(capability_archive, capability)
    installer, _catalog = _Installer_Get(tmp_path / "capability-store")
    with pytest.raises(PluginInstallError, match="Missing plugin capabilities"):
        installer.Install(capability_archive)

    managed_archive = tmp_path / "managed.ssplugin"
    managed = _Manifest_Get(component_id="example.device.managed")
    managed["build"]["sources"] = []
    managed["build"]["include_dirs"] = []
    managed["payload"]["roots"] = ["Generated"]
    with zipfile.ZipFile(managed_archive, "w") as archive:
        archive.writestr("plugin.json", json.dumps(managed))
        archive.writestr("payload/Generated/owned.c", "int owned;\n")
    installer, _catalog = _Installer_Get(tmp_path / "managed-store")
    with pytest.raises(PluginInstallError, match="FCCG-managed paths"):
        installer.Install(managed_archive)
