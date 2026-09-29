from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/GSHC"))

from protocol.common import crc16_ccitt_false  # noqa: E402
from protocol.gsp_min import GspParser, build_gsp_frame  # noqa: E402


@pytest.fixture(scope="module")
def ground_gsp_tool(tmp_path_factory) -> Path:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("Host GCC is needed for the C/Python GSP contract test")
    output = tmp_path_factory.mktemp("ground-gsp") / "gsp_vectors.exe"
    protocol = (
        ROOT / "apps/FCCG/plugins/builtin/silverstar_core_ground_0_1_0"
        / "payload/Ground/Protocol"
    )
    common = (
        ROOT / "apps/FCCG/plugins/builtin/silverstar_core_0_1_0"
        / "payload/Common"
    )
    subprocess.run(
        [
            compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I" + str(protocol / "Inc"),
            "-I" + str(common / "Inc"),
            str(ROOT / "tests/integration/ground_gsp_vectors.c"),
            str(protocol / "Src/gsp_min_protocol.c"),
            str(protocol / "Src/protocol_crc16.c"),
            str(common / "Src/silverstar_assert.c"),
            "-o", str(output),
        ],
        check=True, capture_output=True, text=True,
    )
    return output


def test_ground_c_and_gshc_python_share_gsp_golden_frames(ground_gsp_tool: Path) -> None:
    golden = json.loads((ROOT / "contracts/gsp/golden.json").read_text(encoding="utf-8"))
    crc_bytes = b"123456789"
    assert f"{crc16_ccitt_false(crc_bytes):04x}" == golden["crc_123456789"]
    assert subprocess.check_output(
        [ground_gsp_tool, "crc", "0", crc_bytes.hex()], text=True
    ).strip() == golden["crc_123456789"]
    for case in golden["frames"]:
        payload = bytes.fromhex(case["payload_hex"])
        frame = bytes.fromhex(case["frame_hex"])
        assert build_gsp_frame(case["type"], payload) == frame, case["name"]
        parsed = GspParser().feed(frame)
        assert len(parsed) == 1
        assert (parsed[0].msg_type, parsed[0].payload) == (case["type"], payload)
        assert subprocess.check_output(
            [ground_gsp_tool, case["builder"], str(case["type"]), payload.hex()],
            text=True,
        ).strip() == case["frame_hex"]
        assert subprocess.check_output(
            [ground_gsp_tool, "parse", "0", case["frame_hex"]],
            text=True,
        ).strip() == f"{case['type']}:{case['payload_hex']}"
