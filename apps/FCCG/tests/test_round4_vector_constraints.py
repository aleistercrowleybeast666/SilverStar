from __future__ import annotations

from pathlib import Path

from test_joint_sensor_library import _Command_Run, _Compiler_Get


ROOT = Path(__file__).resolve().parents[1]
COMMON = (
    ROOT
    / "plugins/builtin/silverstar_algorithm_alignment_common"
    / "payload/Algorithm/Alignment/Common"
)


def test_vector_constraints_host_and_arm(tmp_path: Path) -> None:
    compiler = _Compiler_Get()
    host = tmp_path / "vector_constraints.exe"
    flags = [
        compiler,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wconversion",
        "-Wsign-conversion",
        "-Wshadow",
        "-Wvla",
        "-I" + str(COMMON / "Inc"),
    ]
    source = COMMON / "Src/vector_constraints.c"
    test_source = ROOT / "tests/host_alignment/test_vector_constraints.c"
    _Command_Run(
        flags + [str(source), str(test_source), "-lm", "-o", str(host)],
        tmp_path,
        "compile",
    )
    _Command_Run([str(host)], tmp_path, "run")
