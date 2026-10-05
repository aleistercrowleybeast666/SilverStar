#ifndef __FLIGHT_LANDING_H
#define __FLIGHT_LANDING_H

#include <stdint.h>

#define FLIGHT_LANDING_COVERAGE_GAP_US 20000ULL
#define FLIGHT_LANDING_MAXIMUM_BAD_US 200000ULL

typedef enum
{
    FLIGHT_LANDING_INIT_OK = 0,
    FLIGHT_LANDING_INIT_INVALID_ARGUMENT,
    FLIGHT_LANDING_INIT_INVALID_CONFIG
} FlightLandingInitResult;

typedef enum
{
    FLIGHT_LANDING_RESULT_OK = 0,
    FLIGHT_LANDING_RESULT_INVALID_ARGUMENT,
    FLIGHT_LANDING_RESULT_INVALID_SAMPLE,
    FLIGHT_LANDING_RESULT_NOT_READY
} FlightLandingResult;

typedef enum
{
    FLIGHT_LANDING_CONDITION_INVALID = 0,
    FLIGHT_LANDING_CONDITION_NOT_MET,
    FLIGHT_LANDING_CONDITION_MET
} FlightLandingConditionResult;

typedef struct
{
    uint32_t sample_max_age_ms;
    float local_gravity_mps2;
    float impact_threshold_mps2;
    float still_gyro_threshold_radps;
    float still_accel_tolerance_mps2;
    float barometer_confirm_rate_mps;
    float barometer_max_span_m;
} FlightLandingConfig;

typedef struct
{
    FlightLandingConfig config;
    uint8_t initialized;
} FlightLandingContext;

typedef struct
{
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t count;
    double sum_t_s;
    double sum_h_m;
    double sum_t2_s2;
    double sum_th_m_s;
    float minimum_m;
    float maximum_m;
} FlightLandingBarometerRegression;

typedef struct
{
    float accel_norm_mps2;
    float gyro_norm_radps;
    float gravity_error_mps2;
} FlightLandingImuMetrics;

/* One fixed-duration candidate bucket: no sample-count weighting or allocation. */
typedef struct
{
    uint64_t start_us;
    uint64_t last_us;
    uint64_t valid_us;
    uint64_t still_us;
    uint64_t bad_us;
    uint64_t maximum_bad_us;
    uint64_t last_good_us;
    uint8_t previous_valid;
    uint8_t previous_still;
} FlightLandingTimeWindow;

void FlightLanding_TimeWindowReset(FlightLandingTimeWindow *window, uint64_t start_us);
FlightLandingResult FlightLanding_TimeWindowAdd(FlightLandingTimeWindow *window,
    uint64_t timestamp_us, uint8_t valid, uint8_t still);
FlightLandingConditionResult FlightLanding_TimeWindowEvaluate(
    const FlightLandingTimeWindow *window, uint64_t duration_us);

FlightLandingInitResult FlightLanding_ContextInit(
    FlightLandingContext *context,
    const FlightLandingConfig *config);
FlightLandingConditionResult FlightLanding_SampleFreshEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us);
FlightLandingResult FlightLanding_ImpactMetricGet(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t acceleration_valid,
    const float acceleration_b_mps2[3],
    float *metric_mps2);
FlightLandingConditionResult FlightLanding_PostImpactStillnessEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t acceleration_valid,
    uint8_t gyro_valid,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    float *accel_norm_mps2);
FlightLandingConditionResult FlightLanding_StillnessEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t inertial_timestamp_us,
    uint64_t ins_timestamp_us,
    uint8_t gyro_valid,
    uint8_t linear_acceleration_valid,
    const float gyro_b_radps[3],
    const float linear_acceleration_n_mps2[3]);
FlightLandingResult FlightLanding_ImuMetricsGet(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint64_t candidate_start_us,
    uint8_t acceleration_valid,
    uint8_t gyro_valid,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    FlightLandingImuMetrics *metrics);
FlightLandingConditionResult FlightLanding_BarometerSampleEvaluate(
    const FlightLandingContext *context,
    uint64_t now_us,
    uint64_t timestamp_us,
    uint8_t healthy,
    uint8_t valid,
    float altitude_m);
void FlightLanding_BarometerRegressionReset(
    FlightLandingBarometerRegression *regression);
FlightLandingResult FlightLanding_BarometerRegressionAdd(
    FlightLandingBarometerRegression *regression,
    uint64_t timestamp_us,
    float altitude_m);
FlightLandingResult FlightLanding_BarometerRegressionGet(
    const FlightLandingBarometerRegression *regression,
    float *slope_mps,
    float *span_m);
FlightLandingConditionResult FlightLanding_BarometerCandidateEvaluate(
    const FlightLandingContext *context,
    float slope_mps,
    float span_m,
    float maximum_gyro_norm_radps,
    float maximum_gravity_error_mps2);

#endif /* __FLIGHT_LANDING_H */
