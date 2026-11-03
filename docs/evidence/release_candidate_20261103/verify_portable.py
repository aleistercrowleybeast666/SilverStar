"""Extract only validated members of the candidate into a fresh Windows QA directory."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("receipt", "new_directory", "result"):
        parser.add_argument(name, type=Path)
    options = parser.parse_args()
    receipt = json.loads(options.receipt.read_text(encoding="utf8"))
    archive = Path(receipt["archive"])
    assert digest(archive) == receipt["sha256"]
    root = options.new_directory.resolve()
    root.mkdir(exist_ok=False)
    files = set()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name = PurePosixPath(entry.filename)
            if (name.parts[:1] != ("SilverStar",) or name.is_absolute()
                    or any(part in (".", "..") or ":" in part or "\\" in part for part in name.parts)
                    or entry.is_dir()):
                raise ValueError(f"Invalid portable member {name}")
            target = root.joinpath(*name.parts).resolve()
            if not target.is_relative_to(root) or target in files:
                raise ValueError(f"Conflicting portable member {name}")
            files.add(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as data, target.open("xb") as out:
                shutil.copyfileobj(data, out)
    bundle = root / "SilverStar"
    manifest_path = bundle / "CANDIDATE_MANIFEST.json"
    expected = json.loads(manifest_path.read_text(encoding="utf8"))
    assert expected["code_commit"] == receipt["code_commit"]
    assert {bundle / name for name in expected["files"]} == files - {manifest_path}
    for name, expected_hash in expected["files"].items():
        if digest(bundle / name) != expected_hash:
            raise ValueError("Unpacked file differs: " + name)
    result = {"sha256": receipt["sha256"], "code_commit": expected["code_commit"],
              "unpacked": str(bundle), "verified_members": len(files),
              "executables": {p.name: digest(p) for p in sorted(bundle.glob("*.exe"))}}
    assert result["executables"] == receipt["executable_sha256"]
    with options.result.open("x", encoding="utf8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
