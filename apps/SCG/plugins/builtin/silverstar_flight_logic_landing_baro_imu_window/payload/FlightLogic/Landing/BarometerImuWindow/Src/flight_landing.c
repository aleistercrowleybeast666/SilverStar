#include "flight_landing.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

static uint8_t FlightLanding_VectorIsFinite(const float value[3])
{
    return (uint8_t)((value != NULL) && isfinite(value[0]) &&
                     isfinite(value[1]) && isfinite(value[2]));
}

static float FlightLanding_VectorNormSquared(const float value[3])
{
    return (value[0] * value[0]) + (value[1] * value[1]) +
           (value[2] * value[2]);
}

FlightLandingInitResult FlightLanding_ContextInit(
    FlightLandingContext *context,
    const FlightLandingConfig *config)
{
    if ((context == NULL) || (config == NULL))
    {
        return FLIGHT_LANDING_INIT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(config, FlightLandingConfig,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)memset(context, 0, sizeof(*context));
    if ((config->sample_max_age_ms == 0U) ||
        !isfinite(config->local_gravity_mps2) ||
        !isfinite(config->impact_threshold_mps2) ||
        !isfinite(config->still_gyro_threshold_radps) ||
        !isfinite(config->still_accel_tolerance_mps2) ||
        !isfinite(config->barometer_confirm_rate_mps) ||
        !isfinite(config->barometer_max_span_m) ||
        (config->local_gravity_mps2 <= 0.0f) ||
        (config->impact_threshold_mps2 <= 0.0f) ||
        (config->still_gyro_threshold_radps <= 0.0f) ||
        (config->still_accel_tolerance_mps2 <= 0.0f) ||
        (config->barometer_confirm_rate_mps <= 0.0f) ||
        (config->barometer_max_span_m <= 0.0f))
    {
        return FLIGHT_LANDING_INIT_INVALID_CONFIG;
    }
    context->config = *config;
    context->initialized = 1U;
    return FLIGHT_LANDING_INIT_OK;
}

FlightLandingConditionResult FlightLanding_SampleFreshEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us)
{
    uint64_t max_age_us;

    if ((context == NULL) || (context->initialized == 0U))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    max_age_us = (uint64_t)context->config.sample_max_age_ms * 1000ULL;
    return ((timestamp_us != 0ULL) && (now_us >= timestamp_us) &&
            ((now_us - timestamp_us) <= max_age_us)) ?
        FLIGHT_LANDING_CONDITION_MET :
        FLIGHT_LANDING_CONDITION_NOT_MET;
}

FlightLandingResult FlightLanding_ImpactMetricGet(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t acceleration_valid,
    const float acceleration_b_mps2[3],
    float *metric_mps2)
{
    if ((context == NULL) || (metric_mps2 == NULL) ||
        (context->initialized == 0U))
    {
        return FLIGHT_LANDING_RESULT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(metric_mps2, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if ((acceleration_valid == 0U) ||
        (FlightLanding_SampleFreshEvaluate(context, now_us, timestamp_us) !=
         FLIGHT_LANDING_CONDITION_MET) ||
        (FlightLanding_VectorIsFinite(acceleration_b_mps2) == 0U))
    {
        return FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
    }
    *metric_mps2 = sqrtf(
        FlightLanding_VectorNormSquared(acceleration_b_mps2));
    return isfinite(*metric_mps2) ? FLIGHT_LANDING_RESULT_OK :
                                    FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
}

FlightLandingConditionResult FlightLanding_PostImpactStillnessEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t acceleration_valid,
    uint8_t gyro_valid,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    float *accel_norm_mps2)
{
    float gyro_norm_squared;

    if ((context == NULL) || (accel_norm_mps2 == NULL) ||
        (context->initialized == 0U) || (gyro_valid == 0U) ||
        (FlightLanding_ImpactMetricGet(context, now_us, timestamp_us,
                                       acceleration_valid,
                                       acceleration_b_mps2,
                                       accel_norm_mps2) !=
         FLIGHT_LANDING_RESULT_OK) ||
        (FlightLanding_VectorIsFinite(gyro_b_radps) == 0U))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(accel_norm_mps2, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    gyro_norm_squared = FlightLanding_VectorNormSquared(gyro_b_radps);
    return ((gyro_norm_squared <
             (context->config.still_gyro_threshold_radps *
              context->config.still_gyro_threshold_radps)) &&
            (fabsf(*accel_norm_mps2 - context->config.local_gravity_mps2) <
             context->config.still_accel_tolerance_mps2)) ?
        FLIGHT_LANDING_CONDITION_MET :
        FLIGHT_LANDING_CONDITION_NOT_MET;
}

FlightLandingConditionResult FlightLanding_StillnessEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t inertial_timestamp_us,
    uint64_t ins_timestamp_us,
    uint8_t gyro_valid,
    uint8_t linear_acceleration_valid,
    const float gyro_b_radps[3],
    const float linear_acceleration_n_mps2[3])
{
    float gyro_threshold_squared;
    float accel_threshold_squared;

    if ((context == NULL) || (context->initialized == 0U))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    gyro_threshold_squared = context->config.still_gyro_threshold_radps *
                             context->config.still_gyro_threshold_radps;
    accel_threshold_squared = context->config.still_accel_tolerance_mps2 *
                              context->config.still_accel_tolerance_mps2;
    if ((gyro_valid == 0U) || (linear_acceleration_valid == 0U) ||
        (FlightLanding_SampleFreshEvaluate(context, now_us,
                                           inertial_timestamp_us) !=
         FLIGHT_LANDING_CONDITION_MET) ||
        (FlightLanding_SampleFreshEvaluate(context, now_us,
                                           ins_timestamp_us) !=
         FLIGHT_LANDING_CONDITION_MET) ||
        (FlightLanding_VectorIsFinite(gyro_b_radps) == 0U) ||
        (FlightLanding_VectorIsFinite(linear_acceleration_n_mps2) == 0U))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    return ((FlightLanding_VectorNormSquared(gyro_b_radps) <
             gyro_threshold_squared) &&
            (FlightLanding_VectorNormSquared(linear_acceleration_n_mps2) <
             accel_threshold_squared)) ?
        FLIGHT_LANDING_CONDITION_MET :
        FLIGHT_LANDING_CONDITION_NOT_MET;
}

FlightLandingResult FlightLanding_ImuMetricsGet(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint64_t candidate_start_us,
    uint8_t acceleration_valid,
    uint8_t gyro_valid,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    FlightLandingImuMetrics *metrics)
{
    if ((context == NULL) || (metrics == NULL) ||
        (context->initialized == 0U))
    {
        return FLIGHT_LANDING_RESULT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(metrics, FlightLandingImuMetrics,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if ((timestamp_us <= candidate_start_us) ||
        (acceleration_valid == 0U) || (gyro_valid == 0U) ||
        (FlightLanding_SampleFreshEvaluate(context, now_us, timestamp_us) !=
         FLIGHT_LANDING_CONDITION_MET) ||
        (FlightLanding_VectorIsFinite(acceleration_b_mps2) == 0U) ||
        (FlightLanding_VectorIsFinite(gyro_b_radps) == 0U))
    {
        return FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
    }
    metrics->accel_norm_mps2 = sqrtf(
        FlightLanding_VectorNormSquared(acceleration_b_mps2));
    metrics->gyro_norm_radps = sqrtf(
        FlightLanding_VectorNormSquared(gyro_b_radps));
    metrics->gravity_error_mps2 = fabsf(
        metrics->accel_norm_mps2 - context->config.local_gravity_mps2);
    return (isfinite(metrics->accel_norm_mps2) &&
            isfinite(metrics->gyro_norm_radps) &&
            isfinite(metrics->gravity_error_mps2)) ?
        FLIGHT_LANDING_RESULT_OK : FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
}

FlightLandingConditionResult FlightLanding_BarometerSampleEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t healthy,
    uint8_t valid,
    float altitude_m)
{
    if ((context == NULL) || (context->initialized == 0U))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    return ((healthy != 0U) && (valid != 0U) && isfinite(altitude_m) &&
            (FlightLanding_SampleFreshEvaluate(context, now_us,
                                               timestamp_us) ==
             FLIGHT_LANDING_CONDITION_MET)) ?
        FLIGHT_LANDING_CONDITION_MET :
        FLIGHT_LANDING_CONDITION_NOT_MET;
}

void FlightLanding_BarometerRegressionReset(
    FlightLandingBarometerRegression *regression)
{
    if (regression != NULL)
    {
        (void)memset(regression, 0, sizeof(*regression));
    }
}

FlightLandingResult FlightLanding_BarometerRegressionAdd(
    FlightLandingBarometerRegression *regression,
    uint64_t timestamp_us,
    float altitude_m)
{
    double time_s;

    if ((regression == NULL) || (timestamp_us == 0ULL) ||
        !isfinite(altitude_m) ||
        ((regression->count != 0U) &&
         (timestamp_us <= regression->last_timestamp_us)))
    {
        return FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
    }
    SILVERSTAR_ASSERT_OBJECT(regression, FlightLandingBarometerRegression,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (regression->count == 0U)
    {
        regression->first_timestamp_us = timestamp_us;
        regression->minimum_m = altitude_m;
        regression->maximum_m = altitude_m;
    }
    regression->last_timestamp_us = timestamp_us;
    time_s = (double)(timestamp_us - regression->first_timestamp_us) /
             1000000.0;
    regression->sum_t_s += time_s;
    regression->sum_h_m += (double)altitude_m;
    regression->sum_t2_s2 += time_s * time_s;
    regression->sum_th_m_s += time_s * (double)altitude_m;
    if (altitude_m < regression->minimum_m)
    {
        regression->minimum_m = altitude_m;
    }
    if (altitude_m > regression->maximum_m)
    {
        regression->maximum_m = altitude_m;
    }
    regression->count++;
    return FLIGHT_LANDING_RESULT_OK;
}

FlightLandingResult FlightLanding_BarometerRegressionGet(
    const FlightLandingBarometerRegression *regression,
    float *slope_mps,
    float *span_m)
{
    double count;
    double denominator;
    double slope;

    if ((regression == NULL) || (slope_mps == NULL) ||
        (span_m == NULL))
    {
        return FLIGHT_LANDING_RESULT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(regression, FlightLandingBarometerRegression,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(slope_mps, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (regression->count < 2U) { return FLIGHT_LANDING_RESULT_NOT_READY; }
    count = (double)regression->count;
    denominator = (count * regression->sum_t2_s2) -
                  (regression->sum_t_s * regression->sum_t_s);
    if (denominator <= 0.0) { return FLIGHT_LANDING_RESULT_INVALID_SAMPLE; }
    slope = ((count * regression->sum_th_m_s) -
             (regression->sum_t_s * regression->sum_h_m)) /
            denominator;
    if (!isfinite(slope)) { return FLIGHT_LANDING_RESULT_INVALID_SAMPLE; }
    *slope_mps = (float)slope;
    *span_m = regression->maximum_m - regression->minimum_m;
    return isfinite(*span_m) ? FLIGHT_LANDING_RESULT_OK :
                               FLIGHT_LANDING_RESULT_INVALID_SAMPLE;
}

FlightLandingConditionResult FlightLanding_BarometerCandidateEvaluate(
    const FlightLandingContext *context,
    float slope_mps,
    float span_m,
    float maximum_gyro_norm_radps,
    float maximum_gravity_error_mps2)
{
    if ((context == NULL) || (context->initialized == 0U) ||
        !isfinite(slope_mps) || !isfinite(span_m) ||
        !isfinite(maximum_gyro_norm_radps) ||
        !isfinite(maximum_gravity_error_mps2))
    {
        return FLIGHT_LANDING_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightLandingContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    return ((fabsf(slope_mps) <
             context->config.barometer_confirm_rate_mps) &&
            (span_m < context->config.barometer_max_span_m) &&
            (maximum_gyro_norm_radps <
             context->config.still_gyro_threshold_radps) &&
            (maximum_gravity_error_mps2 <
             context->config.still_accel_tolerance_mps2)) ?
        FLIGHT_LANDING_CONDITION_MET :
        FLIGHT_LANDING_CONDITION_NOT_MET;
}

#define FLIGHT_LANDING_VALID_PERCENT 90ULL
#define FLIGHT_LANDING_STILL_PERCENT 95ULL

void FlightLanding_TimeWindowReset(FlightLandingTimeWindow *window, uint64_t start_us)
{
    if (window == NULL) { return; }
    (void)memset(window, 0, sizeof(*window));
    window->start_us = start_us;
    window->last_us = start_us;
}

FlightLandingResult FlightLanding_TimeWindowAdd(FlightLandingTimeWindow *window,
    uint64_t timestamp_us, uint8_t valid, uint8_t still)
{
    uint64_t dt_us;
    uint64_t covered_us;
    if ((window == NULL) || (valid > 1U) || (still > 1U) ||
        (timestamp_us <= window->last_us)) { return FLIGHT_LANDING_RESULT_INVALID_SAMPLE; }
    SILVERSTAR_ASSERT_OBJECT(window, FlightLandingTimeWindow, SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    dt_us = timestamp_us - window->last_us;
    covered_us = (dt_us <= FLIGHT_LANDING_COVERAGE_GAP_US) ? dt_us : 0U;
    if ((valid != 0U) && (window->previous_valid != 0U))
    { window->valid_us += covered_us; }
    else { covered_us = 0U; }
    if ((still != 0U) && (window->previous_still != 0U) && (covered_us != 0U))
    { window->still_us += covered_us; window->bad_us = 0U; }
    else { window->bad_us += dt_us; }
    if (window->bad_us > window->maximum_bad_us)
    { window->maximum_bad_us = window->bad_us; }
    if ((valid != 0U) && (still != 0U)) { window->last_good_us = timestamp_us; }
    window->last_us = timestamp_us;
    window->previous_valid = valid;
    window->previous_still = (uint8_t)((valid != 0U) && (still != 0U));
    return FLIGHT_LANDING_RESULT_OK;
}

FlightLandingConditionResult FlightLanding_TimeWindowEvaluate(
    const FlightLandingTimeWindow *window, uint64_t duration_us)
{
    uint64_t elapsed_us;
    if ((window == NULL) || (window->last_us < window->start_us))
    { return FLIGHT_LANDING_CONDITION_INVALID; }
    elapsed_us = window->last_us - window->start_us;
    return ((elapsed_us >= duration_us) &&
        (window->valid_us * 100ULL >= elapsed_us * FLIGHT_LANDING_VALID_PERCENT) &&
        (window->still_us * 100ULL >= window->valid_us * FLIGHT_LANDING_STILL_PERCENT) &&
        (window->maximum_bad_us <= FLIGHT_LANDING_MAXIMUM_BAD_US) &&
        (window->previous_still != 0U) &&
        (window->last_us - window->last_good_us <= FLIGHT_LANDING_COVERAGE_GAP_US)) ?
        FLIGHT_LANDING_CONDITION_MET : FLIGHT_LANDING_CONDITION_NOT_MET;
}
