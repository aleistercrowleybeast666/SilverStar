"""EIDE host build hooks. No target runtime or hardware operations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .contract import DiagnosticError, Require
from .project_descriptor import (
    ProjectBindingResult,
    ProjectDescriptor_Begin,
    ProjectDescriptor_Bind,
    ProjectDescriptor_Resolve,
)


def EideHooks_Create(host_command=None):
    """Use EIDE's expanded paths, including spaces and the selected target."""
    if host_command is None:
        host_command = ([sys.executable] if getattr(sys, "frozen", False) else
                        [sys.executable, "-X", "utf8", "-B",
                         str(Path(__file__).resolve().parents[2] / "main.py")])

    def command(arguments):
        # Quote every argument: EIDE expands macros AFTER this command is made.
        # list2cmdline alone does not quote a macro that later contains spaces.
        quoted = []
        for argument in [*host_command, "--diagnostics-eide", *arguments]:
            encoded = subprocess.list2cmdline([str(argument)])
            quoted.append(encoded if encoded.startswith('"') else f'"{encoded}"')
        return " ".join(quoted)

    common = ["--project", "${ProjectRoot}/Flight.ssdiag"]
    return {
        "beforeBuildTasks": [{
            "name": "SilverStar diagnostics pending",
            "command": command(["begin", *common]),
            "abortAfterFailed": True,
        }],
        "afterBuildTasks": [{
            "name": "SilverStar diagnostics bind",
            "command": command(["bind", *common, "--elf",
                                "${OutDir}/${ProjectName}.elf"]),
            "abortAfterFailed": True,
        }],
    }


def EideHooks_Merge(options, hooks=None):
    """Replace only our named hooks, retaining user tasks and compiler flags."""
    from copy import deepcopy
    value = deepcopy(options)
    hooks = EideHooks_Create() if hooks is None else hooks
    names = {task["name"] for tasks in hooks.values() for task in tasks}
    for key, additions in hooks.items():
        retained = [task for task in value.get(key, []) if task.get("name") not in names]
        value[key] = additions + retained if key == "beforeBuildTasks" else retained + additions
    return value


def EideDiagnostics_Bind(project, elf):
    """Publish only an unchanged, strictly matched successful ELF/HEX pair."""
    project = Path(project).absolute()
    ProjectDescriptor_Begin(project)
    try:
        root = project.parent.resolve()
        elf = Path(elf).absolute()
        Require(not elf.is_symlink() and elf.resolve().is_relative_to(root),
                "EIDE ELF escaped project root")
        Require(elf.suffix == ".elf" and elf.is_file(), "Completed EIDE ELF missing")
        image = elf.with_suffix(".hex")
        Require(image.is_file() and not image.is_symlink(), "Matching EIDE HEX missing")

        def hashes():
            result = {}
            for path in (elf, image):
                Require(path.stat().st_size <= 33554432, "EIDE artifact exceeds 32 MiB")
                with path.open("rb") as stream:
                    data = stream.read(33554433)
                Require(len(data) <= 33554432, "EIDE artifact exceeds 32 MiB")
                result[path.name] = hashlib.sha256(data).hexdigest()
            return result

        before = hashes()
        state, detail = ProjectDescriptor_Bind(project, elf, image_file=image.name)
        Require(state is ProjectBindingResult.Ready, detail)
        firmware = ProjectDescriptor_Resolve(project, elf)
        Require(before == hashes(), "EIDE artifacts changed during binding")
        return dict(diagnostics="ready", descriptor=str(project),
                    elf_sha256=firmware.sha256, hex_sha256=before[image.name],
                    image_contract_version=2, hardware_verified=False)
    except (DiagnosticError, OSError):
        # A failed post-build command must never leave an apparently fresh ready entry.
        ProjectDescriptor_Begin(project)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("begin", "bind"))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--elf", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "begin":
            ProjectDescriptor_Begin(args.project)
            result = dict(diagnostics="pending_build", hardware_verified=False)
        else:
            Require(args.elf is not None, "An explicit EIDE ELF is required")
            result = EideDiagnostics_Bind(args.project, args.elf)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (DiagnosticError, OSError) as exc:
        print(f"EIDE diagnostics failed: {exc}", file=sys.stderr)
        return 1
