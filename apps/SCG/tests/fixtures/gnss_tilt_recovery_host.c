#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "flight_deployment.h"
#include "estimator_bus.h"
#include "estimator_task.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_barometer_if.h"
#include "system_flight_recovery.h"
#include "system_navigation_health.h"
#include "system_navigation_profile.h"
#include "system_time.h"

/* The test runner copies this complete function unchanged from flight_task.c. */
#include "flight_task_recovery_extract.h"

static EstimatorOutputSnapshot s_estimator;
static uint64_t s_now_us;
static unsigned int s_failures;

uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    *snapshot = s_estimator;
    return 1U;
}

uint8_t EstimatorBus_PressureGetLatest(EstimatorPressureSnapshot *snapshot)
{
    (void)snapshot;
    return 0U;
}

uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    if (condition == 0U) { abort(); }
}
void SilverStarAssert_ObjectCheck(const volatile void *object,
    uint32_t alignment, SilverStarAssertModuleId module, const char *file,
    uint32_t line)
{
    (void)alignment; (void)module; (void)file; (void)line;
    if (object == NULL) { abort(); }
}

static void Check(const char *name, uint8_t actual, uint8_t expected)
{
    if (actual != expected)
    {
        printf("FAIL %s actual=%u expected=%u\n", name,
            (unsigned int)actual, (unsigned int)expected);
        s_failures++;
    }
}

static void Health_FusedAt(uint64_t timestamp_us)
{
    SystemNavigationFusionEvidence evidence;
    uint8_t group;
    (void)memset(&evidence, 0, sizeof(evidence));
    evidence.receive_us = timestamp_us;
    evidence.measurement_us = timestamp_us;
    evidence.evaluation_us = timestamp_us;
    evidence.sequence = 1U;
    evidence.physically_valid = 1U;
    evidence.attempted = 1U;
    evidence.effective_update = 1U;
    evidence.variance_scale = 1.0f;
    for (group = 0U; group < 4U; group++)
    {
        if (SystemNavigationHealth_Observe(group, &evidence) != SYSTEM_DEVICE_OK)
        { abort(); }
    }
}

static void RunCase(const char *name, uint8_t expected_attitude,
    uint8_t expected_velocity, uint8_t expected_tilt, uint8_t expected_apogee)
{
    SystemFlightRecoveryInput recovery;
    FlightDeploymentInput deployment;
    FlightDeploymentContext context;
    FlightDeploymentConfig config;
    FlightDeploymentEvaluation evaluation;
    (void)memset(&recovery, 0, sizeof(recovery));
    FlightTask_RecoveryEstimatorInputApply(&recovery);
    Check(name, recovery.attitude_valid, expected_attitude);
    Check("velocity gate", recovery.velocity_valid, expected_velocity);
    Check("linear acceleration gate", recovery.linear_accel_valid,
        expected_attitude);
    (void)memset(&deployment, 0, sizeof(deployment));
    (void)memcpy(deployment.q_nb, recovery.q_nb, sizeof(deployment.q_nb));
    (void)memcpy(deployment.velocity_enu_mps, recovery.velocity_enu_mps,
        sizeof(deployment.velocity_enu_mps));
    deployment.attitude_valid = recovery.attitude_valid;
    deployment.velocity_valid = recovery.velocity_valid;
    (void)memset(&config, 0, sizeof(config));
    config.trigger_mask = SYSTEM_DEPLOY_TRIGGER_TILT |
        SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ;
    config.rocket_longitudinal_axis = SYSTEM_BODY_AXIS_Z_POSITIVE;
    config.tilt_reference = SYSTEM_TILT_REFERENCE_NAV_UP;
    config.tilt_threshold_deg = 90.0f;
    config.apogee_vertical_velocity_threshold_mps = -1.0f;
    if (FlightDeployment_ContextInit(&context, &config) != FLIGHT_DEPLOYMENT_INIT_OK)
    { abort(); }
    (void)FlightDeployment_ConditionEvaluate(&context, &deployment,
        &evaluation);
    Check("tilt trigger", (uint8_t)((evaluation.matched_mask &
        SYSTEM_DEPLOY_TRIGGER_TILT) != 0U), expected_tilt);
    Check("apogee trigger", (uint8_t)((evaluation.matched_mask &
        SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ) != 0U), expected_apogee);
}

int main(void)
{
    SystemNavigationFusionEvidence mismatch;
    s_now_us = 12000000ULL;
    (void)memset(&s_estimator, 0, sizeof(s_estimator));
    s_estimator.initialized = 1U;
    s_estimator.mission_running = 1U;
    s_estimator.timestamp_us = s_now_us - 20000ULL;
    s_estimator.update_sequence = 42U;
    s_estimator.q_nb[0] = cosf(50.0f * 0.01745329251994329577f);
    s_estimator.q_nb[1] = sinf(50.0f * 0.01745329251994329577f);
    s_estimator.velocity_enu_mps[2] = -5.0f;
    SystemNavigationHealth_Reset(1000000ULL);
    RunCase("GNSS outage >10s", 1U, 0U, 1U, 0U);
    s_estimator.q_nb[0] = cosf(44.5f * 0.01745329251994329577f);
    s_estimator.q_nb[1] = sinf(44.5f * 0.01745329251994329577f);
    RunCase("tilt below 90 degrees", 1U, 0U, 0U, 0U);
    s_estimator.q_nb[0] = cosf(50.0f * 0.01745329251994329577f);
    s_estimator.q_nb[1] = sinf(50.0f * 0.01745329251994329577f);
    SystemNavigationHealth_Reset(1000000ULL);
    Health_FusedAt(11500000ULL);
    RunCase("recent GNSS fusion", 1U, 1U, 1U, 1U);
    SystemNavigationHealth_Reset(1000000ULL);
    s_estimator.timestamp_us = s_now_us - 150000ULL;
    RunCase("stale estimator", 0U, 0U, 0U, 0U);
    s_estimator.timestamp_us = s_now_us - 20000ULL;
    s_estimator.q_nb[0] = NAN;
    RunCase("NaN quaternion", 0U, 0U, 0U, 0U);
    s_estimator.q_nb[0] = 0.0f;
    s_estimator.q_nb[1] = 0.0f;
    RunCase("zero quaternion", 0U, 0U, 0U, 0U);
    s_estimator.q_nb[0] = 1.0f;
    SystemNavigationHealth_ImuQualityRecord(0x02U);
    RunCase("IMU fault", 0U, 0U, 0U, 0U);
    SystemNavigationHealth_Reset(1000000ULL);
    s_estimator.health_flags = ESTIMATOR_HEALTH_KF_NUMERIC_ERROR;
    RunCase("numeric fault", 0U, 0U, 0U, 0U);
    s_estimator.health_flags = 0U;
    s_estimator.mission_running = 0U;
    RunCase("outside mission", 0U, 0U, 0U, 0U);
    s_estimator.mission_running = 1U;
    s_estimator.initialized = 0U;
    RunCase("uninitialized estimator", 0U, 0U, 0U, 0U);
    s_estimator.initialized = 1U;
    (void)memset(&mismatch, 0, sizeof(mismatch));
    mismatch.receive_us = s_now_us - 10000ULL;
    mismatch.measurement_us = mismatch.receive_us;
    mismatch.evaluation_us = mismatch.receive_us;
    mismatch.variance_scale = 1.0f;
    mismatch.reason = SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH;
    if (SystemNavigationHealth_Observe(0U, &mismatch) != SYSTEM_DEVICE_OK)
    { abort(); }
    RunCase("model mismatch", 0U, 0U, 0U, 0U);
    printf("%u failures\n", s_failures);
    return (s_failures == 0U) ? 0 : 1;
}
