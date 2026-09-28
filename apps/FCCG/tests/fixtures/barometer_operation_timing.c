/* Inserted after the actual App time resolver and barometer replay functions. */
int main(void)
{
    static NavigationReplayStorage storage;
    NavigationKfContext reference;
    NavigationKfContext wrong_present;
    EstimatorBarometerUpdateWork work;
    SystemEstimatorProfile profile = {0};
    const float delta[3] = {0.0f, 0.0f, 0.001f};
    const uint64_t present = 1500000ULL;
    unsigned int trusted, axis, column, step;
    profile.nis_1d_soft = 3.84f;
    profile.nis_max_r_scale = 100.0f;
    for (trusted = 0U; trusted < 2U; trusted++)
    {
        uint64_t expected = trusted ? 1300000ULL :
            present - (uint64_t)SYSTEM_ESTIMATOR_BARO_MEASUREMENT_DELAY_MS * 1000ULL;
        float wrong_difference = 0.0f;
        (void)memset(&s_estimator, 0, sizeof(s_estimator));
        (void)memset(&work, 0, sizeof(work));
        NavigationKf_Init(&s_estimator.kf);
        NavigationKf_Reset(&s_estimator.kf);
        s_estimator.kf.state[5] = 2.0f;
        reference = s_estimator.kf;
        NavigationReplay_Reset(&s_replay, &storage, &s_estimator.kf, 1000000ULL, 4U);
        for (step = 1U; step <= 100U; step++)
        {
            uint64_t timestamp = 1000000ULL + step * 5000ULL;
            if (!NavigationKf_Predict(&reference, delta, 0.005f) ||
                NavigationReplay_Predict(&s_replay, &s_estimator.kf,
                    timestamp, delta, 0.005f) != NAV_REPLAY_OK) { return 1; }
            if (timestamp == expected)
            { (void)NavigationKf_UpdateBaroAltitude(&reference, 0.3f, 0.25f); }
        }
        wrong_present = s_estimator.kf;
        (void)NavigationKf_UpdateBaroAltitude(&wrong_present, 0.3f, 0.25f);
        work.pressure.timestamp_us = 1300000ULL;
        work.pressure.receive_timestamp_us = present;
        work.pressure.measurement_timestamp_trusted = (uint8_t)trusted;
        work.pressure.sequence = 11U;
        work.relative_altitude_m = 0.3f;
        work.variance_m2 = 0.25f;
        Estimator_BarometerReplay(present, &profile, &work);
        if (work.measurement.measurement_timestamp_us != expected ||
            work.measurement.operation_sequence != 1U ||
            work.measurement.replay_result != NAV_REPLAY_OK ||
            work.measurement.update_result != NAV_KF_UPDATE_ACCEPTED ||
            work.measurement.replay_generation != (uint32_t)(expected < present))
        { fprintf(stderr, "Barometer operation identity/timing mismatch\n"); return 2; }
        for (axis = 0U; axis < 6U; axis++)
        {
            if (fabsf(reference.state[axis] - s_estimator.kf.state[axis]) > 0.00001f)
            { return 3; }
            wrong_difference += fabsf(reference.state[axis] - wrong_present.state[axis]);
            for (column = 0U; column < 6U; column++)
            {
                if (fabsf(reference.covariance[axis][column] -
                    s_estimator.kf.covariance[axis][column]) > 0.00001f) { return 4; }
            }
        }
        if (expected < present && wrong_difference < 0.001f)
        { fprintf(stderr, "Current-state negative control failed\n"); return 5; }
    }
    return 0;
}
