#ifndef __SYSTEM_USER_CONFIG_H
#define __SYSTEM_USER_CONFIG_H

/*
 * Optional estimator noise overrides must be defined here, before the target
 * composition header is reached through system_user_flight_config.h. Leave
 * them undefined to consume qualified recommendations from selected devices.
 *
 * #define SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_OVERRIDE    1.5f
 * #define SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_OVERRIDE    1.5f
 * #define SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_OVERRIDE    2.0f
 * #define SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE 1.5f
 * #define SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE   2.5f
 * #define SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE 0.15f
 * #define SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE    5.0f
 */

#include "system_configuration_types.h"
#include "system_user_flight_config.h"

/* -------------------------------------------------------------------------- */
/* Release and profile                                                        */
/* -------------------------------------------------------------------------- */
#define SILVERSTAR_VERSION_MAJOR     0
#define SILVERSTAR_VERSION_MINOR     1
#define SILVERSTAR_VERSION_PATCH     0
#define SILVERSTAR_VERSION_BUILD     0
#define SILVERSTAR_LOG_BUILD_TAG     "SILV0100"
#define SYSTEM_PROFILE_ID            0x0000000CUL
#define SYSTEM_PROFILE_OUTPUT_CHANNEL_COUNT 2U

/* -------------------------------------------------------------------------- */
/* Local indicators                                                           */
/* -------------------------------------------------------------------------- */
/* The generated project owns the actual selected indicator. Missing binding
 * is an invalid build; never silently enable an absent physical device. */
#ifndef SYSTEM_INDICATOR_SYSTEM_ENABLE
#error "System indicator selection must be bound by project_flight_config.h"
#endif
#ifndef SYSTEM_INDICATOR_GNSS_ENABLE
#define SYSTEM_INDICATOR_GNSS_ENABLE                      0U
#endif
#define SYSTEM_INDICATOR_SAFETY_ENABLE                    0U
#define SYSTEM_INDICATOR_FAST_HALF_PERIOD_US          100000ULL
#define SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US          500000ULL
#define SYSTEM_INDICATOR_EVENT_CONFIRM_US              500000ULL

/* -------------------------------------------------------------------------- */
/* Navigation and estimation                                                  */
/* -------------------------------------------------------------------------- */
#define SYSTEM_LOCAL_GRAVITY_MPS2       9.78f
#ifndef SYSTEM_KF_GRAVITY_MPS2
#define SYSTEM_KF_GRAVITY_MPS2 9.78f
#endif
#ifndef SYSTEM_INS_GRAVITY_MPS2
#define SYSTEM_INS_GRAVITY_MPS2 9.78f
#endif
#define SYSTEM_ATTITUDE_POLICY           SYSTEM_ATTITUDE_SOFTWARE_ALWAYS
#ifndef SYSTEM_BUILD_MECHANIZATION_ALGORITHM
#define SYSTEM_BUILD_MECHANIZATION_ALGORITHM \
    SYSTEM_MECHANIZATION_CONING2_SCULLING2
#endif
#ifndef SYSTEM_BUILD_FUSION_ALGORITHM
#define SYSTEM_BUILD_FUSION_ALGORITHM SYSTEM_FUSION_KF6
#endif
#ifndef SYSTEM_BUILD_ESTIMATOR_ENABLED
#define SYSTEM_BUILD_ESTIMATOR_ENABLED 1U
#endif
#ifndef SYSTEM_BUILD_ESKF15_ENABLED
#define SYSTEM_BUILD_ESKF15_ENABLED 0U
#endif
#define SYSTEM_MECHANIZATION_ALGORITHM \
    SYSTEM_BUILD_MECHANIZATION_ALGORITHM
#define SYSTEM_FUSION_ALGORITHM SYSTEM_BUILD_FUSION_ALGORITHM

#include "system_user_alignment_config.h"

#ifndef SYSTEM_IMU_OUTPUT_RATE_HZ
#define SYSTEM_IMU_OUTPUT_RATE_HZ                      200U
#endif
#define SYSTEM_HARDWARE_QUATERNION_OUTPUT_RATE_HZ      200U
#ifndef SYSTEM_GNSS_NAVIGATION_RATE_HZ
#define SYSTEM_GNSS_NAVIGATION_RATE_HZ                 25U
#endif
#define SYSTEM_GNSS_CONSTELLATION_MASK                 \
    (SYSTEM_GNSS_CONSTELLATION_GPS |                   \
     SYSTEM_GNSS_CONSTELLATION_BDS |                   \
     SYSTEM_GNSS_CONSTELLATION_GALILEO)
#ifndef SYSTEM_GNSS_DYNAMIC_MODEL
#define SYSTEM_GNSS_DYNAMIC_MODEL                      \
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G
#endif
#define SYSTEM_GNSS_OUTPUT_PROTOCOL                    \
    SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX
#define SYSTEM_GNSS_ENABLED_MESSAGE_MASK               \
    SYSTEM_GNSS_MESSAGE_NAV_PVT

/*
 * "Usable" only decides whether a sample may enter the preflight origin
 * window.  The KF still uses the receiver-reported hAcc/vAcc/sAcc as R, so
 * accepting a less-than-ideal cold-start fix does not make it over-confident.
 */
#define SYSTEM_GNSS_MIN_SATELLITES                      6U
#define SYSTEM_GNSS_MAX_HORIZONTAL_ACCURACY_M           5.0f
#define SYSTEM_GNSS_MAX_VERTICAL_ACCURACY_M            10.0f
#define SYSTEM_GNSS_MAX_SPEED_ACCURACY_MPS              2.0f
#define SYSTEM_GNSS_MAX_SAMPLE_AGE_MS                  500U
#define SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ             200U
#define SYSTEM_BAROMETER_OUTPUT_RATE_HZ                200U

#ifndef SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT
#define SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT           2U
#endif
#define SYSTEM_MECHANIZATION_SAMPLE_RATE_MIN_HZ        50U
#define SYSTEM_MECHANIZATION_SAMPLE_RATE_MAX_HZ        500U
#define SYSTEM_MECHANIZATION_DT_TOLERANCE_RATIO        0.35f
#define SYSTEM_KF_PREDICTION_DT_MAX_S                  0.10f
#define SYSTEM_ESTIMATOR_MEASUREMENT_MAX_AGE_US         500000ULL
#define SYSTEM_IMU_BIAS_SETTLE_TIME_US                  1000000ULL
#define SYSTEM_IMU_BIAS_MIN_VALID_SAMPLES               190U
#define SYSTEM_IMU_BIAS_MIN_DURATION_US                 900000ULL
#define SYSTEM_IMU_BIAS_MAX_GYRO_RADPS                   0.05f
#define SYSTEM_IMU_BIAS_ACCEL_TOLERANCE_MPS2             0.50f
#define SYSTEM_IMU_BIAS_MAX_SAMPLE_GAP_US               50000ULL
#define SYSTEM_IMU_BIAS_ACCEL_VARIANCE_MAX_M2PS4         0.040f
#define SYSTEM_IMU_BIAS_GYRO_VARIANCE_MAX_RAD2PS2        0.0001f
#define SYSTEM_IMU_BIAS_REPORT_PERIOD_US               1000000ULL
#define SYSTEM_IMU_CAL_ACCEL_SCALE_MIN                       0.5f
#define SYSTEM_IMU_CAL_ACCEL_SCALE_MAX                       1.5f
#define SYSTEM_INS_AUXILIARY_SAMPLE_MAX_AGE_US           50000ULL

#ifndef SYSTEM_ESTIMATOR_P0_POSITION_E_VARIANCE_M2
#define SYSTEM_ESTIMATOR_P0_POSITION_E_VARIANCE_M2      4.0f
#endif
#ifndef SYSTEM_ESTIMATOR_P0_POSITION_N_VARIANCE_M2
#define SYSTEM_ESTIMATOR_P0_POSITION_N_VARIANCE_M2      4.0f
#endif
#ifndef SYSTEM_ESTIMATOR_P0_POSITION_U_VARIANCE_M2
#define SYSTEM_ESTIMATOR_P0_POSITION_U_VARIANCE_M2      9.0f
#endif
#ifndef SYSTEM_ESTIMATOR_P0_VELOCITY_E_VARIANCE_M2PS2
#define SYSTEM_ESTIMATOR_P0_VELOCITY_E_VARIANCE_M2PS2   0.25f
#endif
#ifndef SYSTEM_ESTIMATOR_P0_VELOCITY_N_VARIANCE_M2PS2
#define SYSTEM_ESTIMATOR_P0_VELOCITY_N_VARIANCE_M2PS2   0.25f
#endif
#ifndef SYSTEM_ESTIMATOR_P0_VELOCITY_U_VARIANCE_M2PS2
#define SYSTEM_ESTIMATOR_P0_VELOCITY_U_VARIANCE_M2PS2   0.25f
#endif
#define SYSTEM_ESTIMATOR_GNSS_ACCURACY_SCALE            1.25f

#ifndef SYSTEM_ESTIMATOR_NIS_3D_SOFT_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_3D_SOFT_THRESHOLD          11.345f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_3D_HARD_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_3D_HARD_THRESHOLD          16.266f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_2D_SOFT_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_2D_SOFT_THRESHOLD          9.210f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_2D_HARD_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_2D_HARD_THRESHOLD          13.816f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_1D_SOFT_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_1D_SOFT_THRESHOLD          6.635f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_1D_HARD_THRESHOLD
#define SYSTEM_ESTIMATOR_NIS_1D_HARD_THRESHOLD          10.828f
#endif
#ifndef SYSTEM_ESTIMATOR_NIS_MAX_R_SCALE
#define SYSTEM_ESTIMATOR_NIS_MAX_R_SCALE                10.0f
#endif
#define SYSTEM_ESTIMATOR_P_DIAGONAL_MIN                 1.0e-8f
#define SYSTEM_ESTIMATOR_MATRIX_EPSILON                 1.0e-9f
#define SYSTEM_ESTIMATOR_GNSS_ORIGIN_WINDOW_SAMPLES     100U
#define SYSTEM_ESTIMATOR_BARO_ORIGIN_WINDOW_SAMPLES     100U
#define SYSTEM_ESTIMATOR_ORIGIN_MIN_INLIERS              80U
#define SYSTEM_ESTIMATOR_GNSS_ORIGIN_MAX_AGE_US          1000000ULL
#define SYSTEM_ESTIMATOR_BARO_ORIGIN_MAX_AGE_US          500000ULL
#define SYSTEM_ESTIMATOR_GNSS_FUSION_REQUIRES_PREFLIGHT_ORIGIN 1U
#define SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_OUTLIER_FLOOR_M 3.0f
#define SYSTEM_ESTIMATOR_GNSS_VERTICAL_OUTLIER_FLOOR_M   5.0f
#define SYSTEM_ESTIMATOR_BARO_OUTLIER_FLOOR_M            2.0f
#define SYSTEM_ESTIMATOR_ORIGIN_FREEZE_WAIT_MS           20U

/* GNSS/KF reacquisition.  Each EN/U position and velocity group is managed
 * independently; all limits are applied only after the normal quality gate. */
#ifndef SYSTEM_ESTIMATOR_GNSS_REACQUIRE_OUTAGE_MS
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_OUTAGE_MS 300U
#endif
#ifndef SYSTEM_ESTIMATOR_GNSS_VELOCITY_VERTICAL_SCALE
#define SYSTEM_ESTIMATOR_GNSS_VELOCITY_VERTICAL_SCALE 1.0f
#endif
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ENABLE                         1U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_REJECT_COUNT                   5U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT               3U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ACCEPT_COUNT                   3U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_FACTOR               2.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES     5U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS                   8U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MIN_DT_MS                     10U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_DT_MS                   1000U
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_HORIZONTAL_FLOOR_M    3.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VERTICAL_FLOOR_M      5.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE              2.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_HORIZONTAL_ACCEL_MPS2     60.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_VERTICAL_ACCEL_MPS2       60.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2  1000000.0f
#define SYSTEM_ESTIMATOR_GNSS_REACQUIRE_VELOCITY_VARIANCE_CAP_M2PS2 10000.0f

#if ((SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ENABLE != 0U) && \
     (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ENABLE != 1U)) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_OUTAGE_MS < 100U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_REJECT_COUNT == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ACCEPT_COUNT == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MIN_DT_MS == 0U) || \
    (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_DT_MS < \
     SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MIN_DT_MS)
#error "Invalid GNSS reacquisition configuration"
#endif

/* -------------------------------------------------------------------------- */
/* Logging runtime/storage policy. Stream policy is authoritative in SSLOG.   */
/* -------------------------------------------------------------------------- */
/* Normal sessions keep bootstrap/snapshots/events, but no high-rate preflight
 * samples. Explicit compiler -D overrides enable diagnostic preflight capture. */
#ifndef SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE
#define SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE      0U
#endif
#ifndef SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE
#define SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE 0U
#endif

#define SYSTEM_POWER_SAMPLE_PERIOD_US                20000ULL
#define SYSTEM_TELEMETRY_STATUS_REPEAT_PERIOD_US      50000ULL
#define SYSTEM_TELEMETRY_COMMAND_POLICY                    1U
#define SYSTEM_TELEMETRY_PREFLIGHT_STATE_ENABLE          1U
#define SYSTEM_TELEMETRY_PREFLIGHT_STATE_PERIOD_US     200000ULL
#define SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US         1000000ULL
#define SYSTEM_TELEMETRY_PREFLIGHT_STATUS_PERIOD_US    1000000ULL
#define SYSTEM_TELEMETRY_STREAM_PERIOD_US            200000ULL
#define SYSTEM_LOG_SYNC_PERIOD_US                   250000ULL
#define SYSTEM_LOG_RETRY_PERIOD_US                 1000000ULL
#define SYSTEM_LOG_POST_LANDING_GRACE_MS              1000U
#define SYSTEM_LOG_AGGREGATION_BUFFER_SIZE            4096U
#define SYSTEM_LOG_RECORD_QUEUE_DEPTH                   80U
#define SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH                48U
#define SYSTEM_LOG_FILE_INDEX_MAX                     9999U
#define SYSTEM_LOG_PROFILE_ID                             0U

/* System/module queue sizing kept here because it changes static RAM use. */
#define SYSTEM_IMU_SAMPLE_BUS_DEPTH                       64U
#define SYSTEM_IMU_DRAIN_MAX_SAMPLES_PER_CYCLE            32U
#define SYSTEM_LIFECYCLE_QUEUE_DEPTH                       4U
#define SYSTEM_TELEMETRY_STATUS_QUEUE_DEPTH                8U
#define SYSTEM_TELEMETRY_ACK_QUEUE_DEPTH                   8U
#define SYSTEM_TELEMETRY_ACK_CACHE_DEPTH                   4U
#define SYSTEM_TELEMETRY_STATUS_REPEAT_COUNT               3U

/* -------------------------------------------------------------------------- */
/* Local maintenance diagnostics                                              */
/* -------------------------------------------------------------------------- */
#define SYSTEM_DEBUG_LOG_ENABLE                            1U
#define SYSTEM_DEBUG_LOG_LINE_SIZE                       320U
#define SYSTEM_DEBUG_LOG_AUTO_CRLF                         1U
#define SYSTEM_DEBUG_LOG_PREFIX              "LOG INFO SYSTEM "

#if ((SYSTEM_INDICATOR_SYSTEM_ENABLE != 0U) && \
     (SYSTEM_INDICATOR_SYSTEM_ENABLE != 1U)) || \
    ((SYSTEM_INDICATOR_GNSS_ENABLE != 0U) && \
     (SYSTEM_INDICATOR_GNSS_ENABLE != 1U)) || \
    ((SYSTEM_INDICATOR_SAFETY_ENABLE != 0U) && \
     (SYSTEM_INDICATOR_SAFETY_ENABLE != 1U))
#error "System indicator enable macros must be 0 or 1"
#endif
#if (SYSTEM_INDICATOR_FAST_HALF_PERIOD_US == 0ULL) || \
    (SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US == 0ULL) || \
    (SYSTEM_INDICATOR_EVENT_CONFIRM_US == 0ULL)
#error "System indicator timing values must be non-zero"
#endif

#if (SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT != 1U) && \
    (SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT != 2U)
#error "Mechanization aggregation must be one or two real IMU intervals"
#endif
#if (SYSTEM_IMU_OUTPUT_RATE_HZ < SYSTEM_MECHANIZATION_SAMPLE_RATE_MIN_HZ) || \
    (SYSTEM_IMU_OUTPUT_RATE_HZ > SYSTEM_MECHANIZATION_SAMPLE_RATE_MAX_HZ)
#error "Configured IMU output rate is outside the mechanization validity range"
#endif
#if (SYSTEM_LOG_RECORD_QUEUE_DEPTH == 0U) || \
    (SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH == 0U) || \
    (SYSTEM_IMU_SAMPLE_BUS_DEPTH < 4U) || \
    (SYSTEM_IMU_DRAIN_MAX_SAMPLES_PER_CYCLE == 0U) || \
    (SYSTEM_LIFECYCLE_QUEUE_DEPTH < 2U) || \
    (SYSTEM_TELEMETRY_STATUS_QUEUE_DEPTH < 2U) || \
    (SYSTEM_TELEMETRY_ACK_QUEUE_DEPTH < 2U) || \
    (SYSTEM_TELEMETRY_ACK_CACHE_DEPTH == 0U)
#error "Configured queue depths are invalid"
#endif
#if (SYSTEM_LOG_AGGREGATION_BUFFER_SIZE < 512U)
#error "SYSTEM_LOG_AGGREGATION_BUFFER_SIZE is too small"
#endif

/* Single entry point for device and algorithm build qualification. */
#include "system_user_capability_validation.h"

#endif /* __SYSTEM_USER_CONFIG_H */
