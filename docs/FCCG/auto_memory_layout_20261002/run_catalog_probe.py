"""Actual Host metadata test, including independent SF6 catalog corruptions.

This isolates the unchanged function body from the owning Host test. It does
not alter the real protocol payload, generated candidates or recorded logs.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload"
PROTOCOL = ROOT / "apps/FCCG/plugins/builtin/silverstar_protocol_logging_sslog_0_0/payload/Protocol/SSLOG"
VERSION = os.environ.get("SILVERSTAR_CATALOG_VERSION", "v1")
OUT = ROOT / (".work/HostCatalogFault_" + VERSION)
OUT.mkdir(exist_ok=False)
EVIDENCE = Path(__file__).parent / ("catalog_fault_" + VERSION)
EVIDENCE.mkdir(exist_ok=False)
test = (CORE / "Tests/Host/test_logger.c").read_text()
function = test.split("static void Test_RecordMetadata(void)", 1)[1].split("static void Test_FileHeaderAndCrc(void)", 1)[0]
program = '''#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include "sslog_protocol.h"
static unsigned failures;
#define TEST_CHECK(expr) do { if (!(expr)) { failures++; fprintf(stderr, "failed line=%u: %s\\n", (unsigned)__LINE__, #expr); } } while (0)
static void Test_RecordMetadata(void)
''' + function + '''int main(void) { Test_RecordMetadata(); return failures == 0U ? 0 : 1; }
'''
(OUT / "probe.c").write_text(program)
records = (PROTOCOL / "Src/sslog_records.c").read_text()
cases = {
    "valid": records,
    "bad_state_size": records.replace("1U, FLIGHT_LOG_SF6_STATE_PAYLOAD_SIZE,", "1U, 71U,", 1),
    "bad_measurement_size": records.replace("1U, FLIGHT_LOG_SF6_MEASUREMENT_PAYLOAD_SIZE,", "1U, 55U,", 1),
    "bad_state_version": records.replace("FLIGHT_LOG_RECORD_SF6_STATE, 1U,", "FLIGHT_LOG_RECORD_SF6_STATE, 0U,", 1),
    "bad_measurement_name": records.replace('"SF6_MEASUREMENT"', '"BAD_MEASUREMENT"', 1),
    "duplicate_state_id": records.replace("FLIGHT_LOG_RECORD_SF6_MEASUREMENT, 1U,", "FLIGHT_LOG_RECORD_SF6_STATE, 1U,", 1),
}
report = {"source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (CORE / "Tests/Host/test_logger.c", PROTOCOL / "Src/sslog_records.c", PROTOCOL / "Inc/sslog_records.h")}, "cases": []}
for name, text in cases.items():
    source = OUT / (name + ".c")
    source.write_text(text)
    exe = OUT / (name + ".exe")
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections", "-I" + str(PROTOCOL / "Inc"),
        "-I" + str(CORE / "Common/Inc"), str(OUT / "probe.c"), str(source),
        str(CORE / "Common/Src/silverstar_assert.c"), "-o", str(exe)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (EVIDENCE / (name + "_compile.log")).write_text(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
    expected = 0 if name == "valid" else 1
    assert result.returncode == expected, (name, result.stderr)
    log = EVIDENCE / (name + ".log")
    log.write_text(compiled.stdout + compiled.stderr + result.stdout + result.stderr)
    report["cases"].append({"name": name, "compile_command": command, "compile_exit": compiled.returncode,
        "run_command": [str(exe)], "run_exit": result.returncode, "expected_exit": expected,
        "exe_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name, result.returncode, flush=True)
(EVIDENCE / "results.json").write_text(json.dumps(report, indent=2) + "\n")
