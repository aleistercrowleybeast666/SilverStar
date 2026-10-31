"""Export a small, auditable, offline mathematical SDK; never exports hardware stubs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


PLUGINS = {
    "silverstar_algorithm_common": ("attitude_frame.c", "attitude_frame.h"),
    "silverstar_algorithm_ins_coning2_sculling2": ("ins_mechanization.c", "ins_mechanization.h"),
    "silverstar_algorithm_estimator_kf6": ("navigation_kf.c", "navigation_kf.h"),
    "silverstar_algorithm_estimator_sf6": ("navigation_sf6.c", "navigation_sf6.h"),
    "silverstar_algorithm_estimator_eskf15": ("navigation_eskf.c", "navigation_eskf.h"),
    "silverstar_algorithm_augmented_common": ("navigation_bounded.c", "navigation_bounded.h"),
    "silverstar_algorithm_estimator_eskf20": (),
    "silverstar_algorithm_estimator_inekf15": (),
    "silverstar_algorithm_estimator_inekf20": (),
    "silverstar_algorithm_control_pid": ("control_pid.c", "control_pid.h"),
    "silverstar_algorithm_control_lqr": ("control_lqr.c", "control_lqr.h"),
}


def Sdk_Export(destination: Path) -> dict:
    """Copy an explicit allowlist and bind every byte to its owning source path."""
    root = Path(__file__).resolve().parents[3]
    builtin = root / "apps/SCG/plugins/builtin"
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    for folder, names in PLUGINS.items():
        plugin = builtin / folder
        for name in (*names, "plugin.json"):
            matches = list(plugin.rglob(name))
            if len(matches) != 1:
                raise ValueError(f"SDK source is not unique: {folder}/{name}")
            source = matches[0]
            target = destination / folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files[target.relative_to(destination).as_posix()] = {
                "source": source.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "modified": False,
            }
    extra = {
        "LICENSE": root / "LICENSE",
        "tuning_bundle_v1.schema.json": root / "contracts/tuning_bundle_v1.schema.json",
        "reference_config.h": root / "apps/SCG/tests/fixtures/navigation_perf_config/system_user_config.h",
        "silverstar_assert.h": builtin / "silverstar_core_0_1_0/payload/Common/Inc/silverstar_assert.h",
        "silverstar_compiler.h": builtin / "silverstar_core_0_1_0/payload/Common/Inc/silverstar_compiler.h",
    }
    for name, source in extra.items():
        shutil.copyfile(source, destination / name)
        files[name] = {"source": source.relative_to(root).as_posix(),
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "modified": False}
    manifest = {
        "schema_id": "silverstar.algorithm-sdk/1",
        "repository": "https://github.com/aleistercrowleybeast666/SilverStar",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "source_state": "content-addressed working tree snapshot; commit alone is insufficient",
        "files": files,
        "scope": "mathematical cores, explicit host configuration; no MCU/HAL/RTOS or flight qualification",
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(Sdk_Export(args.destination), indent=2))
