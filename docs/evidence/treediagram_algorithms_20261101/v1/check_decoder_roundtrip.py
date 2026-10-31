"""Read-only comparison of frozen bundle, generated header and verified decoder."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/SCG/src"))
from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify


def Float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


rows = []
for kind in ("pid", "lqr"):
    base = ROOT / (".work/0.1.3-treediagram-20261101/control-core-v1/" + kind)
    decoder = base / ("ControlCore_" + kind + ".ssdecoder")
    manifest = LogDecoderPackage_Verify(decoder.read_bytes())
    with zipfile.ZipFile(decoder) as archive:
        semantics = json.loads(archive.read("project_semantics.json"))
    owners = {row["component"]: row for row in semantics["firmware_algorithm_parameters"]}
    header = (base / "Flight_Controller/Generated/Inc/project_algorithm_parameters.h").read_text()
    defines = dict(re.findall(r"^#define (SYSTEM_\w+) ([+\-\d.eE]+)f$", header, re.MULTILINE))
    bundle = json.loads((ROOT / f"apps/SCG/tests/fixtures/tuning_bundle_v1/kf6-{kind}.sstuning.json").read_text())
    owner = owners["silverstar.algorithm.control." + kind]
    values = {row["id"]: row["value"] for row in owner["parameters"]}
    actual = {key: Float32(value) for key, value in bundle["control_research"]["parameters"].items()}
    assert values == actual
    for key, value in actual.items():
        assert Float32(float(defines[f"SYSTEM_CONTROL_{kind.upper()}_{key.upper()}"])) == value
    gravity = Float32(9.80665)
    for component, prefix in (("silverstar.algorithm.ins.coning2_sculling2", "INS"),
                              ("silverstar.algorithm.estimator.kf6", "KF")):
        parameters = {row["id"]: row["value"] for row in owners[component]["parameters"]}
        assert parameters["gravity_mps2"] == gravity
        assert Float32(float(defines[f"SYSTEM_{prefix}_GRAVITY_MPS2"])) == gravity
    rows.append({"kind": kind, "decoder_sha256": hashlib.sha256(decoder.read_bytes()).hexdigest(),
        "decoder_verified": True, "generation_profile_sha256": manifest["generation_profile_sha256"],
        "gravity_mps2": gravity, "control_parameters": actual, "header_decoder_bundle_match": True})
print(json.dumps(rows, indent=2))
