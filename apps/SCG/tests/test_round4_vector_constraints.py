from __future__ import annotations

from pathlib import Path
import shutil

from test_joint_sensor_library import _Command_Run, _Compiler_Get

ROOT = Path(__file__).resolve().parents[1]
COMMON = (
    ROOT
    / "plugins/builtin/silverstar_algorithm_alignment_common"
    / "payload/Algorithm/Alignment/Common"
)


def test_vector_constraints_host(tmp_path: Path) -> None:
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
    core_common = (
        ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
    )
    _Command_Run(
        flags + [
            "-I" + str(core_common / "Inc"),
            str(source),
            str(test_source),
            "-lm", "-o", str(host),
        ],
        tmp_path,
        "compile",
    )
    _Command_Run([str(host)], tmp_path, "run")


def test_vector_constraints_real_analyzer_and_arm_object(tmp_path: Path) -> None:
    """Actual analyzer compilation and target code generation, not syntax-only."""
    source = COMMON / "Src/vector_constraints.c"
    core = ROOT / "plugins/builtin/silverstar_core_0_1_0/payload/Common"
    flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion",
             "-Wsign-conversion", "-Wshadow", "-Wvla", "-fstack-usage",
             "-I" + str(COMMON / "Inc"), "-I" + str(core / "Inc")]
    _Command_Run([_Compiler_Get(), *flags, "-fanalyzer", "-O0", "-c",
                  str(source), "-o", str(tmp_path / "analyzer.o")],
                 tmp_path, "analyzer")
    arm = shutil.which("arm-none-eabi-gcc")
    assert arm is not None, "ARM compiler required for this numerical firmware gate"
    _Command_Run([arm, *flags, "-Os", "-mcpu=cortex-m4", "-mthumb",
                  "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard", "-c",
                  str(source), "-o", str(tmp_path / "vector_constraints.o")],
                 tmp_path, "arm_object")
    assert (tmp_path / "vector_constraints.o").stat().st_size > 0


def test_vector_constraints_nonconvergence_clears_output(tmp_path: Path) -> None:
    """Fault injection is confined to a disposable Host source copy."""
    source = (COMMON / "Src/vector_constraints.c").read_text(encoding="utf-8")
    limit = "#define VECTOR_CONSTRAINTS_SVD_SWEEPS 16U"
    assert source.count(limit) == 1
    injected = tmp_path / "nonconvergent.c"
    injected.write_text(source.replace(limit, "#define VECTOR_CONSTRAINTS_SVD_SWEEPS 1U"),
                        encoding="utf-8")
    harness = tmp_path / "budget_failure.c"
    harness.write_text(r"""
#include "vector_constraints.h"
#include <assert.h>
#include <string.h>
int main(void)
{
    const VectorConstraint input[3] = {
        {{1,0,0}, {1,0,0}, 1},
        {{0.6F,0.8F,0}, {0.6F,0.8F,0}, 1},
        {{0.2F,0.3F,0.93F}, {0.2F,0.3F,0.93F}, 1}
    };
    VectorConstraintsSolution output;
    const VectorConstraintsSolution zero = {0};
    (void)memset(&output, 0x5a, sizeof(output));
    assert(VectorConstraints_Solve(input, 3U, &output) == VectorConstraintsSolveDegenerate);
    assert(memcmp(&output, &zero, sizeof(output)) == 0);
    return 0;
}
""", encoding="utf-8")
    executable = tmp_path / "budget_failure.exe"
    _Command_Run([_Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
                  "-I" + str(COMMON / "Inc"), str(injected), str(harness),
                  "-lm", "-o", str(executable)], tmp_path, "compile")
    _Command_Run([str(executable)], tmp_path, "run")


def test_vector_strategy_solver_failure_never_ready(tmp_path: Path) -> None:
    strategy = (ROOT / "plugins/builtin/silverstar_algorithm_alignment_vector_constraints"
                / "payload/Algorithm/Alignment/VectorConstraints")
    attitude = (ROOT / "plugins/builtin/silverstar_algorithm_common"
                / "payload/Algorithm/Common")
    fixture = ROOT / "tests/fixtures/alignment/test_vector_strategy.c"
    harness = tmp_path / "strategy_boundary.c"
    harness.write_text(
        '#define main ExistingVectorStrategyFixtureMain\n'
        f'#include "{fixture.as_posix()}"\n#undef main\n' + r"""
int main(void)
{
    AlignmentStrategyContext context;
    AlignmentStrategyConfig config = Test_ConfigGet(0U);
    AlignmentStrategySample sample = Test_SampleGet(10000ULL, 0U);
    AlignmentStrategyOutput output;
    unsigned int attempt;
    assert(ExistingVectorStrategyFixtureMain() == 0);
    config.constraints[1].weight = 1.0e-8F; /* Numerically unobservable yaw. */
    AlignmentStrategy_Init(&context);
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    /* Existing strategy retries failed solves until maximum_samples=4.
     * ACCEPTED acknowledges the sample; only READY publishes alignment. */
    for (attempt = 0U; attempt < 3U; attempt++)
    {
        sample.timestamp_us += 5000ULL;
        assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
            &output) == ((attempt < 2U) ? ALIGNMENT_STRATEGY_PROCESS_ACCEPTED :
                ALIGNMENT_STRATEGY_PROCESS_REJECTED));
        assert(output.q_nb[0] == 0.0F && output.q_nb[1] == 0.0F &&
            output.q_nb[2] == 0.0F && output.q_nb[3] == 0.0F);
    }
    assert(context.sample_count == 0U && context.reject_count == 1U);
    return 0;
}
""", encoding="utf-8")
    executable = tmp_path / "strategy_boundary.exe"
    _Command_Run([
        _Compiler_Get(), "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(COMMON / "Inc"), "-I" + str(strategy / "Inc"),
        "-I" + str(attitude / "Inc"),
        str(COMMON / "Src/vector_constraints.c"),
        str(COMMON / "Src/attitude_alignment.c"),
        str(strategy / "Src/alignment_strategy_binding.c"),
        str(attitude / "Src/attitude_frame.c"), str(harness), "-lm",
        "-o", str(executable)], tmp_path, "compile")
    _Command_Run([str(executable)], tmp_path, "run")
