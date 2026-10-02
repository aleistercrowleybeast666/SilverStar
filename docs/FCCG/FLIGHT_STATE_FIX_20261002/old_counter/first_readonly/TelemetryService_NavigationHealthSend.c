static uint8_t TelemetryService_NavigationHealthSend(uint64_t now_us)
{
    AirNavigationStatusPayload payload;
    uint8_t regular = (uint8_t)(now_us >= s_next_navigation_health_us);
    uint8_t index = (regular != 0U) ? s_navigation_health_index : s_navigation_detail_index;
    uint8_t group = ((regular != 0U) || (index < TELEMETRY_NAV_DETAIL_GROUP_ITEMS)) ?
        (index % SYSTEM_NAVIGATION_GROUP_COUNT) : 7U;
    uint8_t metric = (group == 7U) ? (uint8_t)(index - TELEMETRY_NAV_DETAIL_GROUP_ITEMS) :
        (uint8_t)((index / SYSTEM_NAVIGATION_GROUP_COUNT) + ((regular != 0U) ? 0U : 2U));
    uint16_t value;

    SILVERSTAR_ASSERT(index < ((regular != 0U) ? TELEMETRY_NAV_HEALTH_ITEM_COUNT : TELEMETRY_NAV_DETAIL_ITEM_COUNT),
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(now_us <= (UINT64_MAX - TELEMETRY_NAV_DETAIL_PERIOD_US),
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    if ((regular == 0U) && (now_us < s_next_navigation_detail_us)) { return 0U; }
    value = TelemetryService_NavigationMetricGet(group, metric, now_us);
    payload.session = s_navigation_session;
    payload.generation = s_navigation_generation;
    payload.tail[0] = (uint8_t)(group + (metric * 8U));
    payload.tail[1] = (uint8_t)value;
    payload.tail[2] = (uint8_t)(value >> 8U);
    if (TelemetryService_NavigationFrameSend(AIR_TYPE_NAV_HEALTH, &payload) != 0U)
    {
        if (regular != 0U)
        {
            s_navigation_health_index = (uint8_t)((index + 1U) % TELEMETRY_NAV_HEALTH_ITEM_COUNT);
            s_next_navigation_health_us = now_us + TELEMETRY_NAV_HEALTH_PERIOD_US;
        }
        else
        {
            s_navigation_detail_index = (uint8_t)((index + 1U) % TELEMETRY_NAV_DETAIL_ITEM_COUNT);
            s_next_navigation_detail_us = now_us + TELEMETRY_NAV_DETAIL_PERIOD_US;
        }
    }
    return 1U;
}
