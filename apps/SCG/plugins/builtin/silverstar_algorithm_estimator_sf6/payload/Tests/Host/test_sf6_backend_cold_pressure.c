/* Real backend/pressure admission. The existing native-height fixture and
 * its strict numerical expectations remain unchanged in their own scope. */
#define main Test_NativeAltitudeEntry
#include "test_sf6_backend.c"
#undef main

#if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 1U)
#error Cold-pressure regression requires the production pressure policy
#endif

static void Test_ColdSample(EstimatorPressureSnapshot *pressure,
    SystemInertialIncrement *input, EstimatorOutputSnapshot *output)
{
    input->timestamp_us += 5000ULL;
    pressure->timestamp_us = input->timestamp_us;
    pressure->receive_timestamp_us = input->timestamp_us;
    pressure->sequence++;
    HostPlatformMock_TimeSetUs(input->timestamp_us);
    TEST_CHECK(EstimatorBus_PressurePublish(pressure) == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(SystemNavigationBackend_Predict(input, output) == SYSTEM_DEVICE_OK);
    Test_RecordsDrain();
}

int main(void)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    EstimatorOutputSnapshot output = {0};
    EstimatorPressureSnapshot pressure = {0};
    SystemInertialIncrement input = {0};
    HostPlatformMock_Reset();
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    Test_GnssPrepare(); s_gnss.position_usable = 0U; s_gnss_available = 0U;
    TEST_CHECK(SystemNavigationBackend_Initialize(q, &s_gnss, 0.0f, 1U, 81U, 1U) == SYSTEM_DEVICE_OK);
    input.dt_s = 0.005f; input.timestamp_us = 1000000ULL;
    input.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * input.dt_s;
    pressure.pressure_pa = 101325.0f; pressure.altitude_m = 10.5f;
    pressure.supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
    pressure.valid_fields = pressure.supported_fields;
    pressure.valid = 1U; pressure.healthy = 1U; pressure.measurement_timestamp_trusted = 1U;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 1U && output.baro_reject_count == 0U);
    TEST_CHECK_NEAR(output.baro_relative_altitude_m, 0.0f, 1.0e-6f);
    TEST_CHECK_NEAR(output.position_enu_m[2], 0.0f, 1.0e-6f);
    TEST_CHECK(output.gnss_position_update_count == 0U);
    /* Native altitude must not rescue missing, corrupt or out-of-range pressure. */
    pressure.supported_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    pressure.valid_fields = pressure.supported_fields;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 1U && output.baro_reject_count == 1U);
    pressure.supported_fields |= SYSTEM_BARO_FIELD_PRESSURE;
    pressure.valid_fields = pressure.supported_fields; pressure.pressure_pa = NAN;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 1U && output.baro_reject_count == 2U);
    pressure.pressure_pa = 999.0f;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 1U && output.baro_reject_count == 3U);
    pressure.pressure_pa = 101325.0f; pressure.valid_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 1U && output.baro_reject_count == 4U);
    pressure.valid_fields = pressure.supported_fields;
    Test_ColdSample(&pressure, &input, &output);
    TEST_CHECK(output.baro_update_count == 2U && output.baro_reject_count == 4U);
    TEST_CHECK(LoggerBus_OverflowCountGet() == 0U);
    return Test_Finish("sf6_backend_cold_pressure_actual");
}
