"""Instrument the real Host fixture, retaining a compact hash of every operation.

The fixture zero-initializes its contexts/events, including padding. Pointer-valued
storage identity is deliberately excluded; all stored KF/history bytes are included.
Only test code writes trace files. No instrumentation enters generated runtime code.
"""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

TRACE_WRAPPERS = r'''
static FILE *s_trace;
static uint64_t TestTrace_Hash(uint64_t hash, const void *data, size_t size)
{
    const unsigned char *bytes = data;
    size_t i;
    for (i = 0; i < size; i++) { hash = (hash ^ bytes[i]) * UINT64_C(1099511628211); }
    return hash;
}
static void TestTrace_Record(NavigationReplayContext *h, NavigationKfContext *s,
                             NavigationReplayOutcome *o, int result)
{
    uint64_t hash = UINT64_C(14695981039346656037);
    if (h != NULL)
    {
        size_t offset = offsetof(NavigationReplayContext, events);
        hash = TestTrace_Hash(hash, (const unsigned char *)h + offset, sizeof(*h) - offset);
        if (h->storage != NULL) { hash = TestTrace_Hash(hash, h->storage, sizeof(*h->storage)); }
    }
    if (s != NULL) { hash = TestTrace_Hash(hash, s, sizeof(*s)); }
    if (o != NULL) { hash = TestTrace_Hash(hash, o, sizeof(*o)); }
    (void)fwrite(&result, sizeof(result), 1, s_trace);
    (void)fwrite(&hash, sizeof(hash), 1, s_trace);
}
static NavigationReplayResult TestTrace_Predict(NavigationReplayContext *h,
    NavigationKfContext *s, uint64_t t, const float *d, float dt)
{
    NavigationReplayResult r = NavigationReplay_Predict(h, s, t, d, dt);
    TestTrace_Record(h, s, NULL, (int)r);
    return r;
}
static NavigationReplayResult TestTrace_Insert(NavigationReplayContext *h,
    NavigationKfContext *s, const NavigationReplayEvent *e, NavigationReplayOutcome *o)
{
    NavigationReplayResult r = NavigationReplay_Insert(h, s, e, o);
    TestTrace_Record(h, s, o, (int)r);
    return r;
}
static NavigationReplayResult TestTrace_Receive(NavigationReplayContext *h,
    const NavigationKfGnssEpoch *e, NavigationReplayEvent *out)
{
    NavigationReplayResult r = NavigationReplay_ReceiveTrack(h, e, out);
    TestTrace_Record(h, NULL, NULL, (int)r);
    return r;
}
#define NavigationReplay_Predict TestTrace_Predict
#define NavigationReplay_Insert TestTrace_Insert
#define NavigationReplay_ReceiveTrack TestTrace_Receive
'''


def replay_trace_run(project: Path, output: Path, fixture: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    source = fixture.read_text(encoding="utf-8")
    marker = "static NavigationReplayContext s_reference_history;"
    source = source.replace(marker, "#include <stddef.h>\n" + TRACE_WRAPPERS + "\n" + marker)
    head, main = source.split("int main(void)", 1)
    names = []
    def instrument(match):
        call = match.group(0)
        name = re.sub(r"[^A-Za-z0-9_]", "", call)
        names.append(name)
        return f's_trace = fopen("{name}.trace", "wb");\n    if (s_trace == NULL) {{ return 2; }}\n    {call}\n    (void)fclose(s_trace);'
    main = re.sub(r"Test_(?!Finish)[A-Za-z0-9_]+\([^;\n]*\);", instrument, main)
    instrumented = output / "replay_trace.c"
    instrumented.write_text(head + "int main(void)" + main, encoding="utf-8")
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra",
               "-Werror", "-pedantic", "-O2", "-include",
               str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    command += [str(project / p) for p in (
        "Algorithm/Estimator/KF6/Src/navigation_kf.c",
        "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
        "System/Src/system_navigation_health.c", "System/Src/system_time.c", "Common/Src/silverstar_assert.c")]
    command += [str(instrumented), "-lm", "-o", str(output / "trace.exe")]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    built = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    (output / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(output / "trace.exe")], cwd=output, env=env, capture_output=True, text=True, check=False)
    (output / "result.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    traces = {}
    for name in names:
        data = (output / (name + ".trace")).read_bytes()
        # Direct covariance/recovery checks need no replay-engine operation;
        # their numerical assertions are enforced by the executable exit code.
        assert len(data) % 12 == 0
        traces[name] = {"operations": len(data) // 12, "sha256": hashlib.sha256(data).hexdigest()}
    (output / "traces.json").write_text(json.dumps(traces, indent=2) + "\n", encoding="utf-8")
    return traces


def replay_work_limit_run(project: Path, output: Path, fixture: Path) -> str:
    """Inject budget exhaustion in a test-only source copy; production stays 560.

    Valid histories cannot naturally exceed that conservative bound. A one-step
    budget exercises the existing public transactional failure path on both the
    original and refactored engines without modifying their storage or math.
    """
    output.mkdir(parents=True, exist_ok=True)
    engine = project / "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c"
    injected = output / "replay_budget_fault.c"
    source = engine.read_text(encoding="utf-8")
    assert source.count("> NAV_REPLAY_MAX_STEPS") == 2
    injected.write_text(source.replace("> NAV_REPLAY_MAX_STEPS", "> 1U"), encoding="utf-8")
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-O2", "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    command += [str(project / p) for p in (
        "Algorithm/Estimator/KF6/Src/navigation_kf.c", "Common/Src/silverstar_assert.c")]
    command += [str(injected), str(fixture), "-lm", "-o", str(output / "work-limit.exe")]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    built = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(output / "work-limit.exe")], env=env, capture_output=True, text=True, check=False)
    (output / "result.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def estimator_trace_run(project: Path, output: Path, fixture: Path) -> dict:
    """Compile the actual App GNSS dispatch functions, not a rewritten model."""
    output.mkdir(parents=True, exist_ok=True)
    app = (project / "APP/Src/estimator_task.c").read_text(encoding="utf-8")
    type_end = app.index("} EstimatorGnssUpdateWork;") + len("} EstimatorGnssUpdateWork;")
    type_start = app.rfind("typedef struct", 0, type_end)
    start = app.index("static SystemMeasurementTimeResult Estimator_MeasurementTimeResolve(")
    end = app.index("static void Estimator_GnssUpdate(", start)
    source = '''#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include "navigation_kf_replay.h"
#include "navigation_integrity.h"
#include "navigation_quality.h"
#include "system_navigation_health.h"
#include "system_calibration.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "system_source_selector.h"
#include "system_user_config.h"
#include "system_gnss_if.h"
#include "system_estimator_diagnostics.h"
#include "system_estimator_profile.h"
#include "sslog_protocol.h"
#include "silverstar_assert.h"
#include "system_time.h"
#include "platform_time.h"
#include "platform_critical.h"
PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t PlatformTime_Us(void) { return 0ULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
LoggerBusResult LoggerBus_EventPush(uint64_t timestamp_us, FlightLogEventId event_id,
    uint32_t arg0, uint32_t arg1)
{
    (void)timestamp_us;
    (void)event_id;
    (void)arg0;
    (void)arg1;
    return LOGGER_BUS_RESULT_BAD_STATE;
}
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance_id)
{
    if (instance_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *instance_id = 0U;
    return SYSTEM_DEVICE_OK;
}
static struct { NavigationKfContext kf; SystemEstimatorGnssDiagnostics gnss_diagnostics; uint32_t operation_sequence; } s_estimator;
static struct { float position_innovation[3]; uint32_t health_flags; } s_snapshot;
static NavigationReplayContext s_replay;
static NavigationWindowContext s_integrity;
static uint64_t s_native_week_us;
static uint32_t s_native_previous_tow_ms;
static uint32_t s_integrity_log_failures;
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time) { (void)time; return SYSTEM_DEVICE_NOT_READY; }
'''
    conversion_start = app.index(
        "static SystemEstimatorMeasurementResult Estimator_MeasurementResultConvert("
    )
    conversion_end = app.index("\n}", conversion_start) + 2
    diagnostic_start = app.index("static void Estimator_GnssGroupDiagnosticsRefresh(")
    diagnostic_end = app.index("#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED", diagnostic_start)
    operation_start = app.index("static uint32_t Estimator_OperationNext(")
    operation_end = app.index("\n}", operation_start) + 2
    scale_start = app.index("static float Estimator_ResultScale(")
    scale_end = app.index("\n}", scale_start) + 2
    dispatch = app[start:end]
    quality_start = dispatch.index("static void Estimator_NavigationQualityLog(")
    quality_end = dispatch.index("\n}", quality_start) + 2
    dispatch = dispatch[:quality_start] + dispatch[quality_end:]
    source += (app[type_start:type_end] + "\n"
               + app[conversion_start:conversion_end] + "\n"
               + app[diagnostic_start:diagnostic_end]
               + app[operation_start:operation_end] + "\n"
               + app[scale_start:scale_end] + "\n" + dispatch
               + fixture.read_text(encoding="utf-8"))
    instrumented = output / "app_trace.c"
    instrumented.write_text(source, encoding="utf-8")
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-O2", "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    command += [str(project / p) for p in (
        "Algorithm/Estimator/KF6/Src/navigation_kf.c", "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
        "Algorithm/Estimator/KF6/Src/navigation_integrity.c",
        "Algorithm/Common/Src/navigation_quality.c",
        "System/Src/system_navigation_health.c", "System/Src/system_time.c", "Common/Src/silverstar_assert.c")]
    command.append(str(project / "System/Src/system_estimator_profile.c"))
    command += [str(instrumented), "-lm", "-o", str(output / "app.exe")]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    traces = {}
    for pos, vel in ((0, 270), (270, 0), (0, 0), (100, 100)):
        build = command + [f"-DSYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS={pos}",
                           f"-DSYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS={vel}"]
        result = subprocess.run(build, env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        result = subprocess.run([str(output / "app.exe")], env=env, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
        (output / f"app-{pos}-{vel}.trace").write_bytes(result.stdout)
        traces[f"{pos}/{vel}"] = hashlib.sha256(result.stdout).hexdigest()
    return traces


def barometer_operation_run(project: Path, output: Path, fixture: Path) -> None:
    """Compare the real App replay dispatch/log timing with a direct on-time KF."""
    output.mkdir(parents=True, exist_ok=True)
    app = (project / "APP/Src/estimator_task.c").read_text(encoding="utf-8")
    def function_get(name):
        match = re.search(r"static [^\n]+ " + name + r"\(", app)
        assert match
        start = match.start()
        end = app.index("\n}", start) + 2
        return app[start:end] + "\n"
    type_end = app.index("} EstimatorBarometerUpdateWork;") + len("} EstimatorBarometerUpdateWork;")
    type_start = app.rfind("typedef struct", 0, type_end)
    source = r'''
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "navigation_kf_replay.h"
#include "estimator_bus.h"
#include "system_navigation_health.h"
#include "estimator_task.h"
#include "system_estimator_diagnostics.h"
#include "system_estimator_profile.h"
#include "system_user_config.h"
#include "sslog_protocol.h"
#include "silverstar_assert.h"
#include "system_time.h"
#include "platform_time.h"
#include "platform_critical.h"
PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t PlatformTime_Us(void) { return 0ULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
static struct { NavigationKfContext kf; uint32_t operation_sequence; } s_estimator;
static struct { SystemEstimatorMeasurementResult baro_update_result; float baro_innovation, baro_r_scale; uint32_t health_flags; } s_snapshot;
static NavigationReplayContext s_replay;
'''
    source += app[type_start:type_end] + "\n"
    for name in ("Estimator_OperationNext", "Estimator_MeasurementResultConvert",
                 "Estimator_ResultScale", "Estimator_MeasurementTimeResolve",
                 "Estimator_ReplayInsert", "Estimator_BarometerHealthPublish",
                 "Estimator_BarometerReplay"):
        source += function_get(name)
    source += fixture.read_text(encoding="utf-8")
    instrumented = output / "barometer_app.c"
    instrumented.write_text(source, encoding="utf-8")
    script = (project / "Tests/Host/run_tests.ps1").read_text(encoding="utf-8")
    includes = re.findall(r'"-I\$repoRoot\\([^"\n]+)"', script)
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-pedantic", "-O2", "-include", str(project / "Generated/Inc/project_flight_config.h")]
    command += ["-I" + str(project / p.replace("\\", "/")) for p in includes]
    command += [str(project / p) for p in (
        "Algorithm/Estimator/KF6/Src/navigation_kf.c", "Algorithm/Estimator/KF6/Src/navigation_kf_replay.c",
        "System/Src/system_navigation_health.c", "System/Src/system_time.c", "Common/Src/silverstar_assert.c")]
    command += [str(instrumented), "-lm", "-o", str(output / "barometer.exe")]
    env = dict(os.environ, TEMP=str(output), TMP=str(output))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    for delay in (0, 100):
        result = subprocess.run(command + [f"-DSYSTEM_ESTIMATOR_BARO_MEASUREMENT_DELAY_MS={delay}"],
                                env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        result = subprocess.run([str(output / "barometer.exe")], env=env, capture_output=True, text=True, check=False)
        assert result.returncode == 0, f"delay={delay}, exit={result.returncode}: {result.stderr}"
