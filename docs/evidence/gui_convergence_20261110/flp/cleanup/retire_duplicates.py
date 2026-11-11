"""Retire only byte-identical, owned old FLP generated outputs; preserve full2."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import zipfile

TASK = Path(__file__).resolve().parent
REPO = TASK.parents[2]
WORK = REPO / ".work"
DEST = Path("D:/SilverStar_Archive/20261110/task/flp-duplicates")
REFERENCE = WORK / "gcf-full2"
SUFFIXES = {".png", ".csv", ".exe", ".dll", ".o", ".obj", ".pyc"}
KEEP_ROOTS = {"gcf-lifecycle8", "gcf-lifecycle9", "gcf-lifecycle10", "gcf-full2"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def no_links(path):
    for part in reversed((path, *path.parents)):
        try:
            data = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(data.st_mode) or data.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError(f"link rejected: {part}")


def scoped(relative):
    parts = relative.split("/")
    if not relative or any(p in {"", ".", ".."} or ":" in p or "\\" in p for p in parts):
        raise RuntimeError("invalid manifest path")
    path = WORK.joinpath(*parts)
    no_links(path)
    if not path.resolve().is_relative_to(WORK.resolve()):
        raise RuntimeError("path escaped .work")
    return path


def candidates(root):
    """No recursive deletion/traversal of links, nested repositories or raw inputs."""
    no_links(root)
    pending = [root]
    while pending:
        folder = pending.pop()
        with os.scandir(folder) as entries:
            children = list(entries)
        if any(entry.name == ".git" for entry in children):
            continue
        for entry in children:
            path = Path(entry.path)
            data = path.lstat()
            if data.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                continue
            if stat.S_ISDIR(data.st_mode):
                if path.name.casefold() not in {"inputs", "fixtures", "logs", "log", "retained_inputs"}:
                    pending.append(path)
            elif stat.S_ISREG(data.st_mode) and path.suffix.casefold() in SUFFIXES:
                parts = path.relative_to(root).parts
                if any(p.startswith("test_") for p in parts[:-1]):
                    # Keep the original failing KF6 bootstrap fixture and timeout repro.
                    if root.name == "gcf-full" and any(
                        p.startswith(("test_horizon", "test_project_header")) for p in parts
                    ):
                        continue
                    yield path


def record(path):
    no_links(path)
    before = path.lstat()
    sha = digest(path)
    after = path.lstat()
    fields = ("st_size", "st_mtime_ns", "st_ino", "st_dev")
    if any(getattr(before, field) != getattr(after, field) for field in fields):
        raise RuntimeError(f"changed while hashing: {path}")
    return {"path": path.relative_to(WORK).as_posix(), "size": before.st_size,
            "sha256": sha, "mtime_ns": before.st_mtime_ns,
            "file_id": before.st_ino, "device": before.st_dev}


def validate(row):
    path = scoped(row["path"])
    data = path.lstat()
    if not stat.S_ISREG(data.st_mode) or (
        data.st_size, data.st_mtime_ns, data.st_ino, data.st_dev
    ) != (row["size"], row["mtime_ns"], row["file_id"], row["device"]):
        raise RuntimeError(f"identity changed: {path}")
    if digest(path) != row["sha256"]:
        raise RuntimeError(f"content changed: {path}")
    return path


def save(name, value):
    path = DEST / name
    no_links(path)
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def plan():
    no_links(DEST)
    DEST.mkdir(parents=True, exist_ok=True)
    owner = json.loads((TASK / "ownership.json").read_text(encoding="utf8"))
    reference = {}
    for path in candidates(REFERENCE):
        row = record(path)
        reference.setdefault((row["sha256"], path.suffix.casefold()), row)
    selected = []
    for name in owner["scratch_roots"]:
        root = Path(name)
        if root.parent.resolve() != WORK.resolve():
            raise RuntimeError("ownership root outside expected work directory")
        if root.name in KEEP_ROOTS or not root.exists():
            continue
        for path in candidates(root):
            row = record(path)
            retained = reference.get((row["sha256"], path.suffix.casefold()))
            if retained is not None:
                selected.append({**row, "retained_full2_copy": retained})
    payload = {"schema": "silverstar.flp-exact-duplicate-retirement/1",
               "created_utc": datetime.now(timezone.utc).isoformat(),
               "owner": "/root/flp_finish", "source_root": str(WORK),
               "ownership_sha256": digest(TASK / "ownership.json"),
               "full2_summary_sha256": digest(TASK / "full2-summary.json"),
               "policy": "Only selected generated image/CSV/compiled files whose bytes also remain in full2; no raw log, decoder, archive, source fixture, link, nested repository or unique output selected. Failed lifecycle trees and original horizon/header reproduction retained.",
               "allowed_suffixes": sorted(SUFFIXES), "retained_roots": sorted(KEEP_ROOTS),
               "files": selected, "count": len(selected),
               "bytes": sum(row["size"] for row in selected)}
    save("manifest.json", payload)
    print(json.dumps({"files": payload["count"], "bytes": payload["bytes"],
                      "manifest_sha256": digest(DEST / "manifest.json")}), flush=True)


def load(expected):
    path = DEST / "manifest.json"
    no_links(path)
    if digest(path) != expected:
        raise RuntimeError("manifest SHA mismatch")
    data = json.loads(path.read_text(encoding="utf8"))
    owner = json.loads((TASK / "ownership.json").read_text(encoding="utf8"))
    roots = {Path(name).name for name in owner["scratch_roots"]} - KEEP_ROOTS
    seen = set()
    for row in data["files"]:
        path = scoped(row["path"])
        ref = scoped(row["retained_full2_copy"]["path"])
        if (path.relative_to(WORK).parts[0] not in roots or path.suffix.casefold() not in SUFFIXES
            or ref.relative_to(WORK).parts[0] != "gcf-full2"
            or row["sha256"] != row["retained_full2_copy"]["sha256"]
            or row["path"] in seen):
            raise RuntimeError("manifest scope invalid")
        seen.add(row["path"])
    return data


def archive(expected):
    data = load(expected)
    target = DEST / "exact-duplicate-objects.zip"
    no_links(target)
    objects = {}
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for row in data["files"]:
            path = validate(row)
            validate(row["retained_full2_copy"])
            if row["sha256"] not in objects:
                zipped.write(path, row["sha256"])
                objects[row["sha256"]] = row["size"]
    restored = DEST / "verified-restore.tmp"
    no_links(restored)
    with zipfile.ZipFile(target) as zipped:
        if set(zipped.namelist()) != set(objects):
            raise RuntimeError("archive contents mismatch")
        for sha, size in objects.items():
            with zipped.open(sha) as source, restored.open("xb") as output:
                shutil.copyfileobj(source, output)
            if restored.stat().st_size != size or digest(restored) != sha:
                raise RuntimeError("physical restoration failed")
            restored.unlink()
    for row in data["files"]:
        validate(row)
        validate(row["retained_full2_copy"])
    receipt = {"manifest_sha256": expected, "archive": str(target),
               "archive_sha256": digest(target), "archive_bytes": target.stat().st_size,
               "unique_objects_physically_restored_and_sha_verified": len(objects),
               "selected_files": data["count"], "selected_bytes": data["bytes"],
               "source_deletion": False}
    save("archive-verified.json", receipt)
    print(json.dumps(receipt), flush=True)


def delete(expected):
    data = load(expected)
    receipt = json.loads((DEST / "archive-verified.json").read_text(encoding="utf8"))
    target = DEST / "exact-duplicate-objects.zip"
    no_links(target)
    if receipt["manifest_sha256"] != expected or receipt["archive_sha256"] != digest(target):
        raise RuntimeError("archive verification identity mismatch")
    for row in data["files"]:
        validate(row)
        validate(row["retained_full2_copy"])
    deleted, errors = [], []
    with (DEST / "deleted-files.jsonl").open("x", encoding="utf8") as journal:
        for row in data["files"]:
            try:
                validate(row["retained_full2_copy"])
                path = validate(row)
                path.unlink()  # Individually validated exact manifest file only.
                deleted.append(row)
                journal.write(json.dumps({key: row[key] for key in ("path", "size", "sha256")}) + "\n")
                journal.flush()
            except (OSError, RuntimeError) as exc:
                errors.append({"path": row["path"], "reason": str(exc)})
                break
    for row in data["files"]:
        validate(row["retained_full2_copy"])
    result = {"manifest_sha256": expected, "archive": receipt,
              "deleted_files": len(deleted), "deleted_bytes": sum(row["size"] for row in deleted),
              "retained_full2_copies_verified": len(data["files"]),
              "errors": errors, "directories_removed": 0,
              "journal_sha256": digest(DEST / "deleted-files.jsonl")}
    save("cleanup-result.json", result)
    print(json.dumps(result), flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("plan", "archive", "delete"))
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.phase == "plan":
        plan()
    elif args.phase == "archive":
        archive(args.manifest_sha256)
    else:
        delete(args.manifest_sha256)
