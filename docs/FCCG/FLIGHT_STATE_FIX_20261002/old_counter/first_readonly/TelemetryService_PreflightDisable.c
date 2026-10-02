static void TelemetryService_PreflightDisable(void)
{
    s_capability_state = TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT;
    s_capability_send_pending = 0U;
    s_next_capability_us = 0ULL;
    s_preflight_status_send_pending = 0U;
    s_preflight_status_known = 0U;
    s_next_preflight_status_us = 0ULL;
    s_next_preflight_state_us = 0ULL;
    s_sensor_snapshot_active = 0U;
    s_sensor_snapshot_terminal_pending = 0U;
}
