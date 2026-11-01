/* Reuse the real START fixture, then run real corrected INS aggregation,
 * real bounded prediction queue and actual KF6 application publication. */
#define main OptionalStart_ExistingCases
#include "test_optional_gnss_start.c"
#undef main

void Test_ControlRawFeed(uint64_t timestamp_us, uint32_t sequence, uint8_t source_valid, uint8_t source);
uint8_t Test_ControlInsFaultGet(void);
void Test_ControlQueueNotReady(void);
void Test_ControlAlignmentSourceChange(uint8_t enabled);

static void ControlProof_Drain(void)
{
    FlightLogRecord record;
    for (uint32_t index = 0U; index < 128U; index++)
    { if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; } }
}

static void ControlProof_Feed(uint32_t sequence, uint8_t valid, uint8_t source, uint8_t consume)
{
    s_test_now += 5000ULL;
    HostPlatformMock_TimeSetUs(s_test_now);
    Test_ControlRawFeed(s_test_now, sequence, valid, source);
    if (consume != 0U) { Estimator_PredictionsProcessCycle(); }
    ControlProof_Drain();
}

int main(int argc, char **argv)
{
    EstimatorOutputSnapshot output;
    TEST_CHECK(argc == 2);
    HostPlatformMock_Reset();
    TEST_CHECK(ImuSampleBus_Init() == IMU_SAMPLE_BUS_RESULT_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    Test_ControlAlignmentSourceChange((uint8_t)(strcmp(argv[1], "alignment_source") == 0));
    Test_Reset(1U, (uint8_t)((SYSTEM_FUSION_CONFIGURED_MASK & 0x10U) != 0U));
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_OK);
    if (strcmp(argv[1], "queue_not_ready") == 0)
    {
        Test_ControlQueueNotReady();
        for (uint32_t step = 1U; step <= 4U; step++) { ControlProof_Feed(step, 1U, 0U, 0U); }
        TEST_CHECK(Test_ControlInsFaultGet() != 0U);
        return Test_Finish("control_queue_not_ready_actual");
    }
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) != 0U && output.attitude_provenance.valid == 0U);
    uint32_t index;
    for (index = 1U; index <= 100U; index++) { ControlProof_Feed(index, 1U, 0U, 1U); }
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) != 0U);
    if (strcmp(argv[1], "alignment_source") == 0)
    {
        TEST_CHECK(output.attitude_provenance.valid == 0U);
        return Test_Finish("control_alignment_source_history_actual");
    }
    if (strcmp(argv[1], "queue_full_boundary") != 0)
    {
        TEST_CHECK(output.attitude_provenance.valid == 1U);
        TEST_CHECK(output.attitude_provenance.source_instance == 0U);
        TEST_CHECK(output.attitude_provenance.calibration_generation == SystemCalibration_GenerationGet());
        TEST_CHECK(EstimatorTask_ControlProvenanceCheck(&output.attitude_provenance,
            output.timestamp_us, output.update_sequence) == SYSTEM_DEVICE_OK);
    }
    TEST_CHECK(output.predict_count > 0U && output.q_nb[2] > 0.001f);
    SystemNavigationProvenance admitted = output.attitude_provenance;
    uint64_t admitted_us = output.timestamp_us;
    uint32_t admitted_sequence = output.update_sequence;
    if (strcmp(argv[1], "normal") == 0) { return Test_Finish("control_provenance_normal_actual"); }
    if ((strcmp(argv[1], "queue_full") == 0) || (strcmp(argv[1], "queue_full_boundary") == 0))
    {
        for (; index <= 240U; index++) { ControlProof_Feed(index, 1U, 0U, 0U); }
        EstimatorBusStats stats;
        EstimatorBus_StatsGet(&stats);
        TEST_CHECK(stats.prediction_overflow_count > 0U);
        TEST_CHECK(Test_ControlInsFaultGet() != 0U);
        if (strcmp(argv[1], "queue_full_boundary") == 0) { return Test_Finish("control_queue_full_actual"); }
    }
    else if (strcmp(argv[1], "source") == 0)
    { ControlProof_Feed(index++, 1U, 1U, 0U); }
    else if (strcmp(argv[1], "unknown") == 0)
    { ControlProof_Feed(index++, 0U, 0U, 0U); }
    else { TEST_CHECK(0); }
    uint8_t available = Estimator_GetLatestSnapshot(&output);
    TEST_CHECK(available == output.initialized && output.attitude_provenance.valid == 0U);
    TEST_CHECK((output.health_flags & ESTIMATOR_HEALTH_INPUT_PROVENANCE_INVALID) != 0U);
    Estimator_PredictionsProcessCycle(); /* Older queued work cannot restore proof. */
    for (uint32_t step = 0U; step < 5U; step++) { ControlProof_Feed(index++, 1U, 0U, 1U); }
    /* A discontinuous backlog may also stop the numerical estimator. Never
     * require it to remain initialized after a real fault. The proof must
     * stay revoked in both the running-invalid and stopped-invalid states. */
    available = Estimator_GetLatestSnapshot(&output);
    TEST_CHECK(available == output.initialized && output.attitude_provenance.valid == 0U);
    TEST_CHECK((output.health_flags & ESTIMATOR_HEALTH_INPUT_PROVENANCE_INVALID) != 0U);
    TEST_CHECK(EstimatorTask_ControlProvenanceCheck(&admitted, admitted_us,
        admitted_sequence) == SYSTEM_DEVICE_NOT_READY);
    return Test_Finish("control_provenance_fault_actual");
}
