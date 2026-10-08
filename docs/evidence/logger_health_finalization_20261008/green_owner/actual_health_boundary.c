#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "system_user_config.h"
#include "system_lifecycle.h"
#include "system_navigation_health.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
static struct { uint8_t mission_running; } s_estimator;
static EstimatorOutputSnapshot s_snapshot;
static void Estimator_HealthEventsPublish(uint64_t evaluation_us)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemNavigationGroupHealth health = {0};
    uint8_t group, changed;
    SILVERSTAR_ASSERT_OBJECT(&health, SystemNavigationGroupHealth, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(s_estimator.mission_running <= 1U, SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_estimator.mission_running == 0U) || (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE)) { return; }
    /* Health ages remain meaningful after navigation stops, but a finalized
     * logger session has no event publisher. Keep grace/draining failures and
     * a close racing this snapshot visible through the ordinary push result. */
    if (LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED) { return; }
    changed = SystemNavigationHealth_ChangesGet(evaluation_us);
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    {
        if (((changed & (1U << group)) != 0U) &&
            (SystemNavigationHealth_GroupGet(group, evaluation_us, &health) == SYSTEM_DEVICE_OK))
        {
            uint64_t elapsed_ms = health.has_success ?
                (evaluation_us - health.last_successful_fusion_us) / 1000U : UINT32_MAX;
            uint32_t age_ms = (elapsed_ms > UINT32_MAX) ? UINT32_MAX : (uint32_t)elapsed_ms;
            if (LoggerBus_EventPush(evaluation_us, FLIGHT_LOG_EVENT_NAV_FUSION_STATE_CHANGE,
                group | ((uint32_t)health.state << 8U) | ((uint32_t)health.reason << 16U), age_ms) != LOGGER_BUS_RESULT_OK)
            { s_snapshot.health_flags |= ESTIMATOR_HEALTH_LOG_EVENT_FAILED; }
        }
    }
#else
    (void)evaluation_us;
#endif
}
/* App function above is unchanged extraction. Real bus/queue/policy/health
 * sources are linked; only IRQ/assertion boundaries and interleaving are Host. */
static uint32_t s_irq_depth;
static unsigned s_race;
static SystemLifecycleState s_lifecycle;

SystemLifecycleState SystemLifecycle_GetState(void) { return s_lifecycle; }

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState state = s_irq_depth;
    s_irq_depth++;
    return state;
}
void PlatformCritical_Exit(PlatformCriticalState state)
{
    if (s_irq_depth == 0U || state + 1U != s_irq_depth) { exit(85); }
    s_irq_depth = state;
}
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    if (condition == 0U) { exit(86); }
}
void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line)
{
    (void)alignment; (void)module; (void)file; (void)line;
    if (object == NULL) { exit(86); }
}

LoggerBusFinalizationState __real_LoggerBus_FinalizationStateGet(void);
LoggerBusFinalizationState __wrap_LoggerBus_FinalizationStateGet(void)
{
    LoggerBusFinalizationState observed = __real_LoggerBus_FinalizationStateGet();
    if (s_race != 0U)
    {
        unsigned race = s_race;
        s_race = 0U;
        TEST_CHECK(s_irq_depth == 0U);
        TEST_CHECK(LoggerBus_FinalizationArm(0ULL) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(LoggerBus_FinalizationProcess(2000000ULL) == LOGGER_BUS_FINALIZATION_DRAINING);
        if (race == 1U) { LoggerBus_FinalizationComplete(); }
    }
    return observed;
}

static void Test_Seed(void)
{
    SystemNavigationFusionEvidence evidence = {0};
    uint8_t group;
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    memset(&s_snapshot, 0, sizeof(s_snapshot));
    s_estimator.mission_running = 1U;
    SystemNavigationHealth_Reset(0ULL);
    evidence.physically_valid = 1U;
    evidence.attempted = 1U;
    evidence.effective_update = 1U;
    evidence.source = 1U;
    evidence.variance_scale = 1.0f;
    evidence.sequence = 1U;
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    { TEST_CHECK(SystemNavigationHealth_Observe(group, &evidence) == SYSTEM_DEVICE_OK); }
    (void)SystemNavigationHealth_ChangesGet(0ULL);
    /* Four groups remain fresh. Only barometer group 4 crosses the real 2 s
       health timeout. No timeout threshold or logging policy is replaced. */
    evidence.evaluation_us = 2000000ULL;
    evidence.receive_us = 2000000ULL;
    evidence.measurement_us = 2000000ULL;
    evidence.sequence = 2U;
    for (group = 0U; group < 4U; group++)
    { TEST_CHECK(SystemNavigationHealth_Observe(group, &evidence) == SYSTEM_DEVICE_OK); }
}

static LoggerBusDiagnostics Test_Diagnostics(void)
{
    LoggerBusDiagnostics diagnostics;
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    return diagnostics;
}

static void Test_TimeoutRecord(void)
{
    FlightLogRecord record;
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_EVENT);
    TEST_CHECK(record.payload.event.event_id == FLIGHT_LOG_EVENT_NAV_FUSION_STATE_CHANGE);
    TEST_CHECK(record.payload.event.arg0 == 0x00010504U);
    TEST_CHECK(record.payload.event.arg1 == 2000U);
    TEST_CHECK(record.timestamp_us == 2000000ULL);
}

int main(int argc, char **argv)
{
    unsigned scenario = (argc == 2) ? (unsigned)strtoul(argv[1], NULL, 10) : 99U;
    LoggerBusDiagnostics diagnostics;
    Test_Seed();
    s_lifecycle = (scenario == 0U || scenario == 5U || scenario == 8U) ?
        SYSTEM_STATE_FLIGHT : (scenario == 1U) ? SYSTEM_STATE_RECOVERY : SYSTEM_STATE_LANDED;
    printf("Host lifecycle=%u scenario=%u\n", (unsigned)SystemLifecycle_GetState(), scenario);
    if (scenario == 2U || scenario == 3U || scenario == 4U)
    {
        /* 1 s grace: at 2 s this is grace only when landing was at 1.5 s. */
        uint64_t landing = (scenario == 2U) ? 1500000ULL : 0ULL;
        TEST_CHECK(LoggerBus_FinalizationArm(landing) == LOGGER_BUS_RESULT_OK);
        if (scenario != 2U)
        { TEST_CHECK(LoggerBus_FinalizationProcess(2000000ULL) == LOGGER_BUS_FINALIZATION_DRAINING); }
        if (scenario == 4U) { LoggerBus_FinalizationComplete(); }
    }
    if (scenario == 5U)
    {
        unsigned i;
        for (i = 0U; i < SYSTEM_LOG_RECORD_QUEUE_DEPTH; i++)
        { TEST_CHECK(LoggerBus_EventPush(1ULL, FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_OK); }
    }
    if (scenario == 6U) { s_race = 1U; }
    if (scenario == 10U) { s_race = 2U; }
    if (scenario == 7U)
    {
        FlightLogRecord landing;
        TEST_CHECK(LoggerBus_EventPush(1500000ULL, FLIGHT_LOG_EVENT_LANDING, 0U, 0U) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(LoggerBus_FinalizationArm(1500000ULL) == LOGGER_BUS_RESULT_OK);
        Estimator_HealthEventsPublish(2000000ULL);
        TEST_CHECK(LoggerBus_Pop(&landing) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(landing.payload.event.event_id == FLIGHT_LOG_EVENT_LANDING);
        Test_TimeoutRecord();
        TEST_CHECK(LoggerBus_FinalizationProcess(2500000ULL) == LOGGER_BUS_FINALIZATION_DRAINING);
        LoggerBus_FinalizationComplete();
        TEST_CHECK(LoggerBus_FinalizationArm(2500000ULL) == LOGGER_BUS_RESULT_BAD_STATE);
        TEST_CHECK(LoggerBus_EventPush(2500000ULL, FLIGHT_LOG_EVENT_LANDING, 0U, 0U) == LOGGER_BUS_RESULT_BAD_STATE);
        diagnostics = Test_Diagnostics();
        TEST_CHECK(diagnostics.accepted_count == 2U && diagnostics.dequeued_count == 2U);
        TEST_CHECK(diagnostics.state_reject_count == 1U);
        TEST_CHECK(s_snapshot.health_flags == 0U);
        return Test_Finish("landing_and_grace_events");
    }
    if (scenario == 8U)
    {
        TEST_CHECK(LoggerBus_FinalizationArm(0ULL) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(LoggerBus_FinalizationProcess(2000000ULL) == LOGGER_BUS_FINALIZATION_DRAINING);
        LoggerBus_FinalizationComplete();
        Estimator_HealthEventsPublish(2000000ULL);
        TEST_CHECK(Test_Diagnostics().state_reject_count == 0U);
        /* Quiescent initialization, not an unsupported LANDED→START command. */
        Test_Seed();
    }
    if (scenario == 9U) { s_estimator.mission_running = 0U; }
    Estimator_HealthEventsPublish(2000000ULL);
    diagnostics = Test_Diagnostics();
    if (scenario <= 2U || scenario == 8U)
    {
        TEST_CHECK(diagnostics.accepted_count == 1U && diagnostics.normal_count == 1U);
        TEST_CHECK(diagnostics.state_reject_count == 0U && diagnostics.capacity_reject_count == 0U);
        TEST_CHECK(s_snapshot.health_flags == 0U);
        Test_TimeoutRecord();
    }
    else if (scenario == 3U || scenario == 6U || scenario == 10U)
    {
        TEST_CHECK(diagnostics.accepted_count == 0U && diagnostics.normal_count == 0U);
        TEST_CHECK(diagnostics.state_reject_count == 1U);
        TEST_CHECK(s_snapshot.health_flags == ESTIMATOR_HEALTH_LOG_EVENT_FAILED);
        TEST_CHECK(s_race == 0U);
    }
    else if (scenario == 4U || scenario == 9U)
    {
        SystemNavigationGroupHealth health;
        TEST_CHECK(diagnostics.accepted_count == 0U && diagnostics.state_reject_count == 0U);
        TEST_CHECK(s_snapshot.health_flags == 0U);
        TEST_CHECK(SystemNavigationHealth_GroupGet(4U, 2000000ULL, &health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.state == SYSTEM_NAVIGATION_DEAD_RECKONING && health.reason == 1U);
        if (scenario == 4U)
        {
            TEST_CHECK(LoggerBus_EventPush(2000000ULL, FLIGHT_LOG_EVENT_NAV_FUSION_STATE_CHANGE, 0U, 0U) == LOGGER_BUS_RESULT_BAD_STATE);
            TEST_CHECK(Test_Diagnostics().state_reject_count == 1U);
        }
    }
    else if (scenario == 5U)
    {
        TEST_CHECK(diagnostics.accepted_count == SYSTEM_LOG_RECORD_QUEUE_DEPTH);
        TEST_CHECK(diagnostics.capacity_reject_count == 1U && diagnostics.state_reject_count == 0U);
        TEST_CHECK(s_snapshot.health_flags == ESTIMATOR_HEALTH_LOG_EVENT_FAILED);
    }
    else { TEST_CHECK(0); }
    TEST_CHECK(s_irq_depth == 0U);
    return Test_Finish("logger_health_boundary");
}
