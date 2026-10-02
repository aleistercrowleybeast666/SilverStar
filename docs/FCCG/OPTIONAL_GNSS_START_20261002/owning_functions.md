### apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/System/Alignment/Src/system_alignment.c :: SystemAlignment_Init

```c
void SystemAlignment_Init(void)
{
    uint32_t primask = SystemAlignment_IrqLock();
    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(s_initialized <= 1U, SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);

    (void)memset(&s_status, 0, sizeof(s_status));
    SystemAlignment_GuardReset();
    s_status.capability_mask = SystemAlignment_CapabilityDetect();
    s_status.selected_mask = SYSTEM_USER_ALIGNMENT_SELECTED_MASK;
    s_status.required_mask = SYSTEM_USER_ALIGNMENT_REQUIRED_MASK;
    /* Fusion's origin prerequisite does not promote an optional mission source. */
    s_status.config_result = SystemAlignment_MasksValidate(
        s_status.capability_mask, s_status.selected_mask,
        s_status.required_mask, &s_status.unavailable_mask);
    SystemAlignment_StatusReset((s_status.config_result ==
        SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED) ?
            SYSTEM_ALIGNMENT_STATE_FAILED : SYSTEM_ALIGNMENT_STATE_IDLE);
    s_initialized = 1U;
    s_collecting = 0U;
    s_frozen = 0U;
    s_action_active = 0U;
    SystemAlignment_IrqUnlock(primask);
}
```

### apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/APP/Src/estimator_task.c :: EstimatorTask_FreezeOrigins

```c
SystemDeviceResult EstimatorTask_FreezeOrigins(void)
{
    uint32_t primask;

    SILVERSTAR_ASSERT(s_estimator.mission_running <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_estimator.origin_collection_frozen <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_estimator.mission_running != 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    primask = EstimatorTask_IrqLock();
    s_estimator.origin_collection_frozen = 1U;
    EstimatorTask_IrqUnlock(primask);
    if (Estimator_OriginCollectionWait() != SYSTEM_DEVICE_OK)
    {
        s_estimator.origin_collection_frozen = 0U;
        return SYSTEM_DEVICE_TIMEOUT;
    }
    /* A fresh START must not reuse a previous preparation's GNSS reference. */
    (void)memset(&s_estimator.frozen_gnss, 0, sizeof(s_estimator.frozen_gnss));
    (void)memset(&s_estimator.gnss_frame, 0, sizeof(s_estimator.gnss_frame));
    s_estimator.gnss_origin_sample_count = 0U;
    s_estimator.gnss_origin_valid = Estimator_GnssOriginFreeze();
    if (Estimator_Kf6Selected() == 0U)
    {
        s_estimator.gnss_fusion_enabled = 0U;
    }
    else
    {
        s_estimator.gnss_fusion_enabled =
            (SYSTEM_ESTIMATOR_GNSS_FUSION_REQUIRES_PREFLIGHT_ORIGIN != 0U) ?
                s_estimator.gnss_origin_valid : 1U;
    }
    s_estimator.baro_origin_valid = Estimator_BarometerOriginFreeze();
    Estimator_FrozenBarometerPublish();
    if (s_estimator.gnss_origin_valid == 0U)
    {
        s_snapshot.health_flags |= ESTIMATOR_HEALTH_GNSS_ORIGIN_UNAVAILABLE;
    }
    if (s_estimator.baro_origin_valid == 0U)
    {
        s_snapshot.health_flags |= ESTIMATOR_HEALTH_BARO_ORIGIN_UNAVAILABLE;
    }
    Estimator_DiagnosticsPublish(0U);
    /* Only explicit mission requirements block START. Without an optional
       origin, fusion remains disabled for this mission and health reports it. */
    if (((SYSTEM_USER_ALIGNMENT_REQUIRED_MASK &
          SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U) &&
        (s_estimator.gnss_origin_valid == 0U))
    {
        s_estimator.origin_collection_frozen = 0U;
        return SYSTEM_DEVICE_NOT_READY;
    }
    return (s_estimator.baro_origin_valid != 0U) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
```

### apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c :: SystemNavigationBackend_Reset

```c
void SystemNavigationBackend_Reset(void)
{
    s_active = 0U; s_started = 0U; s_gnss_seen = 0U; s_baro_seen = 0U;
    s_state.initialized = 0U; s_operation = 0U; s_snapshot_id = 0U;
    memset(&s_frame, 0, sizeof(s_frame));
    s_native_week_us = 0U; s_native_tow_ms = 0U; s_log_failures = 0U;
    s_imu_quality_flags = 0U;
    (void)NavigationWindow_Reset(&s_eskf_window);
}
```

### apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_eskf15/payload/Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c :: SystemNavigationBackend_Initialize

```c
SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],
    const SystemGnssSample *origin, float barometer_origin_m,
    uint8_t barometer_origin_valid, uint32_t generation, uint8_t activate)
{
    (void)barometer_origin_valid; /* ESKF behavior is unchanged by the SF6 reference contract. */
    float nominal[16] = {0.0f};
    uint32_t axis;
    uint8_t source;
    if ((q_nb == NULL) || (origin == NULL) || !isfinite(barometer_origin_m))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(origin, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SystemNavigationBackend_Reset();
    if ((NavigationEskf_ConfigValidate(&s_config) != NAV_ESKF_OK) ||
        (NavigationWindow_ConfigValidate(&s_window_config) != NAV_QUALITY_OK))
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    if (SystemSourceSelector_ImuActiveInstanceGet(&source) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    memcpy(&nominal[6], q_nb, 4U * sizeof(float));
    if (origin->position_usable != 0U)
    {
        if ((SystemSourceSelector_GnssActiveInstanceGet(&s_gnss_source) != SYSTEM_DEVICE_OK) ||
            (GeoLocalFrame_Init(&s_frame, origin->latitude_e7, origin->longitude_e7,
                               origin->ellipsoid_height_mm) == 0U))
        { return SYSTEM_DEVICE_NOT_READY; }
        for (axis = 0U; axis < 3U; axis++)
        {
            if ((origin->velocity_valid_mask & (1U << axis)) != 0U)
            { nominal[3U + axis] = origin->velocity_enu_mps[axis]; }
        }
    }
    memset(s_work.f, 0, sizeof(s_work.f));
    for (axis = 0U; axis < NAV_ESKF_DIM; axis++)
    { s_work.f[axis][axis] = s_initial_diagonal[axis]; }
    if (NavigationEskf_Initialize(&s_state, &s_work, nominal,
            (const float (*)[NAV_ESKF_DIM])s_work.f, 0U, source, generation) != NAV_ESKF_OK)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    if (NavigationEskfReplay_Reset(&s_history, &s_state, s_body_history) != NAV_ESKF_REPLAY_OK)
    { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    s_baro_origin = barometer_origin_m; s_active = activate;
    s_calibration_generation = SystemCalibration_GenerationGet();
    SystemNavigationHealth_Reset(0U);
    return SYSTEM_DEVICE_OK;
}
```

### apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c :: SystemNavigationBackend_Initialize

```c
SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],
    const SystemGnssSample *origin, float barometer_origin_m,
    uint8_t barometer_origin_valid, uint32_t generation, uint8_t activate)
{
    float velocity[3] = {0.0f};
    float quaternion[4];
    uint8_t axis;
    (void)generation; /* SF6 has no covariance generation or bias-state reset. */
    if (q_nb == NULL || origin == NULL || activate > 1U || barometer_origin_valid > 1U ||
        !isfinite(barometer_origin_m)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SystemNavigationBackend_Reset();
    memcpy(quaternion, q_nb, sizeof(quaternion));
    for (axis = 0U; axis < 4U; axis++)
    { if (!isfinite(quaternion[axis])) { return SYSTEM_DEVICE_INVALID_ARGUMENT; } }
    if (!Attitude_QuaternionNormalize(quaternion)) { return SYSTEM_DEVICE_NOT_READY; }
    if (origin->position_usable != 0U)
    {
        if (SystemSourceSelector_GnssActiveInstanceGet(&s_gnss_source) != SYSTEM_DEVICE_OK ||
            !GeoLocalFrame_Init(&s_frame, origin->latitude_e7, origin->longitude_e7,
                origin->ellipsoid_height_mm)) { return SYSTEM_DEVICE_NOT_READY; }
        for (axis = 0U; axis < 3U; axis++)
        {
            if ((origin->velocity_valid_mask & (1U << axis)) != 0U)
            { velocity[axis] = origin->velocity_enu_mps[axis]; }
        }
    }
    if (NavigationSf6_Initialize(&s_context, s_gain, velocity, 0U) != NAV_SF6_OK)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    memcpy(s_q_nb, quaternion, sizeof(s_q_nb));
    s_baro_origin = barometer_origin_m; s_baro_origin_valid = barometer_origin_valid; s_active = activate;
    SystemNavigationHealth_Reset(0U);
    return SYSTEM_DEVICE_OK;
}
```

### apps/FCCG/plugins/builtin/silverstar_algorithm_estimator_sf6/payload/Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c :: Backend_GnssUpdate

```c
static void Backend_GnssUpdate(EstimatorOutputSnapshot *output)
{
    SystemGnssSample sample;
    float position[3];
    uint8_t group, source;
    /* An absent preflight frame stays absent; never rebase a moving mission. */
    if (s_frame.valid == 0U) { return; }
    if (SystemSourceSelector_GnssActiveInstanceGet(&source) != SYSTEM_DEVICE_OK) { return; }
    if (source != s_gnss_source)
    {
        /* A different GNSS reference is not supported until mission reinit. */
        output->health_flags |= ESTIMATOR_HEALTH_GNSS_MEASUREMENT_INVALID;
        return;
    }
    if (SystemGnss_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK ||
        sample.receive_timestamp_us > output->timestamp_us ||
        (s_gnss_seen && sample.sequence == s_gnss_sequence)) { return; }
    s_gnss_seen = 1U; s_gnss_sequence = sample.sequence;
    if (SystemGnssQuality_Evaluate(&sample, output->timestamp_us) != SYSTEM_DEVICE_OK)
    { sample.valid_group_mask = 0U; }
    if (!GeoLocalFrame_ToEnu(&s_frame,
        sample.valid_group_mask & 1U ? sample.latitude_e7 : s_frame.origin_lat_e7,
        sample.valid_group_mask & 1U ? sample.longitude_e7 : s_frame.origin_lon_e7,
        sample.valid_group_mask & 2U ? sample.ellipsoid_height_mm : s_frame.origin_height_mm, position))
    { memset(position, 0, sizeof(position)); sample.valid_group_mask &= (uint8_t)~3U; }
    output->last_gnss_timestamp_us = sample.receive_timestamp_us;
    output->last_gnss_sequence = sample.sequence;
    memcpy(output->gnss_position_enu_m, position, sizeof(position));
    memcpy(output->gnss_velocity_enu_mps, sample.velocity_enu_mps, sizeof(sample.velocity_enu_mps));
    for (group = 0U; group < 4U; group++)
    { Backend_GnssGroupApply(&sample, position, group, output); }
}
```
