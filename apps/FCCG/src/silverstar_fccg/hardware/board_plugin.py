from __future__ import annotations

import json
import hashlib
import re
import zipfile
from pathlib import Path

from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.core.errors import FccgError
from silverstar_fccg.project.model import HardwareConfiguration, ProjectModel


class BoardPluginExportError(FccgError):
    pass


class BoardPluginExporter:
    """Export one trusted custom-hardware snapshot as declarative Board data."""

    _COMPONENT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

    def __init__(
        self,
        policy: WorkspacePolicy,
        output_policy: WorkspacePolicy | None = None,
    ) -> None:
        self.policy = policy
        self.output_policy = output_policy or policy

    def Plugin_Export(
        self,
        model: ProjectModel,
        snapshot_root: Path,
        output_path: Path,
        *,
        component_id: str,
        name: str,
        version: str | None = None,
        target_role: str = "flight",
        namespace_payload: bool = False,
    ) -> Path:
        if target_role not in {"flight", "ground"}:
            raise BoardPluginExportError("Board target role must be flight or ground")
        hardware = (model.hardware if target_role == "flight"
                    else model.ground_target.hardware)
        if hardware.mode != "custom":
            raise BoardPluginExportError("Only imported custom hardware can be exported")
        if not self._COMPONENT_ID_PATTERN.fullmatch(component_id):
            raise BoardPluginExportError("Invalid Board component id")
        if not name.strip():
            raise BoardPluginExportError("Board name must not be empty")
        snapshot = self.policy.Path_Resolve(snapshot_root, allow_root=False)
        if not snapshot.is_dir():
            raise BoardPluginExportError("Custom hardware snapshot is unavailable")
        output = self.output_policy.Path_Resolve(output_path, allow_root=False)
        if output.suffix.casefold() != ".ssplugin":
            output = output.with_suffix(".ssplugin")
            output = self.output_policy.Path_Resolve(output, allow_root=False)
        manifest = self._Manifest_Get(
            model,
            component_id=component_id,
            name=name.strip(),
            version=version or "0.1.0",
            target_role=target_role,
        )
        payload_root = "HardwareGenerated/STM32CubeMX"
        if namespace_payload:
            # Keep Windows paths short; the full ID remains in the manifest.
            payload_root = "PCB/" + hashlib.sha256(component_id.encode("ascii")).hexdigest()[:16]
            manifest["payload"]["roots"] = [payload_root]
            manifest["board"]["hardware_root"] = payload_root
            for key in ("sources", "asm_sources", "include_dirs"):
                manifest["build"][key] = [value.replace("HardwareGenerated/STM32CubeMX", payload_root, 1)
                                          for value in manifest["build"][key]]
            manifest["build"]["linker_script"] = manifest["build"]["linker_script"].replace(
                "HardwareGenerated/STM32CubeMX", payload_root, 1)
        stage = self.output_policy.StagingDirectory_Create("board-export-")
        staged_archive = stage / output.name
        try:
            with zipfile.ZipFile(
                staged_archive, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(
                    "plugin.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
                archive.writestr(
                    "docs/HARDWARE_PROVENANCE.md",
                    self._Provenance_Render(model, name, hardware, target_role),
                )
                connections = {
                    "format_version": 1,
                    "resources": {
                        resource.resource_id: {
                            "physical": resource.resource_id,
                            "fixed": False,
                            "purpose": "custom",
                        }
                        for resource in hardware.resources
                    },
                }
                archive.writestr(
                    "connections.json",
                    json.dumps(connections, ensure_ascii=False, indent=2) + "\n",
                )
                for source in sorted(snapshot.rglob("*")):
                    if source.is_symlink():
                        raise BoardPluginExportError(
                            "Hardware snapshot contains an unexpected symlink"
                        )
                    if not source.is_file():
                        continue
                    relative = source.relative_to(snapshot).as_posix()
                    archive.write(
                        source,
                        f"payload/{payload_root}/{relative}",
                    )
                    if relative == hardware.ioc_file:
                        archive.write(source, f"hardware/{source.name}")
            output.parent.mkdir(parents=True, exist_ok=True)
            self.output_policy.Path_Replace(staged_archive, output)
            return output
        finally:
            if stage.exists():
                self.output_policy.Tree_Remove(stage)
            staging_root = self.output_policy.Path_Resolve(
                ".staging", allow_root=False
            )
            if staging_root.is_dir() and not any(staging_root.iterdir()):
                staging_root.rmdir()

    @staticmethod
    def _Manifest_Get(
        model: ProjectModel, *, component_id: str, name: str, version: str,
        target_role: str = "flight",
    ) -> dict:
        hardware = (model.hardware if target_role == "flight"
                    else model.ground_target.hardware)
        mcu = model.mcu if target_role == "flight" else model.ground_target.mcu
        assignments = (model.resource_assignments if target_role == "flight"
                       else model.ground_target.resource_assignments)
        provisions = [
            {
                "id": resource.resource_id,
                "kind": resource.kind,
                "metadata": {
                    key: resource.metadata[key]
                    for key in ("c_id", "header")
                    if key in resource.metadata
                },
            }
            for resource in hardware.resources
        ]
        by_id = {
            resource.resource_id: resource for resource in hardware.resources
        }
        roles = []
        for key, selected in sorted(assignments.items()):
            resource = by_id.get(selected)
            if resource is None:
                continue
            candidates = [
                candidate.resource_id
                for candidate in hardware.resources
                if candidate.kind == resource.kind
            ]
            roles.append(
                {
                    "key": key,
                    "kind": resource.kind,
                    "default": selected,
                    "candidates": candidates,
                    "fixed": False,
                }
            )
        capability_slug = component_id.replace("-", "_").replace(".", "_")
        ioc_name = Path(hardware.ioc_file).name
        return {
            "schema_version": 0,
            "id": component_id,
            "name": name,
            "type": "board",
            "class": ("flight_controller_board" if target_role == "flight"
                      else "ground_station_board"),
            "version": version,
            "description": "Custom Board imported through the trusted STM32CubeMX provider.",
            "requires": {
                "components": [
                    *([{"id": model.core, "optional": False}]
                      if target_role == "flight" else []),
                    {"id": mcu, "optional": False},
                ],
                "resources": [],
                "capabilities": [],
            },
            "resources": {
                "provides": provisions,
                "roles": roles,
                "conflicts": [],
            },
            "provides": [
                f"board.{capability_slug}",
                "hardware.stm32.generated",
            ],
            "build": {
                "sources": list(hardware.build_sources),
                "asm_sources": list(hardware.asm_sources),
                "include_dirs": list(hardware.include_dirs),
                "defines": list(hardware.defines),
                "linker_script": hardware.linker_script,
            },
            "payload": {"roots": ["HardwareGenerated/STM32CubeMX"]},
            "metadata": {
                "display_names": {"zh_CN": f"{name}（自定义硬件）", "en_US": f"{name} (Custom)"},
                "hardware_maturity": "local_unverified",
                "target_role": ("flight_controller" if target_role == "flight"
                                else "ground_station"),
                "hardware_provenance": {
                    "provider": hardware.provider,
                    "source_kind": "manual_import",
                    "source_label": hardware.source_label,
                    "source_digest": hardware.source_digest,
                    "ioc_file": hardware.ioc_file,
                    "mcu": hardware.mcu,
                    "clock": hardware.inventory.get("clocks", {}),
                },
            },
            "board": {
                "source_kind": "manual_import",
                "compatible_mcus": [mcu],
                "vendor": "STM32",
                "provider": hardware.provider,
                "verified": False,
                "hardware_root": "HardwareGenerated/STM32CubeMX",
                "ioc_file": f"hardware/{ioc_name}",
                "connections_file": "connections.json",
            },
        }

    @staticmethod
    def _Provenance_Render(
        model: ProjectModel, name: str, hardware: HardwareConfiguration,
        target_role: str,
    ) -> str:
        return f"""# {name} hardware provenance

- Source kind: `manual_import`
- Target role: `{target_role}`
- Provider: `{hardware.provider}`
- MCU: `{hardware.mcu}`
- CubeMX input: `{hardware.source_label}/{hardware.ioc_file}`
- Source digest: `{hardware.source_digest}`

This package contains vendor-generated hardware data. It is not an official
SilverStar hardware verification claim. Validate clocks, DMA, interrupts,
GPIO electrical levels and power behavior on the target board.
"""
