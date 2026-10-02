static void Flight_Init(void)
{
    Radio_Init();
    s_over_air_count = 0U;
    s_simulated_tx_end_ms = 0U;
    s_estimator_available = 1U;
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TelemetryService_PreflightDisable();
    s_gnss_state_known = 1U;
    s_gnss_position_usable = 0U;
    s_navigation_session = 1U;
    s_navigation_preparation.algorithm_id = 1U;
    s_next_stream_us = 0ULL;
}
static unsigned int Flight_Count(uint8_t type)
{
    unsigned int count = 0U;
    for (uint8_t i = 0U; i < s_over_air_count; i++)
    { if (s_over_air[i].data[0] == type) { count++; } }
    return count;
}
static void Flight_Run(uint32_t end_ms)
{
    for (uint32_t ms = 1U; ms <= end_ms; ms++)
    {
        Radio_Clock(ms);
        if ((s_simulated_tx_end_ms != 0U) && (ms >= s_simulated_tx_end_ms))
        { s_simulated_tx_end_ms = 0U; s_raw_irq = IRQ_TX_DONE; s_dio1_pending = 1U; }
        TelemetryService_Process();
        TEST_CHECK(s_contexts[0].tx_normal_count <= 2U);
        TEST_CHECK(s_contexts[0].tx_count <= 8U);
    }
}
static void Flight_Contended(void)
{
    Flight_Init(); Flight_Run(14005U);
    printf("CONTENDED ms=14005 FLIGHT=%u NAV_HEALTH=%u NAV_CAP=%u NAV_PREP=%u queued=%u stream_deadline=%llu\n",
        Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH),
        Flight_Count(AIR_TYPE_NAV_CAPABILITY), Flight_Count(AIR_TYPE_NAV_PREPARATION),
        s_contexts[0].tx_count, (unsigned long long)s_next_stream_us);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_CAPABILITY) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_PREPARATION) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
    for (uint8_t i = 0U; i < s_over_air_count; i++)
    {
        if (s_over_air[i].data[0] != AIR_TYPE_FLIGHT_STATE) { continue; }
        TEST_CHECK(s_over_air[i].length == AIR_FLIGHT_STATE_LEN);
        printf("FLIGHT_HEX ");
        for (uint8_t j = 0U; j < s_over_air[i].length; j++) { printf("%02x", s_over_air[i].data[j]); }
        printf("\n");
    }
}
static void Flight_NoNavigation(void)
{
    Flight_Init(); s_navigation_session = 0U; Flight_Run(1500U);
    printf("NO_NAV FLIGHT=%u GNSS_USABLE=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), s_gnss_position_usable);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
}
static void Flight_Unavailable(void)
{
    Flight_Init(); s_estimator_available = 0U; Flight_Run(1500U);
    printf("NO_ESTIMATOR FLIGHT=%u NAV=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH));
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) > 0U);
    Flight_Init(); s_imu_sample.valid_mask = 0U; Flight_Run(1500U);
    printf("NO_IMU FLIGHT=%u NAV=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH));
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) > 0U);
}
int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    if (strcmp(argv[1], "contended") == 0) { Flight_Contended(); }
    else if (strcmp(argv[1], "no_navigation") == 0) { Flight_NoNavigation(); }
    else if (strcmp(argv[1], "unavailable") == 0) { Flight_Unavailable(); }
    else { return 2; }
    return Test_Finish(argv[1]);
}
