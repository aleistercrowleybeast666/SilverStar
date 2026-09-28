from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import yaml


class EideOwnershipError(ValueError):
    pass


class _EideYamlDumper(yaml.SafeDumper):
    """Render lists with the indentation expected by EIDE and its checks."""

    def increase_indent(
        self, flow: bool = False, indentless: bool = False
    ) -> None:
        return super().increase_indent(flow, False)


def _Document_Load(text: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise EideOwnershipError(f"Invalid EIDE YAML: {error}") from error
    if not isinstance(value, dict):
        raise EideOwnershipError("EIDE YAML root must be an object")
    return value


def _StringList_Normalize(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        raise EideOwnershipError(f"EIDE {field_name} must be a string array")
    return sorted(
        dict.fromkeys(item.replace("\\", "/") for item in value)
    )


def _VirtualFiles_Normalize(value: object) -> list[str]:
    if not isinstance(value, dict):
        raise EideOwnershipError("EIDE virtualFolder must be an object")
    files = value.get("files", [])
    if not isinstance(files, list):
        raise EideOwnershipError("EIDE virtualFolder.files must be an array")
    paths: list[str] = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise EideOwnershipError(
                "EIDE virtualFolder.files entries must contain path"
            )
        paths.append(item["path"].replace("\\", "/"))
    return sorted(dict.fromkeys(paths))


def _Generic_Normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _Generic_Normalize(child)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, list):
        normalized = [_Generic_Normalize(child) for child in value]
        return sorted(
            normalized,
            key=lambda child: json.dumps(
                child, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    return value


def _Target_Normalize(value: object, target_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EideOwnershipError(f"EIDE target {target_name} must be an object")
    preprocess = value.get("cppPreprocessAttrs")
    if not isinstance(preprocess, dict):
        raise EideOwnershipError(
            f"EIDE target {target_name} has no cppPreprocessAttrs"
        )
    toolchain = value.get("toolchain")
    configurations = value.get("toolchainConfigMap")
    if not isinstance(toolchain, str) or not toolchain:
        raise EideOwnershipError(
            f"EIDE target {target_name} has no selected toolchain"
        )
    if not isinstance(configurations, dict) or not isinstance(
        configurations.get(toolchain), dict
    ):
        raise EideOwnershipError(
            f"EIDE target {target_name} has no selected toolchain configuration"
        )
    return {
        "defines": _StringList_Normalize(
            preprocess.get("defineList", []),
            f"targets.{target_name}.defineList",
        ),
        "includes": _StringList_Normalize(
            preprocess.get("incList", []),
            f"targets.{target_name}.incList",
        ),
        "libraries": _StringList_Normalize(
            preprocess.get("libList", []),
            f"targets.{target_name}.libList",
        ),
        "excludes": _StringList_Normalize(
            value.get("excludeList", []),
            f"targets.{target_name}.excludeList",
        ),
        "toolchain": toolchain,
        "toolchain_configuration": deepcopy(configurations[toolchain]),
    }


def EideOwnedFields_Normalize(text: str) -> dict[str, Any]:
    document = _Document_Load(text)
    targets = document.get("targets")
    if not isinstance(targets, dict):
        raise EideOwnershipError("EIDE targets must be an object")
    normalized_targets = {
        target_name: _Target_Normalize(targets[target_name], target_name)
        for target_name in ("Debug", "Release")
        if target_name in targets
    }
    if set(normalized_targets) != {"Debug", "Release"}:
        raise EideOwnershipError("EIDE must contain Debug and Release targets")
    out_dir = document.get("outDir")
    if not isinstance(out_dir, str) or not out_dir:
        raise EideOwnershipError("EIDE outDir must be text")
    return {
        "name": document.get("name"),
        "type": document.get("type"),
        "device_name": document.get("deviceName"),
        "source_directories": _StringList_Normalize(
            document.get("srcDirs", []), "srcDirs"
        ),
        "virtual_files": _VirtualFiles_Normalize(
            document.get("virtualFolder", {})
        ),
        "dependencies": _Generic_Normalize(document.get("dependenceList", [])),
        "output_directory": out_dir.replace("\\", "/"),
        "targets": normalized_targets,
    }


def EideOwnedFingerprint_Get(fields: dict[str, Any]) -> str:
    canonical = json.dumps(
        fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _Differences_Collect(
    previous: object, current: object, prefix: str, values: list[str]
) -> None:
    if isinstance(previous, dict) and isinstance(current, dict):
        for key in sorted(set(previous) | set(current)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in previous or key not in current:
                values.append(child)
            else:
                _Differences_Collect(previous[key], current[key], child, values)
        return
    if previous != current:
        values.append(prefix)


def EideOwnedFields_Compare(
    previous: dict[str, Any], current: dict[str, Any]
) -> tuple[str, ...]:
    differences: list[str] = []
    _Differences_Collect(previous, current, "", differences)
    return tuple(dict.fromkeys(differences))


def EideOwnedFields_Merge(current_text: str, desired_text: str) -> str:
    current = _Document_Load(current_text)
    desired = _Document_Load(desired_text)
    for key in (
        "name",
        "type",
        "deviceName",
        "srcDirs",
        "virtualFolder",
        "dependenceList",
        "outDir",
    ):
        current[key] = deepcopy(desired.get(key))
    current_targets = current.setdefault("targets", {})
    desired_targets = desired.get("targets", {})
    if not isinstance(current_targets, dict) or not isinstance(
        desired_targets, dict
    ):
        raise EideOwnershipError("EIDE targets must be objects")
    for target_name in ("Debug", "Release"):
        desired_target = desired_targets.get(target_name)
        if not isinstance(desired_target, dict):
            raise EideOwnershipError(
                f"Desired EIDE target {target_name} is missing"
            )
        current_target = current_targets.get(target_name)
        if not isinstance(current_target, dict):
            current_target = {}
            current_targets[target_name] = current_target
        for key in (
            "cppPreprocessAttrs",
            "excludeList",
            "toolchain",
            "toolchainConfigMap",
        ):
            current_target[key] = deepcopy(desired_target.get(key))
    rendered = yaml.dump(
        current,
        Dumper=_EideYamlDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    return (
        "# AUTO-GENERATED BUILD FIELDS BY SILVERSTAR_FCCG.\n"
        "# EIDE UI, uploader, debugger, and status fields are preserved.\n"
        + rendered
    )
