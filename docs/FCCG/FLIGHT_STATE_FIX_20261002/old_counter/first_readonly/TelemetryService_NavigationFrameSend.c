static uint8_t TelemetryService_NavigationFrameSend(uint8_t type,
    const AirNavigationStatusPayload *payload)
{
    uint8_t frame[AIR_NAV_CAPABILITY_LEN];
    uint8_t length = 0U;

    if (Air_NavigationStatusBuild(s_tx_sequence, type, payload, frame,
            sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_Send(frame, length) != SYSTEM_DEVICE_OK) { return 0U; }
    s_tx_sequence++;
    return 1U;
}
