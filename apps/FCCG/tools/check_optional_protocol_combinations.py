from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = WORKSPACE_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from silverstar_fccg.app.service import FccgService  # noqa: E402
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve  # noqa: E402
from silverstar_fccg.project.model import PROTOCOL_CATEGORIES  # noqa: E402


PROTOCOL_COMBINATIONS = (
    (True, True, True),
    (True, True, False),
    (True, False, True),
    (True, False, False),
    (False, True, True),
    (False, True, False),
    (False, False, True),
    (False, False, False),
)
PROTOCOL_TASK_SYMBOLS = {
    "telemetry": (
        "AppTask_Telemetry",
        "s_telemetry_stack",
        "s_telemetry_task_control",
    ),
    "maintenance": (
        "AppTask_Serial",
        "s_serial_stack",
        "s_serial_task_control",
    ),
    "logging": (
        "AppTask_Logger",
        "s_logger_stack",
        "s_logger_task_control",
    ),
}


def _CombinationName_Get(
    telemetry: bool, maintenance: bool, logging: bool
) -> str:
    return (
        f"T{int(telemetry)}_M{int(maintenance)}_L{int(logging)}"
    )


def _OutputRoot_Resolve(value: str) -> Path:
    output_root = Path(value).resolve(strict=False)
    acceptance_root = (WORKSPACE_ROOT / "tests").resolve()
    try:
        output_root.relative_to(acceptance_root)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Acceptance output must remain below the repository tests directory"
        ) from error
    return output_root


def _Project_Generate(
    service: FccgService,
    output_root: Path,
    combination: tuple[bool, bool, bool],
) -> dict[str, Any]:
    telemetry, maintenance, logging = combination
    name = _CombinationName_Get(telemetry, maintenance, logging)
    model = service.ReferenceProject_Create(name)
    for category, enabled in zip(
        PROTOCOL_CATEGORIES, combination, strict=True
    ):
        if not enabled:
            model.protocols[category] = None
    model = service.ProjectConfiguration_Reconcile(model).model
    project_root = output_root / name
    service.Project_Save(model, project_root, confirm_dangerous=True)
    graph = SourceGraph_Resolve(model, service.catalog)
    return {
        "name": name,
        "project_root": str(project_root),
        "telemetry": telemetry,
        "maintenance": maintenance,
        "logging": logging,
        "source_count": len(graph.sources),
        "asm_source_count": len(graph.asm_sources),
        "builds": {},
    }


def _Project_Build(
    entry: dict[str, Any],
    configuration: str,
    make_command: str,
    nm_command: str,
    jobs: int,
) -> tuple[str, str, dict[str, Any]]:
    project_root = Path(str(entry["project_root"]))
    command = (
        make_command,
        "-B",
        f"-j{jobs}",
        "TARGET_PROFILE=SilverStar_F407",
        f"CONFIG={configuration}",
        "all",
    )
    result = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    audit_errors: list[str] = []
    task_symbol_audit: dict[str, dict[str, Any]] = {}
    nm_output = ""
    if result.returncode == 0:
        elf_candidates = tuple(
            (project_root / "build" / "FCCG" / "SilverStar_F407" /
             configuration).glob("*.elf")
        )
        if len(elf_candidates) != 1:
            audit_errors.append(
                "expected exactly one ELF artifact for task-symbol audit"
            )
        else:
            nm_result = subprocess.run(
                (nm_command, "-a", str(elf_candidates[0])),
                cwd=project_root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            nm_output = nm_result.stdout + nm_result.stderr
            if nm_result.returncode != 0:
                audit_errors.append(
                    f"task-symbol audit returned {nm_result.returncode}"
                )
            else:
                symbol_names = {
                    line.rsplit(None, 1)[-1]
                    for line in nm_result.stdout.splitlines()
                    if line.strip()
                }
                for category, expected_symbols in PROTOCOL_TASK_SYMBOLS.items():
                    enabled = bool(entry[category])
                    present = tuple(
                        symbol
                        for symbol in expected_symbols
                        if symbol in symbol_names
                    )
                    task_symbol_audit[category] = {
                        "enabled": enabled,
                        "expected_symbols": list(expected_symbols),
                        "present_symbols": list(present),
                    }
                    if enabled and len(present) != len(expected_symbols):
                        audit_errors.append(
                            f"{category} task allocation symbols are incomplete"
                        )
                    if not enabled and present:
                        audit_errors.append(
                            f"{category} disabled task still allocates symbols"
                        )
    log_path = project_root / ".fccg" / (
        f"optional-protocol-{configuration.casefold()}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        result.stdout + result.stderr + nm_output +
        "".join(f"TASK_SYMBOL_AUDIT_ERROR|{item}\n" for item in audit_errors),
        encoding="utf-8",
    )
    return_code = result.returncode if result.returncode != 0 else (
        3 if audit_errors else 0
    )
    return (
        str(entry["name"]),
        configuration,
        {
            "command": list(command),
            "return_code": return_code,
            "log": str(log_path.relative_to(WORKSPACE_ROOT)),
            "task_symbol_audit": task_symbol_audit,
            "task_symbol_audit_errors": audit_errors,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and optionally build all eight optional-Protocol "
            "combinations for the official SS0.5/F407 target."
        )
    )
    parser.add_argument(
        "--output-root",
        type=_OutputRoot_Resolve,
        default=_OutputRoot_Resolve(
            str(WORKSPACE_ROOT / "tests" / "acceptance_optional_protocols")
        ),
    )
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--configuration",
        action="append",
        choices=("Release", "Debug"),
        dest="configurations",
    )
    parser.add_argument("--make-command", default="mingw32-make")
    parser.add_argument("--nm-command", default="arm-none-eabi-nm")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--parallel-builds", type=int, default=1)
    arguments = parser.parse_args()
    if arguments.jobs < 1 or arguments.parallel_builds < 1:
        parser.error("--jobs and --parallel-builds must be positive")
    configurations = tuple(arguments.configurations or ("Release",))

    service = FccgService(WORKSPACE_ROOT)
    output_root = Path(arguments.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    entries = [
        _Project_Generate(service, output_root, combination)
        for combination in PROTOCOL_COMBINATIONS
    ]

    if arguments.build:
        jobs = [
            (entry, configuration)
            for entry in entries
            for configuration in configurations
        ]
        with ThreadPoolExecutor(
            max_workers=arguments.parallel_builds
        ) as executor:
            results = tuple(
                executor.map(
                    lambda item: _Project_Build(
                        item[0],
                        item[1],
                        arguments.make_command,
                        arguments.nm_command,
                        arguments.jobs,
                    ),
                    jobs,
                )
            )
        entries_by_name = {str(entry["name"]): entry for entry in entries}
        for name, configuration, result in results:
            entries_by_name[name]["builds"][configuration] = result

    summary = {
        "schema": "silverstar.optional-protocol-acceptance/1.0",
        "target": "SilverStar_F407",
        "entries": entries,
    }
    summary_path = output_root / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return int(
        any(
            build["return_code"] != 0
            for entry in entries
            for build in entry["builds"].values()
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
