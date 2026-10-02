void TelemetryService_Process(void)
{
    SystemLifecycleState lifecycle_state;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    SystemTelemetry_Process();
    TelemetryService_CapabilityTxPoll();
    TelemetryService_StartResponseProcess();
    TelemetryService_ReceiveProcess();

    lifecycle_state = SystemLifecycle_GetState();
    if (((lifecycle_state == SYSTEM_STATE_FLIGHT) ||
         (lifecycle_state == SYSTEM_STATE_RECOVERY) ||
         (lifecycle_state == SYSTEM_STATE_LANDED) ||
         (lifecycle_state == SYSTEM_STATE_POSTFLIGHT)) &&
        (s_capability_state !=
         TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT))
    {
        TelemetryService_PreflightDisable();
    }

    if (TelemetryService_IsPreflightState() != 0U)
    {
        TelemetryService_SelfTestStateProcess();
        TelemetryService_CalibrationStateProcess();
        TelemetryService_AlignmentStateProcess();
    }
    TelemetryService_GnssStateProcess();
    TelemetryService_PreflightStatusStateProcess();
    TelemetryService_FlightRecoveryStateProcess();
    if (TelemetryService_AckSend() != 0U) { return; }
    if (TelemetryService_SensorSnapshotSend() != 0U) { return; }
    if (TelemetryService_SensorSnapshotTerminalSend() != 0U) { return; }
    if (TelemetryService_StatusSend() != 0U) { return; }
    if ((s_capability_state == TELEMETRY_CAPABILITY_NOT_ACKED) &&
        (TelemetryService_CapabilitySend() != 0U)) { return; }
    if (TelemetryService_PreflightStatusSend() != 0U) { return; }
    if (TelemetryService_CapabilitySend() != 0U) { return; }
    if (TelemetryService_PreflightStateSend() != 0U) { return; }
    if (TelemetryService_NavigationSend() != 0U) { return; }
    TelemetryService_StreamSend();
}
