/* Real generated backend, real mission engine, calibration math and adapter.
 * Sensor/estimator publication is injected here; producer proof is a separate test. */
#if defined(CONTROL_RESEARCH_HOST_TRAP_CAPTURE)
#include <setjmp.h>
static jmp_buf s_terminal_return;
static _Noreturn void ControlReview_TerminalTrap(void) { longjmp(s_terminal_return, 1); }
#define __builtin_trap() ControlReview_TerminalTrap()
#include "D:/python_software/SilverStar/.work/0.1.3-software-completion-20261101/control/pytest-v5/control-research-pid0/Flight_Controller/Common/Src/silverstar_assert.c"
#undef __builtin_trap
#endif
#include "../../APP/Src/control_research.c"
#include "estimator_task.h"
#include "system_inertial.h"
#include "system_calibration.h"
#include "system_source_selector.h"
#include <assert.h>
#include <stdio.h>

static uint64_t s_now = 1000000U;
static SystemLifecycleState s_lifecycle = SYSTEM_STATE_FLIGHT;
static EstimatorOutputSnapshot s_navigation;
static SystemInertialSample s_imu;
static uint32_t s_generation = 7U;
static uint32_t s_faults;
static uint8_t s_generation_race;
static uint32_t s_lock_depth;
static uint8_t s_read_fault;
static uint8_t s_read_fault_blocked;
static uint8_t s_compute_overrun;
static uint8_t s_watch_stop, s_stop_observed, s_watch_schedule, s_schedule_coherent;
#if defined(CONTROL_RESEARCH_HOST_TRAP_CAPTURE)
static ControlResearchSnapshot s_fault_output, s_fault_before;
#endif

PlatformCriticalState PlatformCritical_Enter(void)
{ uint32_t old = s_lock_depth; s_lock_depth++; return old; }
void PlatformCritical_Exit(PlatformCriticalState old)
{
    assert(s_lock_depth == old + 1U); s_lock_depth = old;
    if ((old == 0U) && (s_watch_stop != 0U) &&
        ((s_control.state == ControlResearchState_Stopped) || (s_control.state == ControlResearchState_Failed)))
    {
        ControlResearchSnapshot snapshot;
        s_watch_stop = 0U;
        assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready);
        s_stop_observed = 1U;
    }
    if ((old == 0U) && (s_watch_schedule != 0U) && (s_output.sequence > 1U))
    {
        s_watch_schedule = 0U;
        s_schedule_coherent = (uint8_t)(s_control.next_us == s_output.scheduled_us + CONTROL_RESEARCH_PERIOD_US);
    }
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    uint64_t before = s_now;
    if (s_compute_overrun != 0U) { s_now += 2001U; s_compute_overrun = 0U; }
    return before;
}
SystemLifecycleState SystemLifecycle_GetState(void)
{
    SystemLifecycleState before = s_lifecycle;
    if (s_read_fault != 0U)
    {
        if (s_lock_depth == 0U) { s_lifecycle = SYSTEM_STATE_FAULT; s_read_fault = 0U; }
        else { s_read_fault_blocked = 1U; }
    }
    return before;
}
void SystemLifecycle_EnterFault(uint32_t reason)
{ assert(reason != 0U); s_faults++; s_lifecycle = SYSTEM_STATE_FAULT; }
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{ *snapshot = s_navigation; return s_navigation.initialized; }
SystemDeviceResult EstimatorTask_ControlProvenanceCheck(const SystemNavigationProvenance *provenance,
    uint64_t timestamp_us, uint32_t sequence)
{
    if ((provenance == NULL) || (provenance->valid != 1U) ||
        (s_navigation.attitude_provenance.valid != 1U) || (s_navigation.health_flags != 0U) ||
        (timestamp_us > s_navigation.timestamp_us) || (sequence > s_navigation.update_sequence))
    { return SYSTEM_DEVICE_NOT_READY; }
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{ *sample = s_imu; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *source)
{ *source = 2U; return SYSTEM_DEVICE_OK; }
uint32_t SystemCalibration_GenerationGet(void) { return s_generation; }
uint8_t SystemCalibration_IsReady(void) { return 1U; }
SystemDeviceResult SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *correction)
{
    (void)memset(correction, 0, sizeof(*correction));
    correction->ready = 1U;
    for (unsigned i = 0U; i < 3U; i++) { correction->accel_scale[i] = 1.0f; correction->gyro_scale[i] = 1.0f; }
    correction->gyro_bias_radps[1] = .01f;
    if (s_generation_race) { s_generation++; }
    return SYSTEM_DEVICE_OK;
}

static void Sample_Set(uint64_t time)
{
    s_now = time;
    s_navigation.timestamp_us = time;
    s_navigation.update_sequence++;
    s_navigation.initialized = 1U;
    s_navigation.mission_running = 1U;
    s_navigation.q_nb[0] = cosf(.05f);
    s_navigation.q_nb[2] = sinf(.05f);
    s_navigation.attitude_provenance = (SystemNavigationProvenance){7U, 0U, 2U, 1U};
    s_imu.sample_timestamp_us = time;
    s_imu.sequence++;
    s_imu.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    s_imu.canonical_source_instance = 2U;
    s_imu.canonical_source_valid = 1U;
    s_imu.gyro_b_radps[1] = .03f;
}

static void Stage_Step(uint8_t started)
{
    SystemMissionProcessInput input = {0};
    input.now_us = s_now;
    input.events = started ? 3U : 1U;
    input.mission_started = started;
    SystemMissionProcessResult result = SystemMissionProcess_Step(&input);
    assert(result != SystemMissionProcessResult_Invalid);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    const char *scenario = argv[1];
    ControlResearchSnapshot snapshot;
    SystemMissionProcess_Init(); ControlResearch_Init();
    Stage_Step(0U);
    assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Waiting);
    assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready);
    Sample_Set(1002000U); Stage_Step(1U);
    if (!strcmp(scenario, "startup_timeout"))
    {
        s_navigation.initialized = 0U;
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Waiting);
        s_now += 22000U;
        assert(ControlResearch_RuntimeProcess() != ControlResearchResult_Ok && s_faults);
        puts("PASS startup_timeout"); return 0;
    }
    assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Ok);
    assert(ControlResearch_SnapshotGet(&snapshot) == ControlResearchResult_Ok);
    assert(snapshot.ready && snapshot.sequence == 1U && fabsf(snapshot.angle_rad - .1f) < 1e-6f);
    assert(fabsf(snapshot.rate_radps - .02f) < 1e-7f && fabsf(snapshot.command) <= 1.0f);
    if (!strcmp(scenario, "read_fault"))
    {
        s_read_fault = 1U;
        ControlResearchResult result = ControlResearch_SnapshotGet(&snapshot);
        if (s_lifecycle == SYSTEM_STATE_FAULT)
        { assert(result != ControlResearchResult_Ok && !snapshot.ready && !snapshot.command); }
        else { assert(s_read_fault_blocked && result == ControlResearchResult_Ok); }
        puts("PASS coherent publication excludes asynchronous fault interleave"); return 0;
    }
    if (!strcmp(scenario, "cached_expiry"))
    {
        s_now += 12001U;
        assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready && snapshot.command == 0.0f);
        puts("PASS cached_expiry"); return 0;
    }
    if (!strcmp(scenario, "cached_source_revoked"))
    {
        s_navigation.attitude_provenance.valid = 0U;
        assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready && !snapshot.command);
        puts("PASS source revoked before task next poll"); return 0;
    }
    uint32_t first_sequence = s_navigation.update_sequence;
    Sample_Set(1012000U); Stage_Step(1U);
#if defined(CONTROL_RESEARCH_HOST_TRAP_CAPTURE)
    if (!strcmp(scenario, "corrupt_state") || !strcmp(scenario, "corrupt_backend") ||
        !strcmp(scenario, "sequence_exhausted") || !strcmp(scenario, "corrupt_sink"))
    {
        if (!strcmp(scenario, "corrupt_state")) { s_control.state = (ControlResearchState)255; }
        if (!strcmp(scenario, "corrupt_backend")) { s_control.backend_started = 2U; }
        if (!strcmp(scenario, "sequence_exhausted")) { s_output.sequence = UINT32_MAX; }
        if (!strcmp(scenario, "corrupt_sink")) { s_output.ready = 2U; }
        (void)memset(&s_fault_output, 0xa5, sizeof(s_fault_output)); s_fault_before = s_fault_output;
        if (setjmp(s_terminal_return) == 0)
        {
            if (!strcmp(scenario, "corrupt_sink")) { (void)ControlResearch_SnapshotGet(&s_fault_output); }
            else { (void)ControlResearch_RuntimeProcess(); }
            assert(0);
        }
        SilverStarAssertFaultRecord record;
        assert(SilverStarAssert_FaultRecordGet(&record) == 1U && record.module_id == SILVERSTAR_ASSERT_MODULE_APP);
        assert(s_output.ready == 0U && s_output.command == 0.0f);
        assert(memcmp(&s_fault_output, &s_fault_before, sizeof(s_fault_output)) == 0);
        puts("PASS real fail-stop record; publication revoked; Host-only trap interception"); return 0;
    }
#endif
    if (!strcmp(scenario, "schedule_interleave"))
    {
        s_watch_schedule = 1U;
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Ok);
        assert(s_schedule_coherent == 1U);
        puts("PASS schedule is committed with publication under one lock"); return 0;
    }
    if (!strcmp(scenario, "normal") || !strcmp(scenario, "stop") || !strcmp(scenario, "stop_interleave"))
    {
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Ok);
        Sample_Set(1022000U); Stage_Step(1U); /* New stage, same controller context. */
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Ok);
        assert(ControlResearch_SnapshotGet(&snapshot) == ControlResearchResult_Ok && snapshot.sequence == 3U);
        assert(s_control.start_us == 1002000U && s_control.backend_started == 1U);
        Sample_Set(1042000U); Stage_Step(1U);
        if (!strcmp(scenario, "stop_interleave")) { s_watch_stop = 1U; }
#if defined(CONTROL_RESEARCH_HOST_TRAP_CAPTURE)
        if (setjmp(s_terminal_return) != 0)
        { fputs("FAIL ordinary stop triggered terminal assertion at publication interleave\n", stderr); return 1; }
#endif
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Stopped);
        if (!strcmp(scenario, "stop_interleave")) { assert(s_stop_observed == 1U); }
        assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready && !snapshot.command);
        Sample_Set(1044000U);
        assert(ControlResearch_RuntimeProcess() == ControlResearchResult_Stopped && !s_faults);
        puts("PASS normal stop"); return 0;
    }
    if (!strcmp(scenario, "late_ok")) { Sample_Set(1014000U); }
    if (!strcmp(scenario, "overrun")) { Sample_Set(1014001U); }
    if (!strcmp(scenario, "stale")) { s_navigation.timestamp_us -= 20001U; }
    if (!strcmp(scenario, "future")) { s_imu.sample_timestamp_us++; }
    if (!strcmp(scenario, "duplicate")) { s_navigation.update_sequence = first_sequence; }
    if (!strcmp(scenario, "source")) { s_navigation.attitude_provenance.source_instance++; }
    if (!strcmp(scenario, "generation")) { s_navigation.attitude_provenance.calibration_generation++; }
    if (!strcmp(scenario, "epoch")) { s_navigation.attitude_provenance.sensor_epoch++; }
    if (!strcmp(scenario, "unknown")) { s_navigation.attitude_provenance.valid = 0U; }
    if (!strcmp(scenario, "nan")) { s_navigation.q_nb[0] = NAN; }
    if (!strcmp(scenario, "nonplanar")) { s_navigation.q_nb[3] = .1f; }
    if (!strcmp(scenario, "health")) { s_navigation.health_flags = ESTIMATOR_HEALTH_TIMING_UNQUALIFIED; }
    if (!strcmp(scenario, "calibration_race")) { s_generation_race = 1U; }
    if (!strcmp(scenario, "clock")) { s_now = 1001000U; }
    if (!strcmp(scenario, "compute_overrun")) { s_compute_overrun = 1U; }
    ControlResearchResult result = ControlResearch_RuntimeProcess();
    if (!strcmp(scenario, "late_ok"))
    { assert(result == ControlResearchResult_Ok && !s_faults); puts("PASS late_ok"); return 0; }
    assert(result != ControlResearchResult_Ok && result != ControlResearchResult_Waiting && s_faults);
    assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready && !snapshot.command);
    assert(s_control.state == ControlResearchState_Failed && !s_control.backend_started);
    s_lifecycle = SYSTEM_STATE_FLIGHT; Sample_Set(1022000U);
    assert(ControlResearch_RuntimeProcess() == ControlResearchResult_InvalidState);
    assert(ControlResearch_SnapshotGet(&snapshot) != ControlResearchResult_Ok && !snapshot.ready);
    puts("PASS fault latched, no stale publication");
    return 0;
}
