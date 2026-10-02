static void TelemetryService_CommandDispatch(const AirCmdPayload *command)
{
    if (command == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (command->cmd_id == AIR_CMD_CAPABILITY_ACK)
    {
        TelemetryService_CapabilityCommand(command);
        return;
    }
    if (TelemetryService_CachedAckQueue(command) != 0U)
    {
        return;
    }
    if (TelemetryService_CommandIsPendingStart(command) != 0U)
    {
        return;
    }
    if (command->cmd_id == AIR_CMD_PING)
    {
        (void)TelemetryService_AckQueue(command,
            AIR_ACK_RESULT_OK);
        return;
    }
    if ((TelemetryService_IsPreflightState() != 0U) &&
        (s_capability_state != TELEMETRY_CAPABILITY_ACKED))
    {
        (void)TelemetryService_AckQueue(command,
                                  AIR_ACK_RESULT_CAPABILITY_REQUIRED);
        return;
    }

    if ((command->cmd_id >= AIR_CMD_CAL_START) &&
        (command->cmd_id <= AIR_CMD_CAL_RESET))
    {
        TelemetryService_CalibrationCommand(command);
        return;
    }
    if ((command->cmd_id >= AIR_CMD_ALIGN_START) &&
        (command->cmd_id <= AIR_CMD_ALIGN_RESET))
    {
        TelemetryService_AlignmentCommand(command);
        return;
    }

    TelemetryService_MissionCommand(command);
}
