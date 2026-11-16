"""Copy this task's enumerated evidence, never generated firmware or user input.

No cleanup. Existing archived bytes must match; a different source is an error.
All path mappings and raw SHA-256 identities are retained in evidence-index.json.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / ".work/platform-finish-20261116/contracts"
OUT = Path(__file__).resolve().parent


def main():
    records = []

    def copy(source, relative):
        raw = source.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Evidence file exceeds repository limit: " + str(source))
        destination = OUT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and destination.read_bytes() != raw:
            raise ValueError("Refusing to overwrite different archived bytes: " + str(destination))
        destination.write_bytes(raw)
        records.append({"source": source.relative_to(ROOT).as_posix(),
                        "archive": destination.relative_to(OUT).as_posix(),
                        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})

    for source in sorted(WORK.iterdir()):
        if source.is_file() and source.suffix in (".log", ".exit", ".xml", ".json"):
            copy(source, Path("runs") / source.name)
    for name in ("build-a", "build-b", "build-c", "build-d", "build-d-extra", "build-e",
                 "build-e-extra", "build-e19-a", "build-e19-b"):
        directory = WORK / name
        if not (directory / "input-stability.json").exists():
            raise ValueError("Build run still incomplete: " + name)
        for source in sorted(directory.iterdir()):
            if source.is_file():
                copy(source, Path(name) / source.name)
    for name in ("logger-before-v2", "logger-after", "logger-final-c", "existing-host", "mission-runtime-b"):
        for source in sorted((WORK / name).rglob("*")):
            if source.is_file() and source.name in ("compiler-receipt.json", "compile-receipt.json", "compile.log", "receipt.json"):
                copy(source, Path("host-receipts") / name / source.relative_to(WORK / name))
    for label, directory in (("pre", "pre-generated"), ("a", "post-generated-a"), ("b", "post-generated-b"),
                             ("c", "final-generated-c"), ("d", "final-generated-d"), ("e", "final-generated-e")):
        base = WORK / directory
        project = base / "f4/Flight_Controller"
        copy(base / "generation.json", Path("configurations") / (label + ".json"))
        copy(project / "APP/Src/logger_task.c", Path("compiled-inputs") / (label + "-logger_task.c.txt"))
        copy(project / "Generated/Src/project_log_decoder_profile.c",
             Path("compiled-inputs") / (label + "-project_log_decoder_profile.c.txt"))
        if label in ("b", "e"):
            for config in ("Release", "Debug"):
                build = project / "build/FCCG/SilverStar_F407" / config
                for name in ("memory-report.json", "stack-budget.json"):
                    copy(build / name, Path(label + "-artifacts") / config / name)
    for label in ("a", "b"):
        project = ROOT / (".work/pf1117/contract-e19-" + label) / "Flight_Controller"
        for relative in ("Devices/Telemetry/SX1278/Adapter/Src/sx1278_telemetry_adapter.c",
                         "Generated/Inc/air_link_config.h"):
            copy(project / relative, Path("compiled-inputs") / ("e19-" + label + "-" + Path(relative).name + ".txt"))
        for config in ("Release", "Debug"):
            build = project / "build/FCCG/SilverStar_F407" / config
            names = ("memory-report.json", "stack-budget.json") if label == "b" else ("memory-report.json",)
            for name in names:
                copy(build / name, Path("e19-" + label + "-artifacts") / config / name)
    source = WORK / "e19-import-review.diff.txt"
    copy(source, Path("runs") / source.name)
    (OUT / "evidence-index.json").write_bytes((json.dumps(records, indent=2) + "\n").encode())
    print("Archived", len(records), "files;", sum(row["bytes"] for row in records), "bytes")


if __name__ == "__main__":
    main()
