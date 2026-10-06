/* Production application functions are extracted unchanged above this fixture.
 * Host stubs cover task locks, no available sensor packet, and log sinks only.
 * Actual KF6/replay/attitude/mechanization code is linked. No MCU recovery. */
static void Test_Seed(void)
{
    memset(&s_estimator, 0, sizeof(s_estimator));
    memset(&s_snapshot, 0, sizeof(s_snapshot));
    memset(&s_published_snapshot, 0, sizeof(s_published_snapshot));
    NavigationKf_Init(&s_estimator.kf);
    NavigationKf_Reset(&s_estimator.kf);
    s_estimator.q_nb[0] = 1.0f;
    s_estimator.initialized = 1U;
    s_estimator.mission_running = 1U;
    s_estimator.gnss_origin_valid = 1U;
    s_estimator.baro_origin_valid = 1U;
    s_estimator.gnss_window.count = 5U;
    NavigationReplay_Reset(&s_replay, &s_replay_storage, &s_estimator.kf, 1000000ULL, 7U);
    s_measurement_fault = 0U;
    Estimator_SnapshotPublish(1000000ULL);
}

static void Test_Predict(void)
{
    SystemInertialIncrement input = {0};
    input.timestamp_us = 1005000ULL;
    input.dt_s = 0.005f;
    input.delta_velocity_b_sculling_corrected[2] = SYSTEM_KF_GRAVITY_MPS2 * input.dt_s;
    Estimator_PredictionProcess(&input);
}

static void Test_Healthy(void)
{
    EstimatorOutputSnapshot output;
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 1U);
    TEST_CHECK(output.initialized == 1U);
    /* No sensor packet is supplied here; supervisor timeout is legitimate. */
    TEST_CHECK((output.health_flags & ~ESTIMATOR_HEALTH_FUSION_TIMEOUT) == 0U);
    TEST_CHECK(output.prediction_queue_overflow_count == 0U);
    TEST_CHECK(s_replay.faulted == 0U);
}

int main(int argc, char **argv)
{
    unsigned scenario = (argc == 2) ? (unsigned)strtoul(argv[1], NULL, 10) : 999U;
    Test_Seed();
    if (scenario < 16U)
    {
        s_estimator.kf.health_flags = scenario;
        Estimator_SnapshotPublish(1000000ULL);
        Test_Healthy();
        TEST_CHECK(s_estimator.kf.health_flags == scenario);
        /* Every raw-bit combination also preserves the application's single
         * terminal-fault identity when the real replay model contract fails. */
        s_estimator.kf.process_accel_std_mps2[0] *= 2.0f;
        Test_Predict();
        EstimatorOutputSnapshot output;
        TEST_CHECK(s_replay.faulted == 1U);
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        TEST_CHECK(output.timestamp_us == 1000000ULL && output.update_sequence == 2U);
        TEST_CHECK(output.prediction_queue_overflow_count == 0U);
        TEST_CHECK(s_estimator.kf.health_flags == scenario);
    }
    else if (scenario == 16U)
    {
        s_estimator.kf.covariance[2][2] = -1.0f;
        TEST_CHECK(NavigationKf_UpdateBaroAltitude(&s_estimator.kf, 0.0f, 1.0f) == NAV_KF_UPDATE_NUMERIC_ERROR);
        TEST_CHECK((s_estimator.kf.health_flags & NAV_KF_HEALTH_COVARIANCE_RECOVERED) != 0U);
        Test_Predict();
        Test_Healthy();
    }
    else if (scenario == 17U || scenario == 18U)
    {
        const float observation[3] = {(scenario == 17U) ? NAN : 10000000.0f,
            (scenario == 17U) ? 0.0f : 10000000.0f,
            (scenario == 17U) ? 0.0f : 10000000.0f};
        const float variance[3] = {1.0f, 1.0f, 1.0f};
        if (scenario == 17U)
        {
            NavigationKfGnssSeparatedUpdateResult separated;
            (void)NavigationKf_UpdateGnssPositionSeparated(&s_estimator.kf, observation, variance, &separated);
            TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_REJECTED_INVALID);
            TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_ACCEPTED);
        }
        else
        { TEST_CHECK(NavigationKf_UpdateGnssPosition(&s_estimator.kf, observation, variance) == NAV_KF_UPDATE_REJECTED_NIS); }
        Test_Predict();
        Test_Healthy();
    }
    else if (scenario == 19U || scenario == 20U)
    {
        EstimatorOutputSnapshot output;
        if (scenario == 19U) { s_estimator.kf.process_accel_std_mps2[0] *= 2.0f; }
        else { s_measurement_fault = 1U; }
        Test_Predict();
        TEST_CHECK(s_replay.faulted == 1U);
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.initialized == 0U);
        TEST_CHECK(output.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        TEST_CHECK(output.timestamp_us == 1000000ULL);
        TEST_CHECK(output.update_sequence == 1U);
        TEST_CHECK(output.prediction_queue_overflow_count == 0U);
        FlightLogStatsRecord stats;
        DiagnosticLog_StatsRecordBuild(&stats);
        TEST_CHECK(stats.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        SystemInsDiagnostics diagnostics = {0};
        diagnostics.quaternion_valid = diagnostics.velocity_valid = diagnostics.position_valid = 1U;
        diagnostics.software_attitude_propagation = 1U;
        InsTask_NavigationDiagnosticsApply(&diagnostics);
        TEST_CHECK(diagnostics.quaternion_valid == 0U && diagnostics.velocity_valid == 0U);
        TEST_CHECK(diagnostics.position_valid == 0U && diagnostics.software_attitude_propagation == 0U);
        Test_Predict();
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U && output.timestamp_us == 1000000ULL);
    }
    else if (scenario == 21U)
    {
        EstimatorOutputSnapshot output;
        EstimatorTask_RollbackMissionStart();
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.gnss_origin_valid == 0U && output.baro_origin_valid == 0U);
        TEST_CHECK(s_estimator.gnss_origin_valid == 0U && s_estimator.baro_origin_valid == 0U);
        TEST_CHECK(s_estimator.gnss_window.count == 5U);
        TEST_CHECK(s_estimator.origin_collection_frozen == 0U);
    }
    else if (scenario == 22U)
    {
        s_bus_overflow = 3U;
        Estimator_SnapshotPublish(1000000ULL);
        EstimatorOutputSnapshot output;
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 1U);
        TEST_CHECK(output.prediction_queue_overflow_count == 3U);
        TEST_CHECK(output.health_flags == 0U);
    }
    else { TEST_CHECK(0); }
    return Test_Finish("estimator_health");
}
