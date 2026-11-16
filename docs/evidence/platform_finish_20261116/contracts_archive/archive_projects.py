"""Preserve two immutable, complete generated projects; never delete sources."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DESTINATION = ROOT / "dist/pf1117-evidence"
CASES = (
    ("f407-default-e-20261117",
     ".work/platform-finish-20261116/contracts/final-generated-e/f4/Flight_Controller",
     "docs/evidence/platform_finish_20261116/contracts/runs/final-artifact-summary.json"),
    ("f407-e19-b-20261117", ".work/pf1117/contract-e19-b/Flight_Controller",
     "docs/evidence/platform_finish_20261116/contracts/runs/e19-final-artifact-summary.json"),
)


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return digest(stream)


def scan(source):
    files, directories = {}, []
    for directory, names, filenames in os.walk(source, followlinks=False):
        current = Path(directory)
        for name in names + filenames:
            path = current / name
            info = path.lstat()
            if path.is_symlink() or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("Reparse point is outside this archive contract: " + str(path))
        if current != source:
            directories.append(current.relative_to(source).as_posix())
        for name in filenames:
            path = current / name
            before = path.stat()
            value = file_hash(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed while hashing: " + str(path))
            files[path.relative_to(source).as_posix()] = {"bytes": after.st_size, "sha256": value}
    return dict(sorted(files.items())), sorted(directories)


def write_new(path, value):
    with path.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for label, _, _ in CASES:
        if (DESTINATION / label).exists() or (OUT / (label + ".json")).exists():
            raise ValueError("Refusing to overwrite an existing archive/receipt: " + label)
    receipts = []
    for label, relative, summary_path in CASES:
        source = (ROOT / relative).resolve(strict=True)
        source.relative_to((ROOT / ".work").resolve(strict=True))
        if source.is_symlink() or source.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Source root must be an ordinary task-owned directory")
        destination = DESTINATION / label
        destination.mkdir(parents=False, exist_ok=False)
        archive = destination / "Flight_Controller.zip"
        ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", str(archive)],
                                 cwd=ROOT, check=False)
        if ignored.returncode != 0:
            raise ValueError("Archive must be outside Git product inputs")
        marker = {"kind": "formal_software_evidence_do_not_cleanup", "owner": "/root/silverstar_finish",
                  "source": str(source), "source_must_be_retained_until_root_acceptance": True,
                  "hardware_tested": False, "zip_is_not_a_git_product": True,
                  "note": "Preserve this entire directory. No permission to delete original sources or other work."}
        write_new(destination / "PRESERVE_EVIDENCE.json", marker)
        files, directories = scan(source)
        assert "Makefile" in files and "SilverStar.ssproject" in files
        assert any(name.endswith(".ssdecoder") for name in files)
        summary = json.loads((ROOT / summary_path).read_bytes())
        proven = {}
        for config, data in summary["configurations"].items():
            build = "build/FCCG/SilverStar_F407/" + config + "/"
            for name, value in data["artifact_hashes"].items():
                if files[build + name]["sha256"] != value:
                    raise ValueError("Compiled artifact differs from verified epoch: " + build + name)
            for extension in (".elf", ".bin", ".map", ".su"):
                if not any(name.startswith(build) and name.endswith(extension) for name in files):
                    raise ValueError("Missing final configuration artifact: " + config + extension)
            proven[config] = len(data["artifact_hashes"])
        inventory = {"source": str(source), "archive_root": "Flight_Controller/", "files": files,
                     "directories": directories, "file_count": len(files),
                     "total_bytes": sum(row["bytes"] for row in files.values()),
                     "compiled_summary": summary_path, "compiled_summary_sha256": file_hash(ROOT / summary_path),
                     "exact_compiled_artifacts_verified": proven}
        write_new(destination / "FILE_INVENTORY.json", inventory)
        print(label, "source inventory", len(files), inventory["total_bytes"], flush=True)
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True, strict_timestamps=False) as output:
            output.write(source, "Flight_Controller/")
            for name in directories:
                output.write(source / name, "Flight_Controller/" + name + "/")
            for name in files:
                output.write(source / name, "Flight_Controller/" + name)
        print(label, "compressed; reading every member", flush=True)
        with zipfile.ZipFile(archive, "r") as saved:
            entries = saved.infolist()
            expected = {"Flight_Controller/", *("Flight_Controller/" + name + "/" for name in directories),
                        *("Flight_Controller/" + name for name in files)}
            if len(entries) != len(expected) or {entry.filename for entry in entries} != expected:
                raise ValueError("Missing, duplicate, or unexpected ZIP members")
            for name, row in files.items():
                entry = saved.getinfo("Flight_Controller/" + name)
                with saved.open(entry) as stream:
                    value = digest(stream)
                if entry.file_size != row["bytes"] or value != row["sha256"]:
                    raise ValueError("ZIP readback differs: " + name)
            model = json.loads(saved.read("Flight_Controller/SilverStar.ssproject"))
            if model["build"]["target_profile"] != "SilverStar_F407":
                raise ValueError("Unexpected reopened archived project model")
        after, after_directories = scan(source)
        if files != after or directories != after_directories:
            raise ValueError("Original source changed during archive/readback")
        receipt = marker | {"created_utc": datetime.now(UTC).isoformat(), "current_head": head,
                            "epoch": "Actual immutable generated project, not rebuilt or refreshed to current M3 helper",
                            "archive": str(archive), "archive_sha256": file_hash(archive),
                            "archive_bytes": archive.stat().st_size,
                            "file_inventory_sha256": file_hash(destination / "FILE_INVENTORY.json"),
                            "file_count": len(files), "directory_count": len(directories) + 1,
                            "uncompressed_bytes": inventory["total_bytes"], "every_zip_file_readback_sha256_verified": True,
                            "original_sources_unchanged": True, "exact_compiled_artifacts_verified": proven,
                            "tool_epoch_sha256": {name: files[name]["sha256"] for name in (
                                "Tools/stack_runtime.py", "Tools/check_task_stacks.py", "Tools/software_stack_inputs.json")},
                            "reopen_validation": "ZIP full CRC/SHA readback plus archived model parsing; no GUI launch or recompilation"}
        write_new(destination / "ARCHIVE_RECEIPT.json", receipt)
        write_new(OUT / (label + ".json"), receipt)
        readme = ("# Protected software verification archive\n\n"
                  "Preserve this entire directory and the original source until root archive acceptance.\n"
                  "The ZIP contains the complete original Flight_Controller tree, including both compiled configurations, "
                  "decoder, project, proof tools and input metadata. It is software evidence, not hardware/flight qualification.\n\n"
                  "Extract into a NEW empty directory to inspect/open the existing Makefile or IDE project. "
                  "The recorded Arm GNU Toolchain 14.3.Rel1 and make/Python environment remain external; no SDK was copied. "
                  "Do not regenerate this historical project to synchronize newer helper code. "
                  "This operation verified every archived file by SHA and parsed the saved project model; it did not launch a GUI or rebuild.\n\n"
                  "See FILE_INVENTORY.json and ARCHIVE_RECEIPT.json for exact bytes and source epoch. "
                  "No source deletion, Git staging or publishing was performed.\n")
        with (destination / "README.md").open("x", encoding="utf8", newline="\n") as stream:
            stream.write(readme)
        receipts.append(receipt)
        print(label, "verified", receipt["archive_bytes"], receipt["archive_sha256"], flush=True)
    write_new(OUT / "archive-summary.json", {"archives": receipts, "no_deletions": True})


if __name__ == "__main__":
    main()
