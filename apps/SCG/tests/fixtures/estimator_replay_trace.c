/* App orchestration fixture: production work type/helpers are inserted above. */
static uint64_t TestApp_Hash(uint64_t hash, const void *data, size_t size)
{
    const unsigned char *bytes = data;
    size_t i;
    for (i = 0U; i < size; i++) { hash = (hash ^ bytes[i]) * UINT64_C(1099511628211); }
    return hash;
}

static int TestApp_GroupDiagnostics(void)
{
    EstimatorGnssUpdateWork work;
    (void)memset(&work, 0, sizeof(work));
    work.sample.valid_group_mask = 15U;
    work.position_group_result.horizontal_attempted = 1U;
    work.position_group_result.vertical_attempted = 1U;
    work.velocity_group_result.horizontal_attempted = 1U;
    work.velocity_group_result.vertical_attempted = 1U;
    work.position_group_result.horizontal_result = NAV_KF_UPDATE_ACCEPTED;
    work.position_group_result.vertical_result = NAV_KF_UPDATE_REJECTED_NIS;
    work.velocity_group_result.horizontal_result = NAV_KF_UPDATE_SOFT_WEIGHTED;
    work.velocity_group_result.vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    /* The reusable replay_outcome only describes the last insertion. */
    Estimator_GnssGroupDiagnosticsRefresh(&work);
    return s_estimator.gnss_diagnostics.group[0].update_result != NAV_KF_UPDATE_ACCEPTED ||
        s_estimator.gnss_diagnostics.group[1].update_result != NAV_KF_UPDATE_REJECTED_NIS ||
        s_estimator.gnss_diagnostics.group[2].update_result != NAV_KF_UPDATE_SOFT_WEIGHTED ||
        s_estimator.gnss_diagnostics.group[3].update_result != NAV_KF_UPDATE_REJECTED_INVALID;
}

int main(void)
{
    unsigned int step, axis;
    uint64_t hash = UINT64_C(14695981039346656037);
    static NavigationReplayStorage storage;
    if (TestApp_GroupDiagnostics() != 0) { return 3; }
    NavigationKf_Init(&s_estimator.kf);
    NavigationKf_Reset(&s_estimator.kf);
    NavigationReplay_Reset(&s_replay, &storage, &s_estimator.kf, 1000000ULL, 7U);
    {
        NavigationWindowConfig config = Estimator_IntegrityConfigGet();
        if ((NavigationWindow_ConfigValidate(&config) != NAV_QUALITY_OK) ||
            (NavigationWindow_Reset(&s_integrity) != NAV_QUALITY_OK)) { return 6; }
    }
    for (step = 1U; step <= 450U; step++)
    {
        const float delta[3] = {0.0001f, 0.0002f, 0.0003f};
        uint64_t timestamp = 1000000ULL + (uint64_t)step * 5000ULL;
        if (NavigationReplay_Predict(&s_replay, &s_estimator.kf, timestamp, delta, 0.005f) != NAV_REPLAY_OK)
        { return 2; }
        if ((step % 8U == 0U) && ((step < 120U) || (step > 208U)))
        {
            EstimatorGnssUpdateWork work;
            (void)memset(&work, 0, sizeof(work));
            work.sample.receive_timestamp_us = timestamp;
            work.sample.sample_timestamp_us = timestamp;
            work.sample.sequence = step;
            work.epoch.valid_group_mask = 15U;
            work.velocity_dimension = 3U;
            for (axis = 0U; axis < 3U; axis++)
            {
                work.position_enu_m[axis] = 0.2f * sinf((float)step * 0.03f);
                work.sample.velocity_enu_mps[axis] = 0.05f * cosf((float)step * 0.03f);
                work.position_variance[axis] = 2.25f;
                work.velocity_variance[axis] = 0.04f;
                work.epoch.position_enu_m[axis] = work.position_enu_m[axis];
                work.epoch.velocity_enu_mps[axis] = work.sample.velocity_enu_mps[axis];
                work.epoch.position_std_m[axis] = 1.5f;
                work.epoch.velocity_std_mps[axis] = 0.2f;
            }
            Estimator_GnssReplay(timestamp, &work);
            if ((work.measurement.position_measurement_timestamp_us != timestamp -
                 (uint64_t)SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS * 1000ULL) ||
                (work.measurement.velocity_measurement_timestamp_us != timestamp -
                 (uint64_t)SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS * 1000ULL) ||
                (work.measurement.receive_operation_sequence == 0U) ||
                (work.measurement.receive_operation_sequence >= work.measurement.position_operation_sequence) ||
                (work.measurement.receive_operation_sequence >= work.measurement.velocity_operation_sequence) ||
                (work.measurement.replay_generation != s_replay.diagnostics.replay_count))
            { fprintf(stderr, "Actual operation timing was not recorded\n"); return 4; }
            if (((SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS >
                  SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS) &&
                 (work.measurement.position_operation_sequence >= work.measurement.velocity_operation_sequence)) ||
                ((SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS <
                  SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS) &&
                 (work.measurement.position_operation_sequence <= work.measurement.velocity_operation_sequence)) ||
                ((SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS ==
                  SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS) &&
                 (work.measurement.position_operation_sequence != work.measurement.velocity_operation_sequence)))
            { fprintf(stderr, "Split/combined GNSS operation ordering differs\n"); return 5; }
            hash = TestApp_Hash(hash, &work.replay_outcome, sizeof(work.replay_outcome));
            /* Retain the original numerical trace domain; health has its own causal tests. */
            hash = TestApp_Hash(hash, s_snapshot.position_innovation, sizeof(s_snapshot.position_innovation));
        }
        hash = TestApp_Hash(hash, &s_estimator.kf, sizeof(s_estimator.kf));
        hash = TestApp_Hash(hash, (const unsigned char *)&s_replay + offsetof(NavigationReplayContext, events),
                            sizeof(s_replay) - offsetof(NavigationReplayContext, events));
        hash = TestApp_Hash(hash, &storage, sizeof(storage));
        (void)printf("%016llx\n", (unsigned long long)hash);
    }
    return 0;
}
