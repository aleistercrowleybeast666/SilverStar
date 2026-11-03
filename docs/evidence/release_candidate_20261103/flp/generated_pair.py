"""Build a synthetic recording with a real generated decoder and its compiled C word encoder."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [
    str(ROOT / "apps/FLP/src"),
    str(ROOT / "apps/FLP"),
    str(ROOT / "apps/SCG/src"),
]
from silverstar_flp.decoder_profiles.discovery import DecoderProfileCache
from silverstar_flp.decoder_profiles.package import DecoderProfilePackage
from silverstar_flp.log_open import LogOpenCoordinator, LogOpenRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.sslog_synthetic import (
    SyntheticSslogBuilder,
    START_TIMESTAMP_US,
    Event_Payload,
)
from tests.test_decoder_profiles import _CalibrationNonePayload_Build


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("new_output", type=Path)
    options = parser.parse_args()
    root, work = options.project.resolve(), options.new_output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    mission = work / "mission"
    mission.mkdir()
    packages = list(root.glob("*.ssdecoder"))
    assert len(packages) == 1
    package = DecoderProfilePackage.Load(packages[0])
    copy = mission / packages[0].name
    shutil.copyfile(packages[0], copy)
    with zipfile.ZipFile(copy) as reader:
        catalog = json.loads(reader.read("record_catalog.json"))
        semantics = json.loads(reader.read("project_semantics.json"))
    decl = {row["name"]: row for row in catalog["records"]}
    builder = SyntheticSslogBuilder(build_id=b"HOSTRC03")

    def record(name, payload, timestamp):
        row = decl[name]
        assert len(payload) == row["payload_size"]
        builder.Record_Add(
            int(row["id"], 0), payload, timestamp, record_version=row["version"]
        )

    hashes = bytes.fromhex(
        package.record_catalog_hash_128
        + package.project_semantics_hash_128
        + package.generation_profile_hash_128
    )
    descriptor = (
        struct.pack(
            "<HHHH", package.package_schema_major, package.package_schema_minor, 0, 0
        )
        + hashes
        + bytes(8)
    )
    descriptor_name = next(
        name for name, row in decl.items() if int(row["id"], 0) == 0x1D
    )
    record(descriptor_name, descriptor, START_TIMESTAMP_US - 3)
    record(
        "CALIBRATION_RESULT", _CalibrationNonePayload_Build(), START_TIMESTAMP_US - 2
    )
    record("EVENT", Event_Payload(3), START_TIMESTAMP_US)
    rotation = semantics.get("event_catalog", {}).get("mag_rotation_adopted")
    build = None
    if rotation:
        directory = root / "Flight_Controller" / "Algorithm/Installation/MagRotation"
        src = directory / "Src/mag_rotation.c"
        header = directory / "Inc/mag_rotation.h"
        dll = work / "mag_rotation.dll"
        command = [
            "gcc",
            "-std=c11",
            "-O2",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-fanalyzer",
            "-I" + str(header.parent),
            str(src),
            "-lm",
            "-o",
            str(dll),
        ]
        subprocess.run(command, check=True)
        lib = ctypes.CDLL(str(dll))
        vec = ctypes.c_float * 4
        lib.MagRotation_Encode.argtypes = [ctypes.POINTER(ctypes.c_float)]
        lib.MagRotation_Encode.restype = ctypes.c_uint32
        q = [0.9238795325, 0.0, 0.0, -0.3826834324]
        packed = lib.MagRotation_Encode(vec(*q))
        record(
            "EVENT",
            Event_Payload(rotation["event_id"], packed, 17),
            START_TIMESTAMP_US + 10000,
        )
        record(
            "EVENT",
            Event_Payload(0x36, 3 | (72 << 8) | (40 << 24), 17),
            START_TIMESTAMP_US + 10001,
        )
        build = dict(
            command=command,
            source=sha(src),
            header=sha(header),
            library=sha(dll),
            q=q,
            word=packed,
        )
    log = builder.File_Write(mission / "SYNTHETIC_RC.sslog")
    before = sha(log), sha(copy)
    result = LogOpenCoordinator(
        builtin_registry(), cache=DecoderProfileCache(work / "cache")
    ).Open(LogOpenRequest(log_path=log, auto_find=True, task_directory=mission))
    events = result.dataset.Records_Get("EVENT")
    if build:
        adopted = events[1].payload
        assert adopted["rotation_update_id"] == 17 and all(
            abs(a - b) < 0.002 for a, b in zip(adopted["rotation_q_wxyz"], build["q"])
        )
        assert events[2].payload["rotation_quality_code"] == 3
    assert (
        result.package.package_sha256 == sha(copy)
        and len(result.dataset.Records_Get("CALIBRATION_RESULT")) == 1
    )
    assert result.dataset.metadata["mission_snapshot"]["status"] == "unavailable"
    env = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join(
            map(str, [ROOT / "apps/FLP/src", ROOT / "apps/SCG/src"])
        ),
        LOCALAPPDATA=str(work / "cli-cache"),
        PYTHONUTF8="1",
    )
    command = [sys.executable, "-B", "-m", "silverstar_flp.cli", "inspect", str(log)]
    with (work / "inspect.json").open("w", encoding="utf8") as stream:
        cli = subprocess.run(
            command, env=env, cwd=ROOT, stdout=stream, stderr=subprocess.PIPE, text=True
        )
    (work / "inspect.stderr").write_text(cli.stderr, encoding="utf8")
    assert cli.returncode == 0, cli.stderr
    assert before == (sha(log), sha(copy))
    report = {
        "scope": "Generated project decoder, synthetic SSLOG records; declared defaults are never supplied as Recorded snapshot values.",
        "model": str(root / "SilverStar.ssproject"),
        "model_sha256": sha(root / "SilverStar.ssproject"),
        "decoder": str(packages[0]),
        "decoder_sha256": sha(copy),
        "log": str(log),
        "log_sha256": sha(log),
        "descriptor_payload_hex": descriptor.hex(),
        "compiled_rotation": build,
        "automatic": result.match_mode,
        "cli": command,
        "exit": cli.returncode,
        "recorded_events": [x.payload["event_name"] for x in events],
        "recorded_snapshot_status": result.dataset.metadata["mission_snapshot"][
            "status"
        ],
    }
    (work / "result.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
