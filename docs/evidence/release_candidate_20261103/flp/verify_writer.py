"""Verify exact firmware-writer provenance in a completed FLP inspect result."""

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    run = args.run_directory.resolve()
    directory = run / "valid-input"
    report = json.loads((run / "inspect.json").read_text(encoding="utf-8-sig"))
    snapshot = report["mission_snapshot"]
    assert snapshot["status"] == "verified", snapshot.get("reason")
    assert snapshot["devices"] and snapshot["algorithms"] and snapshot["parameters"]
    if "parameter_dictionary" in snapshot:
        assert len(snapshot["parameter_dictionary"]) == len(snapshot["parameters"])
    assert len(snapshot["sources"]) == 7
    assert report["record_counts"]["CALIBRATION_RESULT"] >= 1
    assert report["record_counts"]["MISSION_SNAPSHOT_IDENTITY"] >= 1
    recorded = snapshot["calibration"]
    assert recorded["ready"] == 1 and recorded["mode"] == 0
    assert recorded["generation"] == snapshot["header"]["calibration_generation"] == 1
    assert recorded["mag_set_hash"] == snapshot["header"]["mag_calibration_set_hash"]
    for source in snapshot["sources"]:
        file = Path(source["path"]).resolve()
        assert file.parent == directory and source["sha256"] == sha256(file)
    package = next(directory.glob("*.ssdecoder"))
    assert sha256(package) == report["decoder"]["package_sha256"]
    initial = directory / "input-hashes.json"
    if initial.is_file():
        assert all(sha256(directory / name) == expected
                   for name, expected in json.loads(initial.read_text(encoding="utf8")).items())
    receipt = {
        "scope": "Simulated input and SD media, generated logger and FatFs, production FLP CLI",
        "log_sha256": sha256(directory / "HOST_GENERATED.sslog"),
        "package_sha256": sha256(package),
        "before_after_input_hashes_checked": initial.is_file(),
        "cli_exit": 0,
        "record_counts": report["record_counts"],
        "snapshot_header": snapshot["header"],
        "calibration": recorded,
        "parameters": snapshot["parameters"],
        "exact_decoder_parameter_names": snapshot.get("parameter_dictionary"),
        "devices": snapshot["devices"],
        "algorithms": snapshot["algorithms"],
        "verified_sources": snapshot["sources"],
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
