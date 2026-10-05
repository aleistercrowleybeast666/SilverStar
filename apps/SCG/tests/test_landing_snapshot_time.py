"""Compile the real snapshot acquisition function with a preemption fixture."""
import os
import subprocess


def _compile_and_run(source, tmp_path):
    fixture = tmp_path / "snapshot_time.c"
    fixture.write_text(source, encoding="utf-8")
    output = tmp_path / "snapshot_time.exe"
    env = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    env["PATH"] = "D:/msys64/ucrt64/bin;" + env.get("PATH", "")
    command = ["D:/msys64/ucrt64/bin/gcc.exe", "-std=c11", "-Wall", "-Wextra", "-Werror",
               str(fixture), "-o", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(output)], env=env)
    assert result.returncode == 0


def test_landing_time_read_after_snapshots(tmp_path, workspace_root):
    app = (workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/flight_task.c").read_text(encoding="utf-8")
    start = app.index("static void FlightTask_FlightRecoveryInputGet(")
    end = app.index("\n#if", start)
    source = r'''
#include <stdint.h>
#include <string.h>
#include <stddef.h>
typedef struct {
    uint64_t now_us, mission_time_ms, inertial_timestamp_us, barometer_timestamp_us;
} SystemFlightRecoveryInput;
static uint64_t clock_us = 1000000;
static uint64_t SystemTime_GetMonotonicUs(void) { return clock_us; }
static uint8_t SystemTime_IsMissionStarted(void) { return 1; }
static uint64_t SystemTime_GetMissionUs(void) { return clock_us; }
static void FlightTask_RecoveryEstimatorInputApply(SystemFlightRecoveryInput *input)
{ clock_us += 20; input->barometer_timestamp_us = clock_us; }
static void FlightTask_RecoveryInitialInputApply(SystemFlightRecoveryInput *input)
{ (void)input; clock_us += 20; }
static void FlightTask_RecoveryInertialInputApply(SystemFlightRecoveryInput *input)
{ clock_us += 20; input->inertial_timestamp_us = clock_us; }
'''
    source += app[start:end]
    source += r'''
int main(void) {
    SystemFlightRecoveryInput input;
    FlightTask_FlightRecoveryInputGet(&input);
    if (input.now_us != 1000060 || input.inertial_timestamp_us != 1000060 ||
        input.barometer_timestamp_us != 1000020) { return 1; }
    if (input.inertial_timestamp_us > input.now_us ||
        input.barometer_timestamp_us > input.now_us) { return 2; }
    return 0;
}
'''
    _compile_and_run(source, tmp_path)


def test_rejected_imu_correction_keeps_observation_identity(tmp_path, workspace_root):
    app = (workspace_root / "plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/flight_task.c").read_text(encoding="utf-8")
    start = app.index("static void FlightTask_RecoveryInertialInputApply(")
    end = app.index("static void FlightTask_FlightRecoveryInputGet(", start)
    source = r'''
#include <stdint.h>
#include <stddef.h>
#define SILVERSTAR_ASSERT_OBJECT(p,t,m) ((void)(p))
#define SYSTEM_DEVICE_OK 0
#define SYSTEM_INERTIAL_VALID_ACCEL 1U
#define SYSTEM_INERTIAL_VALID_GYRO 2U
typedef int SystemCalibrationImuCorrection;
typedef struct {
    uint64_t sample_timestamp_us;
    uint32_t sequence, valid_mask;
    float accel_b_mps2[3], gyro_b_radps[3];
} SystemInertialSample;
typedef struct {
    uint64_t inertial_timestamp_us;
    uint32_t inertial_sequence;
    uint8_t corrected_accel_valid, corrected_gyro_valid;
    float corrected_accel_b_mps2[3], corrected_gyro_b_radps[3];
} SystemFlightRecoveryInput;
static int SystemInertial_LatestGet(SystemInertialSample *sample)
{
    *sample = (SystemInertialSample){.sample_timestamp_us=123456, .sequence=78,
                                   .valid_mask=3};
    return 0;
}
static int SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *correction)
{ *correction=0; return 0; }
static int SystemCalibration_ImuCorrectionApply(const float *a, const float *g,
    const SystemCalibrationImuCorrection *c, float *out_a, float *out_g)
{ (void)a; (void)g; (void)c; (void)out_a; (void)out_g; return 1; }
'''
    source += app[start:end]
    source += r'''
int main(void) {
    SystemFlightRecoveryInput input = {0};
    FlightTask_RecoveryInertialInputApply(&input);
    return (input.inertial_timestamp_us != 123456 || input.inertial_sequence != 78 ||
            input.corrected_accel_valid != 0 || input.corrected_gyro_valid != 0);
}
'''
    _compile_and_run(source, tmp_path)
