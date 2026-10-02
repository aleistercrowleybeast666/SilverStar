static uint8_t TelemetryService_NavigationSend(void)
{
    EstimatorPreparationSnapshot preparation;
    AirNavigationStatusPayload payload;
    uint64_t now_us = SystemTime_GetMonotonicUs();
    uint8_t type;

    if (s_navigation_session == 0U) { return 0U; }
    SILVERSTAR_ASSERT(s_navigation_preparation_pending <= 1U,
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(now_us <= (UINT64_MAX - TELEMETRY_NAV_PREPARATION_PERIOD_US),
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    if ((now_us >= s_next_navigation_preparation_us) || (s_navigation_preparation_pending != 0U))
    {
        if (TelemetryService_NavigationPreparationGet(&payload, &preparation) == 0U) { return 0U; }
        type = AIR_TYPE_NAV_PREPARATION;
        if (s_navigation_preparation_pending == 0U)
        {
            type = AIR_TYPE_NAV_CAPABILITY;
            payload.tail[0] = AIR_NAV_SCHEMA_VERSION;
            payload.tail[1] = preparation.algorithm_id;
            payload.tail[2] = (preparation.algorithm_id == 0U) ? 0U : AIR_NAV_GROUP_MASK;
        }
        if (TelemetryService_NavigationFrameSend(type, &payload) != 0U)
        {
            s_navigation_preparation_pending = (uint8_t)(type == AIR_TYPE_NAV_CAPABILITY);
            s_next_navigation_preparation_us = now_us + TELEMETRY_NAV_PREPARATION_PERIOD_US;
        }
        return 1U;
    }
    return TelemetryService_NavigationHealthSend(now_us);
}
