from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np

from silverstar_flp.analysis.overview import FlightSummary_Build
from silverstar_flp.export.service import (
    ExportLanguage,
    ExportOptions,
    ExportTheme,
    FlightExporter,
)
from silverstar_flp.log_open import (
    LogOpenCoordinator,
    LogOpenRequest,
    LogOpenResult,
    LogOpenSourceMode,
)
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import PluginRegistry, builtin_registry


def _Json_Default(value: Any) -> Any:
    if hasattr(value, "ToDict"):
        return value.ToDict()
    if is_dataclass(value):
        return {
            item.name: getattr(value, item.name)
            for item in fields(value)
        }
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex(" ")
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "value"):
        return value.value
    raise TypeError(type(value).__name__)


def _Dataset_Parse(options: argparse.Namespace) -> tuple[PluginRegistry, LogOpenResult]:
    registry = builtin_registry()
    coordinator = LogOpenCoordinator(registry)
    result = coordinator.Open(
        LogOpenRequest(
            log_path=options.path,
            decoder_package_path=options.decoder,
            auto_find=bool(options.auto_find),
            task_directory=options.path.parent if options.auto_find else None,
            source_mode=LogOpenSourceMode.CLI,
        )
    )
    return registry, result


def _Algorithm_Resolve(registry: PluginRegistry, requested: str):
    normalized = requested.strip().casefold().replace("-", "_")
    matches = []
    for plugin in registry.algorithms:
        metadata = plugin.metadata
        aliases = {
            metadata.plugin_id.casefold(),
            metadata.plugin_id.rsplit(".", 1)[-1].casefold(),
            metadata.display_name.casefold(),
            metadata.display_name.casefold().replace(" ", "_"),
        }
        if normalized in aliases:
            matches.append(plugin)
    if not matches:
        raise ValueError(f"offline_algorithm_not_found:{requested}")
    if len(matches) != 1:
        raise ValueError(f"offline_algorithm_ambiguous:{requested}")
    return matches[0]


def _Command_Inspect(options: argparse.Namespace) -> int:
    registry, open_result = _Dataset_Parse(options)
    dataset = open_result.dataset
    semantic_context = dataset.semantic_context
    algorithms = []
    for plugin in registry.algorithms:
        availability = plugin.availability(dataset)
        configuration = plugin.ConfigurationAvailability_Get(
            dataset,
            input_available=availability.available,
        )
        algorithms.append(
            {
                "plugin_id": plugin.metadata.plugin_id,
                "display_name": plugin.metadata.display_name,
                "firmware_member": configuration.firmware_member,
                "recorded_output_available": configuration.recorded_output_available,
                "recorded_configuration_available": configuration.recorded_available,
                "offline_available": configuration.offline_available,
                "missing_recorded_parameters": configuration.missing_recorded_parameters,
                "fidelity": availability.fidelity,
                "warnings": availability.warnings,
                "input_contract": {
                    "required_records": plugin.metadata.required_records,
                    "optional_records": plugin.metadata.optional_records,
                    "required_semantic_roles": (
                        plugin.metadata.required_semantic_roles
                    ),
                    "optional_semantic_roles": (
                        plugin.metadata.optional_semantic_roles
                    ),
                    "cadence": dict(plugin.metadata.cadence_contract),
                    "gap_tolerance": dict(
                        plugin.metadata.gap_tolerance_contract
                    ),
                    "parameter_sources": dict(
                        plugin.metadata.parameter_source_contract
                    ),
                    "coordinate_frame": dict(
                        plugin.metadata.coordinate_frame_contract
                    ),
                    "exact_validation_reference": (
                        plugin.metadata.exact_validation_reference or None
                    ),
                },
            }
        )
    payload = {
        "source_path": dataset.source_path,
        "file_size": dataset.file_size,
        "decoder": {
            "package_path": open_result.source_package_path,
            "cache_reference": open_result.cache_reference.to_dict(),
            "match_mode": open_result.match_mode,
            "package_sha256": open_result.package.package_sha256,
            "generation_profile_sha256": (
                open_result.package.generation_profile_sha256
            ),
        },
        "semantic_context": (
            semantic_context.ToDict() if semantic_context is not None else None
        ),
        "header": dict(dataset.header),
        "diagnostics": dataset.diagnostics.to_dict(),
        "data_quality": (
            dataset.data_quality.ToDict()
            if dataset.data_quality is not None
            else None
        ),
        "record_counts": {
            name: len(records) for name, records in dataset.records.items()
        },
        "channels": {
            name: {
                "samples": series.count,
                "unit": series.unit,
                "quantity": series.quantity,
                "source": series.source,
            }
            for name, series in dataset.series.items()
        },
        "offline_algorithms": algorithms,
        "overview": FlightSummary_Build(dataset),
    }
    print(json.dumps(payload, default=_Json_Default, ensure_ascii=False, indent=2))
    return 0


def _Command_Replay(options: argparse.Namespace) -> int:
    registry, open_result = _Dataset_Parse(options)
    dataset = open_result.dataset
    plugin = _Algorithm_Resolve(registry, options.algorithm)
    availability = plugin.availability(dataset, options.source)
    configuration = plugin.ConfigurationAvailability_Get(
        dataset,
        input_available=availability.available,
    )
    requested_mode = options.mode
    if requested_mode is None:
        requested_mode = "recorded" if configuration.recorded_available else "offline"
    if requested_mode == "recorded" and not configuration.recorded_available:
        missing = ",".join(configuration.missing_recorded_parameters)
        raise ValueError(f"recorded_configuration_unavailable:{missing}")
    if requested_mode == "offline" and not configuration.offline_available:
        raise ValueError("offline_replay_unavailable")
    parameters: dict[str, float] = (
        dict(configuration.recorded_parameters)
        if requested_mode == "recorded"
        else dict(configuration.offline_parameters)
    )
    for assignment in options.parameter:
        key, separator, value = assignment.partition("=")
        if not separator:
            raise ValueError(f"invalid_parameter_assignment:{assignment}")
        parameters[key] = float(value)
    mode = (
        ReplayMode.RECORDED_CONFIGURATION
        if requested_mode == "recorded"
        else ReplayMode.OFFLINE
    )
    result = plugin.run(
        dataset,
        ReplayRequest(mode=mode, input_source=options.source, parameters=parameters),
    )
    payload = {
        "algorithm_id": result.algorithm_id,
        "algorithm_version": result.algorithm_version,
        "firmware_member": configuration.firmware_member,
        "recorded_output_available": configuration.recorded_output_available,
        "mode": mode,
        "provenance": result.provenance,
        "fidelity": result.fidelity,
        "warnings": result.warnings,
        "parameters": dict(result.parameters),
        "diagnostics": dict(result.diagnostics),
        "channels": {name: series.count for name, series in result.channels.items()},
    }
    print(json.dumps(payload, default=_Json_Default, ensure_ascii=False, indent=2))
    if options.output is not None:
        manifest = FlightExporter(registry).export(
            dataset,
            options.output,
            options=ExportOptions(
                language=ExportLanguage(options.language),
                theme=ExportTheme(options.theme),
            ),
            algorithm_results={plugin.metadata.plugin_id: result},
        )
        print(f"exported={len(manifest.files)} directory={manifest.output_directory}")
    return 0


def _Command_Export(options: argparse.Namespace) -> int:
    registry, open_result = _Dataset_Parse(options)
    manifest = FlightExporter(registry).export(
        open_result.dataset,
        options.output,
        options=ExportOptions(
            language=ExportLanguage(options.language),
            theme=ExportTheme(options.theme),
            include_attitude_gif=not options.no_gif,
        ),
    )
    print(f"exported={len(manifest.files)} directory={manifest.output_directory}")
    return 0


def _Command_Gui(options: argparse.Namespace) -> int:
    from silverstar_flp.app.application import main as gui_main

    arguments: list[str] = []
    if options.path is not None:
        arguments.append(str(options.path))
    if options.decoder is not None:
        arguments.extend(("--decoder", str(options.decoder)))
    if options.auto_find:
        arguments.append("--auto-find")
    return gui_main(arguments)


def _DecoderArguments_Add(parser: argparse.ArgumentParser, *, required: bool) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--decoder", type=Path, help="exact .ssdecoder package")
    group.add_argument(
        "--auto-find",
        action="store_true",
        help="bounded search for one exact log/package pair",
    )


def _Parser_Create() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sslog", description="SilverStar SSLOG0 tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="parse and print log metadata")
    inspect_parser.add_argument("path", type=Path)
    _DecoderArguments_Add(inspect_parser, required=True)
    inspect_parser.set_defaults(handler=_Command_Inspect)

    replay_parser = subparsers.add_parser("replay", help="run a navigation replay")
    replay_parser.add_argument("path", type=Path)
    _DecoderArguments_Add(replay_parser, required=True)
    replay_parser.add_argument("--algorithm", default="pure_ins")
    replay_parser.add_argument(
        "--mode",
        choices=("recorded", "offline"),
        help="defaults to recorded only when every recorded parameter is present",
    )
    replay_parser.add_argument(
        "--source",
        choices=("recorded_inertial_increment", "corrected_imu"),
        default="recorded_inertial_increment",
    )
    replay_parser.add_argument("--parameter", action="append", default=[], metavar="KEY=VALUE")
    replay_parser.add_argument("--output", type=Path)
    replay_parser.add_argument("--language", choices=("zh_CN", "en_US"), default="zh_CN")
    replay_parser.add_argument("--theme", choices=("light", "dark"), default="light")
    replay_parser.set_defaults(handler=_Command_Replay)

    export_parser = subparsers.add_parser("export", help="export all available channels")
    export_parser.add_argument("path", type=Path)
    export_parser.add_argument("output", type=Path)
    _DecoderArguments_Add(export_parser, required=True)
    export_parser.add_argument("--language", choices=("zh_CN", "en_US"), default="zh_CN")
    export_parser.add_argument("--theme", choices=("light", "dark"), default="light")
    export_parser.add_argument("--no-gif", action="store_true")
    export_parser.set_defaults(handler=_Command_Export)

    gui_parser = subparsers.add_parser("gui", help="open the desktop application")
    gui_parser.add_argument("path", nargs="?", type=Path)
    _DecoderArguments_Add(gui_parser, required=False)
    gui_parser.set_defaults(handler=_Command_Gui)
    return parser


def main(arguments: list[str] | None = None) -> int:
    parser = _Parser_Create()
    try:
        options = parser.parse_args(arguments)
        return int(options.handler(options))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
