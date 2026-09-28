from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.model import ProjectModel
from silverstar_fccg.project.resources import (
    BoardResourceProvisions_Get,
    ResourceAssignments_Resolve,
    ResourceProvisionResolvedSymbol_Get,
)

RESOURCE_BINDING_RENDERER_CONTRACT = "verified-board-fixed-v1"


def _FileDigest_Get(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def HardwareResourceBindingDescriptor_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> dict[str, Any]:
    # Ordinary labels are display metadata. A manifest can explicitly make one
    # a physical-net constraint; only these labels become binding integrity data.
    pin_labels = [
        {"requirement": item.requirement_key,
         "expected": item.requirement.constraints["pin_label"],
         "actual": item.provision.metadata.get("label", "")}
        for item in ResourceAssignments_Resolve(model, catalog).assignments
        if "pin_label" in item.requirement.constraints
    ]
    pin_contract = {"pin_label_contracts": pin_labels} if pin_labels else {}
    if model.hardware.mode == "board_plugin":
        board = catalog.Component_Get(model.board)
        bindings = []
        for provision in BoardResourceProvisions_Get(board):
            metadata = provision.metadata
            bindings.append(
                {
                    "logical_id": provision.resource_id,
                    "kind": provision.kind,
                    "physical_alias": str(
                        metadata.get(
                            "physical_alias",
                            metadata.get(
                                "physical_resource", provision.resource_id
                            ),
                        )
                    ),
                    "resolved_symbol": ResourceProvisionResolvedSymbol_Get(
                        provision
                    ),
                    "handle": str(metadata.get("handle", "")),
                    "port": str(metadata.get("port", "")),
                    "pin": str(metadata.get("pin", "")),
                    "channel": str(metadata.get("channel_token", "")),
                    "peripheral": str(metadata.get("peripheral", "")),
                    "physical_pin": str(metadata.get("physical_pin", "")),
                    "fixed": bool(metadata.get("connection_fixed", False)),
                }
            )
        return {
            **pin_contract,
            "renderer_contract": RESOURCE_BINDING_RENDERER_CONTRACT,
            "mode": (
                "verified_board"
                if board.board and board.board.verified
                else "board"
            ),
            "board": {
                "id": board.component_id,
                "version": board.version,
                "manifest_sha256": board.ManifestSha256_Get(),
            },
            "bindings": sorted(
                bindings, key=lambda item: (item["kind"], item["logical_id"])
            ),
        }

    bindings = []
    for resource in model.hardware.resources:
        metadata = resource.metadata
        port = str(metadata.get("port", ""))
        pin = str(metadata.get("pin", ""))
        handle = str(metadata.get("handle", ""))
        channel = str(metadata.get("channel_token", ""))
        resolved_symbol = (
            f"{port}/{pin}"
            if port and pin
            else f"{handle}/{channel}"
            if handle and channel
            else handle
            if handle
            else resource.resource_id
        )
        bindings.append(
            {
                "logical_id": resource.resource_id,
                "kind": resource.kind,
                "physical_alias": str(
                    metadata.get("physical_resource", resource.resource_id)
                ),
                "resolved_symbol": resolved_symbol,
                "handle": handle,
                "port": port,
                "pin": pin,
                "channel": channel,
                "peripheral": str(metadata.get("peripheral", "")),
                "physical_pin": str(metadata.get("physical_pin", "")),
                "logical_index": metadata.get("logical_index"),
            }
        )
    return {
        **pin_contract,
        "renderer_contract": RESOURCE_BINDING_RENDERER_CONTRACT,
        "mode": "custom",
        "board": None,
        "bindings": sorted(
            bindings, key=lambda item: (item["kind"], item["logical_id"])
        ),
    }


def HardwareResourceBindingFingerprint_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> str:
    canonical = json.dumps(
        HardwareResourceBindingDescriptor_Get(model, catalog),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def HardwarePreparationFingerprint_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> str:
    """Return the declarative hardware-input fingerprint for one project."""
    data: dict[str, Any] = {
        "mode": model.hardware.mode,
        "mcu": model.mcu,
        "platform_lock": {
            "component": model.hardware.platform_component,
            "version": model.hardware.platform_version,
            "manifest_sha256": model.hardware.platform_manifest_sha256,
        },
        "board": model.board,
        "cubemx_version": model.hardware.cubemx_version,
        "firmware_package": model.hardware.firmware_package,
        "hal_cmsis_source_policy": model.hardware.hal_cmsis_source_policy,
        "resource_assignments": dict(sorted(model.resource_assignments.items())),
        "resource_binding_fingerprint": HardwareResourceBindingFingerprint_Get(
            model, catalog
        ),
    }
    if model.hardware.mode == "board_plugin":
        board = catalog.Component_Get(model.board)
        payload_files = {
            source.relative_to(board.payload_root).as_posix(): _FileDigest_Get(source)
            for source in board.PayloadFiles_Get()
        }
        connection_digest = ""
        if board.board is not None and board.board.connections_file:
            connection_path = board.package_root.joinpath(
                *board.board.connections_file.split("/")
            )
            if connection_path.is_file() and not connection_path.is_symlink():
                connection_digest = _FileDigest_Get(connection_path)
        data["verified_board"] = {
            "id": board.component_id,
            "version": board.version,
            "manifest_sha256": board.ManifestSha256_Get(),
            "verified": bool(board.board and board.board.verified),
            "hardware_root": board.board.hardware_root if board.board else "",
            "ioc_file": board.board.ioc_file if board.board else "",
            "connections_file": (
                board.board.connections_file if board.board else ""
            ),
            "connections_digest": connection_digest,
            "payload_files": payload_files,
        }
    else:
        data["custom_hardware"] = {
            "provider": model.hardware.provider,
            "snapshot_id": model.hardware.snapshot_id,
            "source_digest": model.hardware.source_digest,
            "ioc_file": model.hardware.ioc_file,
            "build_sources": list(model.hardware.build_sources),
            "asm_sources": list(model.hardware.asm_sources),
            "include_dirs": list(model.hardware.include_dirs),
            "defines": list(model.hardware.defines),
            "linker_script": model.hardware.linker_script,
        }
    canonical = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def HardwareAssignmentFingerprint_Get(
    model: ProjectModel, catalog: PluginCatalog
) -> str:
    """Fingerprint every declarative input that can change resource validity."""
    requirements: list[dict[str, Any]] = []
    device_plugins = set(model.DevicePluginIds_Get())
    for component_id in model.ComponentIds_Get():
        manifest = catalog.Component_Get(component_id)
        owner_ids = (
            tuple(
                instance.instance_id
                for instance in model.device_instances
                if instance.plugin == component_id
            )
            if component_id in device_plugins
            else (component_id,)
        )
        for owner_id in owner_ids:
            for requirement in manifest.resource_requirements:
                requirements.append(
                    {
                        "owner": owner_id,
                        "plugin": component_id,
                        "name": requirement.name,
                        "kind": requirement.kind,
                        "required": requirement.required,
                        "mode": requirement.mode.value,
                        "candidates": list(requirement.candidates),
                        "platform_capabilities": list(
                            requirement.platform_capabilities
                        ),
                        "constraints": requirement.constraints,
                        "electrical_constraints": (
                            requirement.electrical_constraints
                        ),
                    }
                )
    value = {
        "mcu": model.mcu,
        "board": model.board,
        "hardware": {
            "mode": model.hardware.mode,
            "provider": model.hardware.provider,
            "snapshot_id": model.hardware.snapshot_id,
            "source_digest": model.hardware.source_digest,
            "ioc_file": model.hardware.ioc_file,
            "platform_component": model.hardware.platform_component,
            "platform_version": model.hardware.platform_version,
            "platform_manifest_sha256": model.hardware.platform_manifest_sha256,
            "cubemx_version": model.hardware.cubemx_version,
            "firmware_package": model.hardware.firmware_package,
            "hal_cmsis_source_policy": model.hardware.hal_cmsis_source_policy,
            "i2c_external_pullup_confirmations": (
                model.hardware.i2c_external_pullup_confirmations
            ),
        },
        "components": list(model.ComponentIds_Get()),
        "devices": [
            {"instance_id": instance.instance_id, "plugin": instance.plugin}
            for instance in model.device_instances
        ],
        "strategies": dict(sorted(model.strategies.items())),
        "modes": {
            slot: list(values) for slot, values in sorted(model.modes.items())
        },
        "requirements": requirements,
        "assignments": dict(sorted(model.resource_assignments.items())),
        "hardware_preparation": HardwarePreparationFingerprint_Get(
            model, catalog
        ),
    }
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def HardwarePreparationMetadata_Render(
    model: ProjectModel, catalog: PluginCatalog
) -> str:
    board = catalog.Component_Get(model.board) if model.board else None
    value = {
        "format_version": 1,
        "fingerprint": HardwarePreparationFingerprint_Get(model, catalog),
        "resource_binding_fingerprint": (
            HardwareResourceBindingFingerprint_Get(model, catalog)
        ),
        "mode": model.hardware.mode,
        "board": model.board,
        "verified": bool(board and board.board and board.board.verified),
        "external_generator_invoked": False,
        "cubemx_version": model.hardware.cubemx_version,
        "firmware_package": model.hardware.firmware_package,
        "hal_cmsis_source_policy": model.hardware.hal_cmsis_source_policy,
        "hardware_location": (
            board.board.hardware_root
            if board is not None and board.board is not None
            else "HardwareGenerated/STM32CubeMX"
        ),
    }
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
