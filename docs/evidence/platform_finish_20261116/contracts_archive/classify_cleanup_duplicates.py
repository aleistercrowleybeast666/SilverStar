"""Classify verified compiled duplicates only; never delete or move anything."""
import json
from pathlib import Path

from archive_projects import DESTINATION, ROOT, file_hash, scan, write_new

OUT = Path(__file__).resolve().parent
COMPILED_SUFFIXES = {".o", ".su", ".d", ".s", ".elf", ".bin", ".hex", ".map"}


def main():
    target = OUT / "cleanup-eligibility"
    target.mkdir(exist_ok=False)
    acceptance_path = OUT.parent / "delivery/archive-verification.json"
    accepted = {row["archive"]: row for row in json.loads(acceptance_path.read_bytes())}
    source_summary = OUT / "repeated-build-summary.json"
    summaries = []
    for row in json.loads(source_summary.read_bytes())["directories"]:
        original_path = OUT / row["inventory"]
        if file_hash(original_path) != row["inventory_sha256"]:
            raise ValueError("Inventory changed: " + str(original_path))
        original = json.loads(original_path.read_bytes())
        source = Path(original["path"]).resolve(strict=True)
        source.relative_to((ROOT / ".work").resolve(strict=True))
        actual, directories = scan(source)
        if actual != original["files"] or directories != original["directories"]:
            raise ValueError("Current build no longer matches inventory: " + str(source))
        reference_dir = ROOT / original["protected_reference"]
        reference_dir.resolve(strict=True).relative_to(DESTINATION.resolve(strict=True))
        receipt = json.loads((reference_dir / "ARCHIVE_RECEIPT.json").read_bytes())
        approval = accepted[receipt["archive"]]
        if (approval["root_independent_readback"] != "PASS"
                or approval["sha256"] != receipt["archive_sha256"]):
            raise ValueError("Archive has not been independently accepted")
        reference_path = reference_dir / "FILE_INVENTORY.json"
        if file_hash(reference_path) != original["reference_inventory_sha256"]:
            raise ValueError("Protected reference inventory changed")
        reference = json.loads(reference_path.read_bytes())["files"]
        groups = {"eligible_duplicate": {}, "preserved_unique": {}, "preserved_report": {}}
        for name, value in actual.items():
            archived = reference.get("build/FCCG/SilverStar_F407/" + name)
            if value != archived:
                category = "preserved_unique"
            elif Path(name).suffix not in COMPILED_SUFFIXES:
                category = "preserved_report"
            else:
                category = "eligible_duplicate"
            groups[category][name] = value
        counts = {key: {"files": len(values), "bytes": sum(v["bytes"] for v in values.values())}
                  for key, values in groups.items()}
        result = {
            "owner": original["owner"], "build_root": str(source),
            "original_inventory": row["inventory"],
            "original_inventory_sha256": row["inventory_sha256"],
            "formal_commands": original["formal_commands"],
            "protected_archive": receipt["archive"], "protected_archive_sha256": receipt["archive_sha256"],
            "archive_acceptance_sha256": file_hash(acceptance_path),
            "current_files_equal_inventory": True, "deletion_executed": False,
            "eligibility": "Only listed compiled files equal to the accepted archive by relative path, size and SHA; root must recheck at deletion time",
            "excluded": "All unique files, reports/JSON/logs, source, inputs, formal evidence, project roots and other owners",
            "counts": counts, "groups": groups,
        }
        output = target / original_path.name
        write_new(output, result)
        summaries.append({"build_root": str(source), "counts": counts,
                          "eligibility_inventory": output.relative_to(OUT).as_posix(),
                          "sha256": file_hash(output)})
    totals = {category: {
        measure: sum(row["counts"][category][measure] for row in summaries)
        for measure in ("files", "bytes")}
        for category in ("eligible_duplicate", "preserved_unique", "preserved_report")}
    write_new(OUT / "cleanup-eligibility-summary.json", {
        "deletion_executed": False, "directories": summaries, "totals": totals,
        "repeated_inventory_sha256": file_hash(source_summary),
        "archive_acceptance_sha256": file_hash(acceptance_path),
        "scope": "Seven current-task owned ARM build subtrees only; root-controlled later cleanup, no directory deletion authorization",
    })
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    main()
