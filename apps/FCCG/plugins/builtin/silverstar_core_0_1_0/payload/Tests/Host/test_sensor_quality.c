#include <stdint.h>
#include <string.h>

#include "system_barometer.h"
#include "system_estimator_diagnostics.h"
#include "system_gnss_quality.h"
#include "system_user_config.h"
#include "test_common.h"

static SystemGnssSample Test_GnssSampleMake(uint64_t now_us)
{
    SystemGnssSample sample;

    (void)memset(&sample, 0, sizeof(sample));
    sample.sample_timestamp_us = now_us;
    sample.receive_timestamp_us = now_us;
    sample.sequence = 1U;
    sample.supported_fields = SYSTEM_GNSS_FIELD_FIX_TYPE |
        SYSTEM_GNSS_FIELD_FIX_OK |
        SYSTEM_GNSS_FIELD_SATELLITE_COUNT |
        SYSTEM_GNSS_FIELD_POSITION |
        SYSTEM_GNSS_FIELD_HEIGHT |
        SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL |
        SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL |
        SYSTEM_GNSS_FIELD_SPEED_ACCURACY;
    sample.valid_fields = sample.supported_fields;
    sample.fix_type = 3U;
    sample.fix_ok = 1U;
    sample.satellite_count = SYSTEM_GNSS_MIN_SATELLITES;
    sample.horizontal_accuracy_m =
        SYSTEM_GNSS_MAX_HORIZONTAL_ACCURACY_M;
    sample.vertical_accuracy_m = SYSTEM_GNSS_MAX_VERTICAL_ACCURACY_M;
    sample.speed_accuracy_mps = SYSTEM_GNSS_MAX_SPEED_ACCURACY_MPS;
    sample.online = 1U;
    return sample;
}

static void Test_GnssThresholdDiagnostics(void)
{
    const uint64_t now_us = 5000000ULL;
    SystemGnssSample sample;

    sample = Test_GnssSampleMake(now_us);
    TEST_CHECK(SystemGnssQuality_Evaluate(&sample, now_us) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(sample.position_usable != 0U);
    TEST_CHECK(sample.velocity_valid_mask ==
               (SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N |
                SYSTEM_GNSS_VEL_VALID_U));
    TEST_CHECK(sample.position_reject_mask == 0U);
    TEST_CHECK(sample.velocity_reject_mask == 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.fix_ok = 0U;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.position_usable == 0U);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_FIX_FLAG) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.satellite_count = SYSTEM_GNSS_MIN_SATELLITES - 1U;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_SATELLITES) != 0U);
    TEST_CHECK((sample.velocity_reject_mask &
                SYSTEM_GNSS_REJECT_SATELLITES) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.horizontal_accuracy_m =
        SYSTEM_GNSS_MAX_HORIZONTAL_ACCURACY_M + 0.1f;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_HACC) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.vertical_accuracy_m =
        SYSTEM_GNSS_MAX_VERTICAL_ACCURACY_M + 0.1f;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_VACC) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.speed_accuracy_mps =
        SYSTEM_GNSS_MAX_SPEED_ACCURACY_MPS + 0.1f;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK((sample.velocity_reject_mask &
                SYSTEM_GNSS_REJECT_SACC) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.receive_timestamp_us = now_us -
        ((uint64_t)SYSTEM_GNSS_MAX_SAMPLE_AGE_MS * 1000ULL) - 1ULL;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_STALE) != 0U);
    TEST_CHECK((sample.velocity_reject_mask &
                SYSTEM_GNSS_REJECT_STALE) != 0U);
}

static void Test_GnssFieldCapabilities(void)
{
    const uint64_t now_us = 6000000ULL;
    SystemGnssSample sample;

    sample = Test_GnssSampleMake(now_us);
    sample.supported_fields &= ~(SYSTEM_GNSS_FIELD_SATELLITE_COUNT |
        SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY |
        SYSTEM_GNSS_FIELD_SPEED_ACCURACY |
        SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL);
    sample.valid_fields = sample.supported_fields;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.position_usable != 0U);
    TEST_CHECK(sample.velocity_valid_mask ==
               (SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N));
    TEST_CHECK(sample.quality_degraded != 0U);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED) != 0U);
    TEST_CHECK((sample.velocity_reject_mask &
                SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.supported_fields &= ~SYSTEM_GNSS_FIELD_FIX_OK;
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_FIX_OK;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.physical_valid_group_mask == 0U);
    TEST_CHECK(sample.valid_group_mask == 0U);
    TEST_CHECK(sample.position_usable == 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.position_usable == 0U);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_FIELD_INVALID) != 0U);
    TEST_CHECK((sample.position_reject_mask &
                SYSTEM_GNSS_REJECT_HACC) != 0U);

    sample = Test_GnssSampleMake(now_us);
    sample.supported_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL;
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.velocity_valid_mask ==
               (SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N));

    sample = Test_GnssSampleMake(now_us);
    sample.supported_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL;
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.velocity_valid_mask == SYSTEM_GNSS_VEL_VALID_U);
}

static void Test_BarometerFields(void)
{
    SystemBarometerSample sample;
    float altitude_m = -1.0f;

    (void)memset(&sample, 0, sizeof(sample));
    sample.supported_fields = SYSTEM_BARO_FIELD_PRESSURE |
                              SYSTEM_BARO_FIELD_ALTITUDE;
    sample.valid_fields = sample.supported_fields;
    sample.pressure_pa = 90000.0f;
    sample.altitude_m = 123.0f;
    TEST_CHECK(SystemBarometer_AltitudeResolve(&sample, &altitude_m) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(altitude_m, 123.0f, 1.0e-6f);

    sample.supported_fields = SYSTEM_BARO_FIELD_PRESSURE;
    sample.valid_fields = SYSTEM_BARO_FIELD_PRESSURE;
    sample.pressure_pa = 101325.0f;
    sample.altitude_m = 999.0f;
    TEST_CHECK(SystemBarometer_AltitudeResolve(&sample, &altitude_m) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(altitude_m, 0.0f, 1.0e-4f);

    sample.supported_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    sample.valid_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    sample.altitude_m = 456.0f;
    TEST_CHECK(SystemBarometer_AltitudeResolve(&sample, &altitude_m) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(altitude_m, 456.0f, 1.0e-6f);

    sample.supported_fields = 0U;
    sample.valid_fields = 0U;
    TEST_CHECK(SystemBarometer_AltitudeResolve(&sample, &altitude_m) ==
               SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemBarometer_AltitudeResolve(NULL, &altitude_m) ==
               SYSTEM_DEVICE_INVALID_ARGUMENT);
}

static void Test_BarometerUpdateCounters(void)
{
    SystemEstimatorBaroDiagnostics diagnostics;

    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED,
        SYSTEM_ESTIMATOR_BARO_SKIP_NONE, 100U, 1U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_SOFTENED,
        SYSTEM_ESTIMATOR_BARO_SKIP_NONE, 200U, 1U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_REJECTED,
        SYSTEM_ESTIMATOR_BARO_SKIP_NONE, 300U, 1U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_STALE,
        SYSTEM_ESTIMATOR_BARO_SKIP_STALE, 400U, 1U);
    TEST_CHECK(diagnostics.accepted_count == 1U);
    TEST_CHECK(diagnostics.softened_count == 1U);
    TEST_CHECK(diagnostics.rejected_count == 1U);
    TEST_CHECK(diagnostics.skipped_count == 1U);
    TEST_CHECK(diagnostics.last_update_state ==
               SYSTEM_ESTIMATOR_BARO_UPDATE_STALE);
    TEST_CHECK(diagnostics.last_skip_reason ==
               SYSTEM_ESTIMATOR_BARO_SKIP_STALE);
    TEST_CHECK(diagnostics.last_update_timestamp_us == 400U);

    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_NO_SAMPLE,
        SYSTEM_ESTIMATOR_BARO_SKIP_NO_SAMPLE, 500U, 0U);
    TEST_CHECK(diagnostics.skipped_count == 1U);
    TEST_CHECK(diagnostics.last_update_state ==
               SYSTEM_ESTIMATOR_BARO_UPDATE_NO_SAMPLE);

    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP,
        SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP, 600U, 0U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(
        &diagnostics, SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP,
        SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP, 700U, 0U);
    TEST_CHECK(diagnostics.skipped_count == 1U);
    TEST_CHECK(diagnostics.last_update_state ==
               SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP);
}

static void Test_GnssIndependentGroups(void)
{
    const uint64_t now_us = 6000000ULL;
    SystemGnssSample sample = Test_GnssSampleMake(now_us);
    sample.horizontal_accuracy_m = 4.06f;
    sample.vertical_accuracy_m = 10.01f;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.valid_group_mask == 15U);
    TEST_CHECK(sample.physical_valid_group_mask == 15U);
    TEST_CHECK((sample.quality_degraded_group_mask & 2U) != 0U);
    TEST_CHECK(sample.group_reject_mask[0] == 0U);
    TEST_CHECK(sample.group_reject_mask[1] == SYSTEM_GNSS_REJECT_VACC);
    TEST_CHECK(sample.position_usable == 0U);
    sample = Test_GnssSampleMake(now_us);
    sample.horizontal_accuracy_m = SYSTEM_GNSS_MAX_HORIZONTAL_ACCURACY_M + 1.0f;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.valid_group_mask == 15U);
    TEST_CHECK(sample.physical_valid_group_mask == 15U);
    TEST_CHECK((sample.quality_degraded_group_mask & 1U) != 0U);
    TEST_CHECK(sample.position_usable == 0U);
    TEST_CHECK(sample.group_reject_mask[1] == 0U);
    sample = Test_GnssSampleMake(now_us);
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.valid_group_mask == 11U);
    TEST_CHECK(sample.group_reject_mask[3] == 0U);
    sample = Test_GnssSampleMake(now_us);
    sample.valid_fields &= ~SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL;
    (void)SystemGnssQuality_Evaluate(&sample, now_us);
    TEST_CHECK(sample.valid_group_mask == 7U);
}

static void Test_BarometerEventAdmission(void)
{
    SystemEstimatorBaroDiagnostics diagnostics;
    uint32_t index;
    uint32_t events = 0U;
    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    /* 60 seconds at 200 Hz with a normal catch-up between every update. */
    for (index = 1U; index <= 12000U; index++)
    {
        SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
            SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP,
            SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP, index * 5000ULL, 0U);
        events += SystemEstimatorBaroDiagnostics_EventPending(&diagnostics);
        TEST_CHECK(diagnostics.last_update_state == SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP);
        SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
            SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED, SYSTEM_ESTIMATOR_BARO_SKIP_NONE,
            index * 5000ULL + 1U, 1U);
        events += SystemEstimatorBaroDiagnostics_EventPending(&diagnostics);
    }
    TEST_CHECK(events == 0U);
    TEST_CHECK(diagnostics.accepted_count == 12000U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
        SYSTEM_ESTIMATOR_BARO_UPDATE_STALE, SYSTEM_ESTIMATOR_BARO_SKIP_STALE, 61000000U, 1U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 1U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 0U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
        SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP,
        SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP, 61005000U, 0U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 0U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
        SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED, SYSTEM_ESTIMATOR_BARO_SKIP_NONE, 61010000U, 1U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 1U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 0U);
    SystemEstimatorBaroDiagnostics_UpdateRecord(&diagnostics,
        SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP,
        SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP, 62000000U, 0U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 0U);
    diagnostics.last_update_timestamp_us = 63000000U;
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 1U);
    TEST_CHECK(SystemEstimatorBaroDiagnostics_EventPending(&diagnostics) == 0U);
}

int main(void)
{
    Test_GnssIndependentGroups();
    Test_BarometerEventAdmission();
    Test_GnssThresholdDiagnostics();
    Test_GnssFieldCapabilities();
    Test_BarometerFields();
    Test_BarometerUpdateCounters();
    return Test_Finish("sensor_quality");
}
