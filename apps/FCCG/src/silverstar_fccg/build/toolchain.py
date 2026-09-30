from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


def ArmGnuSubtoolPaths_Derive(compiler_path: str) -> dict[str, str]:
    compiler = Path(compiler_path).resolve()
    suffix = compiler.suffix
    values: dict[str, str] = {}
    for tool_id, command in (
        ("objcopy", "arm-none-eabi-objcopy"),
        ("size", "arm-none-eabi-size"),
    ):
        candidate = compiler.with_name(f"{command}{suffix}")
        if candidate.is_file():
            values[tool_id] = str(candidate)
    return values


@dataclass(frozen=True, slots=True)
class ToolchainResult:
    tool_id: str
    command: str
    path: str
    version: str
    available: bool
    compatible: bool
    target: str = ""


class ToolchainDetector:
    TOOL_COMMANDS: ClassVar[dict[str, str]] = {
        "compiler": "arm-none-eabi-gcc",
        "make": "mingw32-make",
        "host_gcc": "gcc",
    }
    VERSION_MARKERS: ClassVar[dict[str, tuple[str, ...]]] = {
        "compiler": ("arm-none-eabi-gcc",),
        "make": ("gnu make",),
        "host_gcc": ("gcc",),
    }

    @staticmethod
    def _CommonCandidates_Get(tool_id: str, command: str) -> tuple[Path, ...]:
        candidates: list[Path] = []
        suffix = ".exe" if os.name == "nt" else ""
        executable = command + suffix
        if os.name == "nt":
            for root in (
                Path("C:/msys64/ucrt64/bin"),
                Path("C:/msys64/mingw64/bin"),
                Path("C:/mingw64/bin"),
            ):
                candidates.append(root / executable)
            if tool_id == "make":
                candidates.append(Path("C:/msys64/usr/bin/make.exe"))
            if tool_id == "compiler":
                for program_root in (
                    Path("C:/Program Files (x86)/Arm GNU Toolchain arm-none-eabi"),
                    Path("C:/Program Files/Arm GNU Toolchain arm-none-eabi"),
                ):
                    if program_root.is_dir():
                        candidates.extend(
                            path / "bin" / executable
                            for path in sorted(program_root.glob("*"), reverse=True)
                            if path.is_dir()
                        )
        return tuple(dict.fromkeys(candidates))

    @classmethod
    def _Path_Find(cls, tool_id: str, command: str, override: str) -> str:
        if override:
            candidate = Path(override).resolve()
            return str(candidate) if candidate.is_file() else ""
        discovered = shutil.which(command)
        if not discovered and tool_id == "make":
            discovered = shutil.which("make")
        if discovered:
            return str(Path(discovered).resolve())
        for candidate in cls._CommonCandidates_Get(tool_id, command):
            if candidate.is_file():
                return str(candidate.resolve())
        return ""

    def Detect(
        self,
        overrides: dict[str, str] | None = None,
        progress_callback: Callable[[int, int, str, bool], None] | None = None,
    ) -> tuple[ToolchainResult, ...]:
        overrides = overrides or {}
        results: list[ToolchainResult] = []
        total = len(self.TOOL_COMMANDS)
        for current, (tool_id, command) in enumerate(
            self.TOOL_COMMANDS.items(), start=1
        ):
            if progress_callback is not None:
                progress_callback(current, total, tool_id, False)
            override = overrides.get(tool_id, "")
            path = self._Path_Find(tool_id, command, override)
            if not path:
                results.append(
                    ToolchainResult(tool_id, command, override, "", False, False)
                )
                if progress_callback is not None:
                    progress_callback(current, total, tool_id, True)
                continue
            version = self._Version_Get(path)
            compatible = self._Version_Compatible(tool_id, version)
            target = ""
            if tool_id == "compiler":
                target = self._Target_Get(path)
                compatible = (
                    compatible
                    and target.casefold() == "arm-none-eabi"
                    and len(ArmGnuSubtoolPaths_Derive(path)) == 2
                )
            elif tool_id == "host_gcc":
                target = self._Target_Get(path)
                compatible = compatible and bool(
                    re.search(r"(?i)(mingw|windows|cygwin|msys)", target)
                )
            results.append(
                ToolchainResult(
                    tool_id, command, path, version, True, compatible, target
                )
            )
            if progress_callback is not None:
                progress_callback(current, total, tool_id, True)
        return tuple(results)

    @classmethod
    def _Version_Compatible(cls, tool_id: str, version: str) -> bool:
        normalized = version.casefold()
        markers = cls.VERSION_MARKERS.get(tool_id, ())
        return bool(normalized) and all(marker in normalized for marker in markers)

    @staticmethod
    def _Version_Get(path: str) -> str:
        try:
            result = subprocess.run(
                [path, "--version"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        output = (result.stdout or result.stderr).strip().splitlines()
        return output[0].strip() if output else ""

    @staticmethod
    def _Target_Get(path: str) -> str:
        try:
            result = subprocess.run(
                [path, "-dumpmachine"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if result.returncode != 0:
            return ""
        output = (result.stdout or result.stderr).strip().splitlines()
        return output[0].strip() if output else ""
