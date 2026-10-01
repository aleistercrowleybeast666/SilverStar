"""Regression tests for the source Power of Ten checker, independent of firmware."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def checker_fixture(tmp_path: Path) -> Path:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if shell is None:
        pytest.skip("PowerShell is unavailable")
    source = Path(__file__).resolve().parents[1] / (
        "plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1"
    )
    tools = tmp_path / "Tools"
    tools.mkdir()
    shutil.copy2(source, tools / source.name)
    (tmp_path / "Makefile").write_text(
        "FIRST_PARTY_C_SOURCES := APP/fixture.c\n"
        "FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror "
        "-Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 "
        "-Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes "
        "-Wmissing-prototypes -Wswitch-enum -Wvla\n"
        "power10-check:\n\t@echo check\n",
        encoding="utf-8",
    )
    (tmp_path / "STM32F407XX_FLASH.ld").write_text(
        "_Min_Heap_Size = 0x0;\n", encoding="utf-8"
    )
    app = tmp_path / "APP"
    app.mkdir()
    (app / "fixture.c").write_text(
        "void Fixture(int count, int size)\n{\n"
        "    SILVERSTAR_ASSERT(count > 0, MODULE, REASON);\n"
        "    SILVERSTAR_ASSERT(size > 0, MODULE, REASON);\n}\n",
        encoding="utf-8",
    )
    return tmp_path


def _PowerShell_Run(root: Path, expression: str) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    assert shell is not None
    probe = root / "probe.ps1"
    probe.write_text(
        '. "$PSScriptRoot/Tools/check_power_of_ten.ps1"\n'
        f"if (-not ({expression})) {{ throw 'checker regression' }}\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )


def test_entire_target_zero_runtime_candidates_blocks_acceptance(checker_fixture: Path) -> None:
    (checker_fixture / "APP/fixture.c").write_text(
        "int Fixture(int value)\n{\n    return value;\n}\n", encoding="utf-8")
    shell = shutil.which("powershell") or shutil.which("pwsh")
    assert shell is not None
    # Match the generated Make/GUI interface. Dot sourcing returns from the
    # included script on exit and allows the surrounding probe to finish at 0.
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(checker_fixture / "Tools/check_power_of_ten.ps1")],
        cwd=checker_fixture, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False)
    assert result.returncode != 0
    assert "Entire current target has zero eligible runtime assertion candidates" in result.stdout


@pytest.mark.parametrize("separator", ("/", "\\"))
def test_authorized_paths_match_both_separators(
    checker_fixture: Path, separator: str,
) -> None:
    estimator = f"APP{separator}Src{separator}estimator_task.c"
    hooks = f"OS{separator}FreeRTOS{separator}freertos_hooks.c"
    expression = (
        f"(Test-PowerTenApprovedConditional '{estimator}' "
        "'#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)') -and "
        f"(Test-PowerTenApprovedDoublePointer '{hooks}' "
        "'    StaticTask_t **task_control,')"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "expression",
    (
        "Test-PowerTenApprovedConditional 'APP/Src/other_estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)'",
        "Test-PowerTenApprovedConditional 'Other/APP/Src/estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)'",
        "Test-PowerTenApprovedConditional 'APP/Src/estimator_task.c' '#if (SYSTEM_BUILD_ESTIMATOR_ENABLED == 1U)'",
        "Test-PowerTenApprovedDoublePointer 'OS/FreeRTOS/other_freertos_hooks.c' 'StaticTask_t **task_control,'",
        "Test-PowerTenApprovedDoublePointer 'Other/OS/FreeRTOS/freertos_hooks.c' 'StaticTask_t **task_control,'",
        "Test-PowerTenApprovedDoublePointer 'OS/FreeRTOS/freertos_hooks.c' 'uint8_t **user_buffer,'",
    ),
)
def test_similar_paths_and_unauthorized_code_get_no_exception(
    checker_fixture: Path, expression: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, f"-not ({expression})")
    assert result.returncode == 0, result.stdout + result.stderr


def test_known_constant_object_assertions_do_not_count(
    checker_fixture: Path,
) -> None:
    expression = (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT_OBJECT(&sample, Sample, MODULE); "
        "SILVERSTAR_ASSERT_OBJECT(s_seq, uint32_t, MODULE); "
        "SILVERSTAR_ASSERT(1U, MODULE, REASON);' @('s_seq')) -eq 0"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr


def test_runtime_pointer_and_state_assertions_still_count(
    checker_fixture: Path,
) -> None:
    expression = (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT_OBJECT(report, Report, MODULE); "
        "SILVERSTAR_ASSERT(report->completed <= 1U, MODULE, REASON);' @()) -eq 2"
    )
    result = _PowerShell_Run(checker_fixture, expression)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("predicate", (
    "1", "0U", "(1U)", "true", "2 > 1", "count == count",
    "count <= count", "count != count", "count++ > 0", "count = 1",
    "Update() != 0", "sizeof(sample) > 0", "1U || count", "count && 0U",
    "&sample != NULL",
))
def test_invalid_predicates_get_no_density_credit(
    checker_fixture: Path, predicate: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        f"'SILVERSTAR_ASSERT({predicate}, MODULE, REASON);' @()) -eq 0"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


def test_duplicate_and_multiline_predicates(checker_fixture: Path) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT(count > 0, M, R); "
        "SILVERSTAR_ASSERT( count>0, M, OTHER_REASON); "
        "SILVERSTAR_ASSERT_OBJECT(report, Report, M); "
        "SILVERSTAR_ASSERT(report != NULL, M, R); "
        "SILVERSTAR_ASSERT((count < limit) &&\n (size > 0), M, R);' @()) -eq 3"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


def test_fixed_local_pointer_and_array_get_no_credit(checker_fixture: Path) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        "'int array[4]; int *fixed = &sample; "
        "SILVERSTAR_ASSERT_OBJECT(array, int, M); "
        "SILVERSTAR_ASSERT_OBJECT(fixed, int, M);' @()) -eq 0"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


def test_static_object_explicit_null_check_gets_no_credit(checker_fixture: Path) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        "'SILVERSTAR_ASSERT(s_state != NULL, M, R); "
        "SILVERSTAR_ASSERT_OBJECT(s_state, State, M);' @('s_state')) -eq 0"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


def _Checker_Run(root: Path, target: str = "Flight") -> subprocess.CompletedProcess[str]:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    assert shell is not None
    return subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "Tools/check_power_of_ten.ps1"), "-TargetKind", target],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=False,
    )


@pytest.mark.parametrize("counts", ((2, 1), (2, 2), (3, 2), (4, 0), (2, 0)))
@pytest.mark.parametrize("target", ("Flight", "Ground"))
def test_average_is_informational_and_includes_short_and_zero_functions(
    checker_fixture: Path, counts: tuple[int, int], target: str,
) -> None:
    functions = []
    for i, count in enumerate(counts):
        functions.append(f"void Function{i}(int value)\n{{\n" + "".join(
            f"    SILVERSTAR_ASSERT(value != {j}, MODULE, REASON);\n"
            for j in range(count)
        ) + "}\n")
    (checker_fixture / "APP/fixture.c").unlink()
    common = checker_fixture / "Common"
    common.mkdir()
    (common / "fixture.c").write_text("\n".join(functions), encoding="utf-8")
    makefile = checker_fixture / "Makefile"
    makefile.write_text(makefile.read_text(encoding="utf-8") + "LDFLAGS := -TSTM32F407XX_FLASH.ld\n", encoding="utf-8")
    result = _Checker_Run(checker_fixture, target)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"functions=2|eligible_assertions={sum(counts)}|" in result.stdout
    assert "|informational|policy=fprime_inspired_c|" in result.stdout
    assert "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending" in result.stdout


def test_third_party_assertions_cannot_raise_first_party_average(checker_fixture: Path) -> None:
    (checker_fixture / "APP/fixture.c").write_text(
        "void Sparse(int value)\n{\n SILVERSTAR_ASSERT(value > 0, M, R);\n}\n",
        encoding="utf-8",
    )
    vendor = checker_fixture / "Middlewares/Third_Party"
    vendor.mkdir(parents=True)
    (vendor / "dense.c").write_text("void Dense(void) { " + "SILVERSTAR_ASSERT(1, M, R);" * 100 + " }", encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0
    assert "files=1|functions=1|eligible_assertions=1|" in result.stdout


def test_other_rules_still_fail_above_density_threshold(checker_fixture: Path) -> None:
    path = checker_fixture / "APP/fixture.c"
    path.write_text(path.read_text(encoding="utf-8").replace("}\n", " goto Fail;\nFail: return;\n}\n"), encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 1
    assert "goto/setjmp/longjmp violation" in result.stdout
    assert "eligible_assertions=2|average=2.000000|" in result.stdout


def test_empty_scan_fails(checker_fixture: Path) -> None:
    (checker_fixture / "APP/fixture.c").write_text("", encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 1
    assert "functions=0|eligible_assertions=0|" in result.stdout


def test_sparse_long_function_is_nonblocking(checker_fixture: Path) -> None:
    source = "void Sparse(int value)\n{\n" + "    value += 1;\n" * 21 + "}\n"
    source += "void Dense(int value)\n{\n" + "".join(
        f"    SILVERSTAR_ASSERT(value != {j}, M, R);\n" for j in range(4)
    ) + "}\n"
    (checker_fixture / "APP/fixture.c").write_text(source, encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "POWER10_RULE5_RECOMMENDATION|APP\\fixture.c|1|Sparse|24|zero_runtime_candidates|nonblocking" in result.stdout


@pytest.mark.parametrize("ending", ("\n", "\r\n"))
def test_literal_continuation_preserves_function_coverage(
    checker_fixture: Path, ending: str,
) -> None:
    source = 'const char *text = "one\\\ntwo";\n'
    source += "void Later(int a, int b)\n{\n"
    source += " SILVERSTAR_ASSERT(a > 0, M, R);\n SILVERSTAR_ASSERT(b > 0, M, R);\n}\n"
    (checker_fixture / "APP/fixture.c").write_bytes(source.replace("\n", ending).encode())
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "functions=1|eligible_assertions=2|" in result.stdout


def test_utf8_real_jy_source_has_identical_lf_crlf_coverage(checker_fixture: Path) -> None:
    source = Path(__file__).resolve().parents[1] / (
        "plugins/builtin/silverstar_device_imu_jy901b/payload/"
        "Devices/IMU/JY901B/Src/jy901b_device.c"
    )
    data = source.read_bytes().replace(b"\r\n", b"\n")
    rows = []
    for contents in (data, data.replace(b"\n", b"\r\n")):
        (checker_fixture / "APP/fixture.c").write_bytes(contents)
        result = _Checker_Run(checker_fixture)
        assert result.returncode == 0  # Low density is informational; review remains pending.
        rows.append([line for line in result.stdout.splitlines()
                     if line.startswith("POWER10_RULE5_FUNCTION|")])
    assert rows[0] == rows[1]
    assert any("|IMU_Poll|" in row for row in rows[0])
    assert any("|IMU_EnsureQuaternionOutput|" in row for row in rows[0])


def test_invalid_source_encoding_is_failure_not_silent_exclusion(checker_fixture: Path) -> None:
    (checker_fixture / "APP/invalid.c").write_bytes(b"// invalid UTF8: \xff\n")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 1
    assert "Source cannot be decoded as UTF-8: APP\\invalid.c" in result.stdout
    assert "files=2|functions=1|eligible_assertions=2|" in result.stdout


@pytest.mark.parametrize("conditional", (False, True))
def test_utf8_bom_preserves_coverage_and_other_rule_diagnostics(
    checker_fixture: Path, conditional: bool,
) -> None:
    path = checker_fixture / "APP/fixture.c"
    data = path.read_bytes()
    if conditional:
        data = b"#if FORBIDDEN\n" + data + b"#endif\n"
    path.write_bytes(b"\xef\xbb\xbf" + data)
    result = _Checker_Run(checker_fixture)
    assert result.returncode == (1 if conditional else 0), result.stdout + result.stderr
    assert "functions=1|eligible_assertions=2|" in result.stdout
    if conditional:
        assert "first-party C conditional compilation violation" in result.stdout


@pytest.mark.parametrize("ending", ("\n", "\r\n"))
@pytest.mark.parametrize("bom", (b"", b"\xef\xbb\xbf"))
def test_first_character_and_function_location_preserved(
    checker_fixture: Path, ending: str, bom: bytes,
) -> None:
    path = checker_fixture / "APP/fixture.c"
    source = '#include "unused.h"\n\n' + path.read_text(encoding="utf-8")
    path.write_bytes(bom + source.replace("\n", ending).encode())
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "POWER10_RULE5_FUNCTION|Flight|APP\\fixture.c|3|Fixture|5|2" in result.stdout


@pytest.mark.parametrize("ending", ("\n", "\r\n"))
@pytest.mark.parametrize("bom", (b"", b"\xef\xbb\xbf"))
@pytest.mark.parametrize("macro", (
    "#define VALUES \\\n (1U | \\\n  2U | \\\n  4U)\n",
    "#define DEFINE_GHOST \\\n void Ghost(int value) { \\\n SILVERSTAR_ASSERT(value > 0, M, R); \\\n SILVERSTAR_ASSERT(value < 10, M, R); \\\n }\n",
))
def test_macro_continuations_do_not_create_or_inflate_functions(
    checker_fixture: Path, ending: str, bom: bytes, macro: str,
) -> None:
    path = checker_fixture / "APP/fixture.c"
    source = macro + path.read_text(encoding="utf-8")
    path.write_bytes(bom + source.replace("\n", ending).encode())
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    start = macro.count("\n") + 1
    assert f"POWER10_RULE5_FUNCTION|Flight|APP\\fixture.c|{start}|Fixture|5|2" in result.stdout
    assert "functions=1|eligible_assertions=2|" in result.stdout
    assert "|Ghost|" not in result.stdout


@pytest.mark.parametrize("statement", (
    "SILVERSTAR_ASSERT_OBJECT((&sample), Sample, M);",
    "SILVERSTAR_ASSERT_OBJECT((((&sample))), Sample, M);",
    "SILVERSTAR_ASSERT_OBJECT((void *)&s_state, State, M);",
    "SILVERSTAR_ASSERT_OBJECT(((const State *)(&s_state)), State, M);",
    "SILVERSTAR_ASSERT_OBJECT((void *)((State *)&sample), State, M);",
    "SILVERSTAR_ASSERT(((void *)&s_state) != NULL, M, R);",
    "SILVERSTAR_ASSERT(NULL != ((void *)&s_state), M, R);",
    "SILVERSTAR_ASSERT((1U || count), M, R);",
    "SILVERSTAR_ASSERT(((true || count)), M, R);",
    "SILVERSTAR_ASSERT((count || true), M, R);",
    "SILVERSTAR_ASSERT((false && count), M, R);",
    "SILVERSTAR_ASSERT((count && false), M, R);",
    "SILVERSTAR_ASSERT((0U && count), M, R);",
    "SILVERSTAR_ASSERT((count && 0U), M, R);",
))
def test_nested_fixed_addresses_and_boolean_constants_get_no_credit(
    checker_fixture: Path, statement: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, (
        f"(Get-MeaningfulAssertionCount '{statement}' @()) -eq 0"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("predicate", (
    "count <= sizeof(array)",
    "(count <= sizeof((array)))",
    "count < sizeof(array) / sizeof(array[0])",
    "(count >= 0) && (count <= sizeof(array))",
    "isfinite(data[0]) && count <= sizeof(array)",
))
def test_capacity_predicates_with_sizeof_remain_candidates(
    checker_fixture: Path, predicate: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        f"'SILVERSTAR_ASSERT({predicate}, M, R);' @()) -eq 1"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("operand", ("(report)", "((Report *)report)", "(void *)(report)"))
def test_parenthesized_runtime_pointer_stays_one_candidate(
    checker_fixture: Path, operand: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        f"'SILVERSTAR_ASSERT_OBJECT({operand}, Report, M); "
        "SILVERSTAR_ASSERT(report != NULL, M, R);' @()) -eq 1"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("code_lines,reported", ((10, False), (11, True)))
def test_fprime_inspired_recommendation_boundary_and_pending_review(
    checker_fixture: Path, code_lines: int, reported: bool,
) -> None:
    source = "void Review(int value)\n{\n" + " value += 1;\n" * (code_lines - 3) + "}\n"
    # This test isolates the per-function recommendation. A separate real
    # boundary in this target keeps it outside the all-zero hard protection.
    source += "void Boundary(int capacity)\n{\n SILVERSTAR_ASSERT(capacity > 0, M, R);\n}\n"
    (checker_fixture / "APP/fixture.c").write_text(source, encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("POWER10_RULE5_RECOMMENDATION|" in result.stdout) is reported
    assert f"|Review|{code_lines}|0" in result.stdout
    assert "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending" in result.stdout
    assert "Critical-contract review NOT PROVEN" in result.stdout


@pytest.mark.parametrize("predicate", (
    "(ready || 1U) && valid",
    "values[index || 1U] != 0",
    "condition ? (1U || count) : other",
))
def test_nested_partial_constants_do_not_erase_runtime_predicate(
    checker_fixture: Path, predicate: str,
) -> None:
    result = _PowerShell_Run(checker_fixture, (
        "(Get-MeaningfulAssertionCount "
        f"'SILVERSTAR_ASSERT({predicate}, M, R);' @()) -eq 1"
    ))
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("statement,diagnostic", (
    ("malloc(4);", "dynamic allocation violation"),
    ("while (value > 0) { value--; }", "finite while/do loop violation"),
    ("for (;;) { value += 1; }", "unapproved infinite loop"),
    ("void (*callback)(void);", "function-pointer declaration violation"),
))
def test_recommendations_do_not_override_other_safety_failures(
    checker_fixture: Path, statement: str, diagnostic: str,
) -> None:
    source = "void Unsafe(int value)\n{\n" + " value += 1;\n" * 8 + f" {statement}\n}}\n"
    (checker_fixture / "APP/fixture.c").write_text(source, encoding="utf-8")
    result = _Checker_Run(checker_fixture)
    assert result.returncode == 1
    assert diagnostic in result.stdout
    assert "POWER10_RULE5_RECOMMENDATION|" in result.stdout
    assert "POWER10_CONTRACT_REVIEW|NOT_PROVEN|manual_acceptance_pending" in result.stdout
