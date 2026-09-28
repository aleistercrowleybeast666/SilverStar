"""Explicitly synthetic parameter-package fixtures, never a real-log gate."""

import json
import struct
from dataclasses import replace
from pathlib import Path

from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import START_TIMESTAMP_US, Event_Payload, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    DESCRIPTOR_RECORD_TYPE,
    IMU_RECORD_TYPE,
    _CalibrationNonePayload_Build,
    _DescriptorPayload_Build,
    _ImuPayload_Build,
    _Package_Write,
    _PackageFiles_Build,
    _SemanticsDocument_Build,
)


def FirmwareSets_Build(overrides=None):
    groups = []
    for plugin in builtin_registry().algorithms:
        name = plugin.metadata.plugin_id.rsplit(".", 1)[-1]
        contract = json.loads(
            (
                Path(__file__).parent / "fixtures/parameter_contracts" / f"{name}_fccg_1_2.json"
            ).read_text(encoding="utf8")
        )
        group = {
            "component": plugin.metadata.firmware_component_ids[0],
            "schema_id": contract["schema_id"],
            "manifest_sha256": "a" * 64,
            "parameters": [],
        }
        for p in contract["parameters"]:
            overrides_for_plugin = (overrides or {}).get(name, {})
            value = overrides_for_plugin.get(p["id"], p["default"])
            # These revision-0 synthetic packages model the old KF6 firmware.
            if (name == "kf6" and p["id"] == "gnss_integrity_enable" and
                    p["id"] not in overrides_for_plugin):
                value = 0
            if p["type"] == "float":
                value = struct.unpack("<f", struct.pack("<f", value))[0]
            group["parameters"].append(
                {
                    "id": p["id"],
                    "value": value,
                    "unit": p["unit"],
                    "representation": p["representation"],
                    "storage_type": "float32" if p["type"] == "float" else "int32",
                    "description": p["description"]["en_US"],
                }
            )
        groups.append(group)
    return groups


def ParameterPackage_Open(tmp_path, groups=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    semantics = _SemanticsDocument_Build()
    semantics["firmware_algorithm_parameters"] = FirmwareSets_Build() if groups is None else groups
    semantics["algorithms"] = [g["component"] for g in semantics["firmware_algorithm_parameters"]]
    files, hashes = _PackageFiles_Build(semantics_document=semantics)
    package, _ = _Package_Write(tmp_path / "SYNTHETIC_actual.ssdecoder", files=files)
    builder = SyntheticSslogBuilder()
    builder.Record_Add(
        DESCRIPTOR_RECORD_TYPE, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US - 3
    )
    builder.Record_Add(0x17, _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2)
    builder.Record_Add(0x02, Event_Payload(3), START_TIMESTAMP_US)
    builder.Record_Add(
        IMU_RECORD_TYPE,
        _ImuPayload_Build(1, 0, START_TIMESTAMP_US + 1, (1, 2, 3)),
        START_TIMESTAMP_US + 1,
    )
    log = builder.File_Write(tmp_path / "SYNTHETIC_actual.sslog")
    return LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(tmp_path / "cache")
    ).Open(LogOpenRequest(log_path=log, decoder_package_path=package))


def SyntheticParameters_Attach(dataset, tmp_path, overrides=None):
    # Unit-level combination of existing synthetic algorithm inputs and a context
    # actually loaded through the production 1.2 package path. No real-log claim.
    context = ParameterPackage_Open(
        tmp_path, FirmwareSets_Build(overrides)
    ).dataset.semantic_context
    return replace(dataset, semantic_context=context)
