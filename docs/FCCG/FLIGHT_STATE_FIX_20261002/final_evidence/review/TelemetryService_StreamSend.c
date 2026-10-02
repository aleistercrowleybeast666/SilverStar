static void TelemetryService_StreamSend(void)
{
    EstimatorOutputSnapshot estimator;
    AirCompactV0ImuQuantized quantized;
    AirFlightStatePayload payload;
    uint8_t frame[AIR_FLIGHT_STATE_LEN];
    uint8_t length = 0U;
    uint8_t index;
    uint64_t now_us;
    SystemLifecycleState state = SystemLifecycle_GetState();

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((state != SYSTEM_STATE_FLIGHT) &&
        (state != SYSTEM_STATE_RECOVERY))
    {
        return;
    }
    now_us = SystemTime_GetMonotonicUs();
    if (now_us < s_next_stream_us) { return; }
    if ((TelemetryService_ImuQuantizedGet(&quantized) == 0U) ||
        (Estimator_GetLatestSnapshot(&estimator) == 0U))
    {
        return;
    }
    (void)memset(&payload, 0, sizeof(payload));
    payload.time_ms = TelemetryService_AirTimeMs();
    for (index = 0U; index < 3U; index++)
    {
        payload.accel_i16[index] = quantized.accel_i16[index];
        payload.gyro_i16[index] = quantized.gyro_i16[index];
        payload.velocity_enu_mps[index] = estimator.velocity_enu_mps[index];
        payload.position_enu_m[index] = estimator.position_enu_m[index];
    }
    for (index = 0U; index < 4U; index++)
    {
        payload.quaternion_q15[index] =
            TelemetryService_QuaternionToQ15(estimator.q_nb[index]);
    }
    if ((Air_FlightStateBuild(s_tx_sequence++, &payload,
            frame, sizeof(frame), &length) == AIR_BUILD_OK) &&
        (SystemTelemetry_Send(frame, length) == SYSTEM_DEVICE_OK))
    {
        s_next_stream_us = now_us + SYSTEM_TELEMETRY_STREAM_PERIOD_US;
    }
}
