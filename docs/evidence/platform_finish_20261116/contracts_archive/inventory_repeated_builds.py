"""Inventory this agent's current-task ARM builds; no deletion is authorized."""
import json
from pathlib import Path

from archive_projects import DESTINATION, ROOT, file_hash, scan, write_new

OUT = Path(__file__).resolve().parent
TARGET = "Flight_Controller/build/FCCG/SilverStar_F407"
WORK = ".work/platform-finish-20261116/contracts/"
ROWS = (
    ("default-a", WORK + "post-generated-a/f4/" + TARGET, "build-a", "default"),
    ("default-b", WORK + "post-generated-b/f4/" + TARGET, "build-b", "default"),
    ("default-c", WORK + "final-generated-c/f4/" + TARGET, "build-c", "default"),
    ("default-d", WORK + "final-generated-d/f4/" + TARGET, "build-d", "default"),
    ("default-e", WORK + "final-generated-e/f4/" + TARGET, "build-e", "default"),
    ("e19-a", ".work/pf1117/contract-e19-a/" + TARGET, "build-e19-a", "e19"),
    ("e19-b", ".work/pf1117/contract-e19-b/" + TARGET, "build-e19-b", "e19"),
)


def main():
    folder = OUT / "build-inventories"
    folder.mkdir(exist_ok=False)
    prefix = "build/FCCG/SilverStar_F407/"
    references = {}
    for kind, label in (("default", "f407-default-e-20261117"), ("e19", "f407-e19-b-20261117")):
        inventory = DESTINATION / label / "FILE_INVENTORY.json"
        value = json.loads(inventory.read_bytes())
        references[kind] = {"directory": label, "inventory_sha256": file_hash(inventory),
                            "files": {name.removeprefix(prefix): row for name, row in value["files"].items()
                                      if name.startswith(prefix)}}
    summary = []
    for label, relative, evidence, kind in ROWS:
        source = (ROOT / relative).resolve(strict=True)
        source.relative_to((ROOT / ".work").resolve(strict=True))
        files, directories = scan(source)
        comparison = references[kind]["files"]
        identical = [name for name, row in files.items() if comparison.get(name) == row]
        unmatched = [name for name in files if name not in identical]
        final = label in ("default-e", "e19-b")
        record = {"owner": "/root/silverstar_finish (ARM build subtree only)", "path": str(source),
                  "repository_relative_path": relative, "scope": "Current 2026-11-16/17 task only",
                  "deletion_authorized": False,
                  "retention": "Protected final original; retain until explicit root archive acceptance" if final else
                               "Mixed repeated objects and historical evidence epoch; inventory is not a deletion allowlist",
                  "formal_commands": "docs/evidence/platform_finish_20261116/contracts/" + evidence + "/commands.json",
                  "formal_input_stability": "docs/evidence/platform_finish_20261116/contracts/" + evidence + "/input-stability.json",
                  "protected_reference": "dist/pf1117-evidence/" + references[kind]["directory"],
                  "reference_inventory_sha256": references[kind]["inventory_sha256"],
                  "files": files, "directories": directories,
                  "file_count": len(files), "total_bytes": sum(row["bytes"] for row in files.values()),
                  "same_relative_path_and_sha_as_archive": identical,
                  "not_identical_or_missing_from_reference": unmatched,
                  "note": "A same-content object is not permission to delete its directory. Distinct analyzers/reports/epochs remain protected."}
        path = folder / (label + ".json")
        write_new(path, record)
        summary.append({key: record[key] for key in (
            "owner", "path", "repository_relative_path", "deletion_authorized", "retention", "formal_commands",
            "protected_reference", "file_count", "total_bytes")}
            | {"inventory": path.relative_to(OUT).as_posix(), "inventory_sha256": file_hash(path),
               "identical_to_protected_reference_count": len(identical), "distinct_or_unarchived_count": len(unmatched)})
    write_new(OUT / "repeated-build-summary.json", {
        "no_deletions": True, "directories": summary,
        "excluded": ["All earlier tasks and other agents' work", "Original source/fixtures/decoder/configuration and formal evidence",
                     "E19 A build/FCCG/Host (root-owned final Host validation)", "Every Ground target (board-agent owned)",
                     "Entire project roots and pytest source fixtures", "All protected dist archives and their markers"]})
    print("Inventoried", len(summary), "owned ARM directories; no deletion;",
          sum(row["total_bytes"] for row in summary), "bytes")


if __name__ == "__main__":
    main()
