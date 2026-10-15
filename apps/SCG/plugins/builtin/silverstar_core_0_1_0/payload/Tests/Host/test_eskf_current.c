/* Host-only reuse of the existing device inputs, real queues and log setup.
 * Including the owning backend permits full private-state/P comparison; target
 * firmware does not acquire a test/export interface. */
#define main ExistingBackend_Main
#define s_gnss_source s_fixture_gnss_source
#include "test_eskf_backend.c"
#undef s_gnss_source
#undef main
#include "../../Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c"

static NavigationEskfState s_expected;
static NavigationEskfWorkspace s_expected_work;

static void Test_CurrentSetup(void)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    SystemInertialIncrement input = {0};
    EstimatorOutputSnapshot output = {0};
    memset(&s_gnss, 0, sizeof(s_gnss));
    s_gnss.receive_timestamp_us = UINT64_MAX;
    TEST_CHECK(SystemNavigationBackend_Initialize(q, &s_gnss, 0.0f, 0U, 77U, 1U) == SYSTEM_DEVICE_OK);
    input.dt_s = 0.01f;
    input.body_accel_mps2[0][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    input.body_accel_mps2[1][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    input.body_gyro_radps[0][2] = 0.2f;
    input.body_gyro_radps[1][2] = 0.4f;
    for (uint32_t index = 1U; index <= 100U; index++)
    {
        input.timestamp_us = 1000000ULL + index * 10000ULL;
        input.sequence = index;
        HostPlatformMock_TimeSetUs(input.timestamp_us);
        TEST_CHECK(SystemNavigationBackend_Predict(&input, &output) == SYSTEM_DEVICE_OK);
        Test_RecordsDrain();
    }
    TEST_CHECK(s_current_endpoint_rate[2] == input.body_gyro_radps[1][2]);
    s_expected = s_state;
}

static NavigationEskfReplayEvent Test_CurrentEvent(uint8_t group, uint32_t sequence)
{
    NavigationEskfReplayEvent event = {0};
    event.measurement_us = 1700000ULL; event.receive_us = 1900000ULL;
    event.sequence = sequence; event.source = (group == 4U) ? 1U : 0U;
    event.generation = 77U; event.measurement.group = group;
    event.measurement.physically_valid = 1U;
    event.measurement.variance[0] = 4.0f; event.measurement.variance[1] = 4.0f;
    event.measurement.observation[0] = 0.1f;
    memcpy(event.measurement.angular_rate_b_radps, s_current_endpoint_rate, sizeof(s_current_endpoint_rate));
    return event;
}

static void Test_CurrentApplyAtPresent(void)
{
    NavigationEskfReplayEvent event;
    NavigationEskfOutcome outcome, expected_outcome;
    BackendMeasurementContext record = {0};
    Test_CurrentSetup();
    event = Test_CurrentEvent(4U, 1U);
    TEST_CHECK(NavigationEskf_Update(&s_expected, &s_expected_work, &s_config,
        &event.measurement, &expected_outcome) == NAV_ESKF_OK);
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_COMPLETE);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(memcmp(&outcome, &expected_outcome, sizeof(outcome)) == 0);
    TEST_CHECK(record.application_timestamp_us == 2000000ULL);
    TEST_CHECK(record.timing_flags == SYSTEM_FUSION_APPLICATION_EPOCH_VALID);
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_DUPLICATE);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
}

static void Test_CurrentAgesAndRetry(void)
{
    const uint64_t ages[] = {499999ULL, 500000ULL, 500001ULL};
    for (uint8_t receive_case = 0U; receive_case < 2U; receive_case++)
    {
        for (uint8_t index = 0U; index < 3U; index++)
        {
            NavigationEskfOutcome outcome;
            BackendMeasurementContext record = {0};
            NavigationEskfReplayEvent event;
            Test_CurrentSetup(); event = Test_CurrentEvent(4U, 1U);
            event.measurement_us = 2000000ULL - ages[index];
            event.receive_us = receive_case ? event.measurement_us : 2000000ULL;
            TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) ==
                ((index < 2U) ? SYSTEM_FUSION_EXEC_COMPLETE : SYSTEM_FUSION_EXEC_STALE));
            if (index == 2U)
            {
                TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
                TEST_CHECK(record.application_timestamp_us == 0U);
                if (receive_case == 0U)
                {
                    event.measurement_us = 1900000ULL;
                    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_DUPLICATE);
                }
            }
        }
    }
}

static void Test_CurrentSourceAndFailure(void)
{
    NavigationEskfOutcome outcome;
    BackendMeasurementContext record = {0};
    NavigationEskfReplayEvent event;
    Test_CurrentSetup(); event = Test_CurrentEvent(0U, UINT32_MAX);
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_COMPLETE);
    event.source = 1U;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_COMPLETE);
    event.source = 0U;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_DUPLICATE);
    event.sequence = 0U;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_COMPLETE);
    event.sequence = 0x80000000UL;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_DISCONTINUITY);
    event.source = UINT32_MAX;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_INVALID);
    Test_CurrentSetup(); event = Test_CurrentEvent(4U, 1U);
    s_state.covariance[0][0] = NAN; s_expected = s_state;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_NUMERIC_ERROR);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(s_current_faulted == 1U);
}

static void Test_CurrentEndpointAndUpdatedBias(void)
{
    EstimatorOutputSnapshot output = {0};
    NavigationEskfOutcome expected_outcome;
    float previous_bias[3];
    Test_CurrentSetup();
    for (uint8_t row = 0U; row < NAV_ESKF_DIM; row++)
    {
        for (uint8_t column = 0U; column < NAV_ESKF_DIM; column++)
        { s_state.covariance[row][column] += 0.0001f * (float)(row + 1U) * (float)(column + 1U); }
    }
    s_state.gyro_bias[0] = 0.01f; s_state.gyro_bias[1] = 0.02f; s_state.gyro_bias[2] = 0.03f;
    memcpy(previous_bias, s_state.gyro_bias, sizeof(previous_bias));
    s_expected = s_state;
    for (uint8_t group = 2U; group < 4U; group++)
    {
        BackendMeasurementContext record = {0};
        NavigationEskfReplayEvent event = Test_CurrentEvent(group, 1U);
        NavigationEskfMeasurement expected_measurement = event.measurement;
        expected_measurement.lever_arm_b_m[0] = SYSTEM_ESKF_LEVER_ARM_BODY_X_M;
        expected_measurement.lever_arm_b_m[1] = SYSTEM_ESKF_LEVER_ARM_BODY_Y_M;
        expected_measurement.lever_arm_b_m[2] = SYSTEM_ESKF_LEVER_ARM_BODY_Z_M;
        TEST_CHECK(NavigationEskf_Update(&s_expected, &s_expected_work, &s_config,
            &expected_measurement, &expected_outcome) == NAV_ESKF_OK);
        event.measurement.angular_rate_b_radps[2] = NAN;
        Backend_EventApply(&event, &record, &output);
        TEST_CHECK(record.execution_result == SYSTEM_FUSION_EXEC_COMPLETE);
        TEST_CHECK(event.measurement.angular_rate_b_radps[2] == 0.4f);
        TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
        TEST_CHECK(record.application_timestamp_us == s_state.timestamp_us);
    }
    TEST_CHECK(memcmp(previous_bias, s_state.gyro_bias, sizeof(previous_bias)) != 0);
    Test_RecordsDrain();
}

static void Test_CurrentKernelInvalidIsCompleted(void)
{
    for (uint8_t item = 0U; item < 2U; item++)
    {
        BackendMeasurementContext record = {0};
        NavigationEskfOutcome outcome;
        NavigationEskfReplayEvent event;
        Test_CurrentSetup(); event = Test_CurrentEvent(4U, 1U);
        if (item == 0U) { event.measurement.observation[0] = NAN; }
        else { event.measurement.variance[0] = 0.0f; }
        TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_COMPLETE);
        TEST_CHECK(outcome.result == NAV_ESKF_INVALID_INPUT && s_current_faulted == 0U);
        TEST_CHECK(record.application_timestamp_us == 2000000ULL);
        TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    }
}

static void Test_CurrentFirstPredictFailure(void)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    SystemInertialIncrement input = {0};
    EstimatorOutputSnapshot output = {0};
    NavigationEskfOutcome outcome;
    BackendMeasurementContext record = {0};
    NavigationEskfReplayEvent event = Test_CurrentEvent(4U, 1U);
    TEST_CHECK(SystemNavigationBackend_Initialize(q, &s_gnss, 0.0f, 0U, 77U, 1U) == SYSTEM_DEVICE_OK);
    s_expected = s_state;
    TEST_CHECK(Backend_CurrentEventApply(&event, &record, &outcome) == SYSTEM_FUSION_EXEC_NOT_READY);
    input.timestamp_us = 3000000ULL; input.dt_s = 0.01f;
    input.body_gyro_radps[1][0] = NAN;
    TEST_CHECK(SystemNavigationBackend_Predict(&input, &output) == SYSTEM_DEVICE_VERIFY_FAILED);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(s_current_endpoint_valid == 0U && s_current_faulted == 1U);
    TEST_CHECK(output.initialized == 0U && output.mission_running == 0U);
    TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
}

int main(int argc, char **argv)
{
    const FlightLogRecordType streams[] = { FLIGHT_LOG_RECORD_ESKF15_STATE,
        FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART, FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE,
        FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART, FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT,
        FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT, FLIGHT_LOG_RECORD_NAV_QUALITY };
    (void)argc; (void)argv;
    HostPlatformMock_Reset();
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    for (uint8_t index = 0U; index < sizeof(streams) / sizeof(streams[0]); index++)
    {
        SystemLogStreamConfig config;
        TEST_CHECK(SystemLogPolicy_StreamGet(streams[index], &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U; config.decimation = 1U;
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
    SystemCalibration_Init();
    TEST_CHECK(LoggerBus_MissionConfigPush(SystemTime_GetMonotonicUs()) == LOGGER_BUS_RESULT_OK);
    Test_RecordsDrain();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    Test_CurrentApplyAtPresent();
    Test_CurrentAgesAndRetry();
    Test_CurrentSourceAndFailure();
    Test_CurrentEndpointAndUpdatedBias();
    Test_CurrentKernelInvalidIsCompleted();
    Test_CurrentFirstPredictFailure();
    return Test_Finish("eskf_current");
}
