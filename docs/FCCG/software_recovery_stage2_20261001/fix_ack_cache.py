from pathlib import Path
root = Path(__file__).resolve().parents[2]
p = root / 'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Modules/Src/telemetry_service.c'
s = p.read_text(encoding='utf-8')
s = s.replace('    uint8_t command_sequence;\n    uint8_t command_id;\n    uint8_t valid;\n} TelemetryAckCacheEntry;', '    AirCmdPayload command;\n    uint64_t recorded_us;\n    uint8_t valid;\n} TelemetryAckCacheEntry;')
s = s.replace('static uint8_t s_start_cmd_sequence;', 'static uint8_t s_start_cmd_sequence;\nstatic AirCmdPayload s_start_command;\nstatic uint8_t s_capability_ack_known;\nstatic uint8_t s_capability_ack_sequence;')
start = s.index('static uint8_t TelemetryService_CachedAckQueue(')
end = s.index('static uint8_t TelemetryService_StatusQueueAt(', start)
s = s[:start] + '''/* Exact wire fields, not struct padding, identify an idempotent retry. */
static uint8_t TelemetryService_CommandEqual(const AirCmdPayload *left,
                                              const AirCmdPayload *right)
{
    SILVERSTAR_ASSERT_OBJECT(left, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    SILVERSTAR_ASSERT_OBJECT(right, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    return (uint8_t)((left->seq == right->seq) &&
        (left->cmd_id == right->cmd_id) && (left->token == right->token) &&
        (left->param0 == right->param0) && (left->param1 == right->param1));
}

static uint8_t TelemetryService_CachedAckQueue(const AirCmdPayload *command)
{
    uint8_t index;
    uint64_t now_us = SystemTime_GetMonotonicUs();

    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    for (index = 0U; index < TELEMETRY_ACK_CACHE_DEPTH; index++)
    {
        TelemetryAckCacheEntry *entry = &s_ack_cache[index];
        /* GSHC's existing four attempts span 3.2 seconds. Bound reuse even if
         * the 8-bit sequence wraps without a new Capability handshake. */
        if ((entry->valid != 0U) &&
            ((now_us - entry->recorded_us) >= 4000000ULL))
        { entry->valid = 0U; }
        if ((entry->valid != 0U) &&
            (TelemetryService_CommandEqual(&entry->command, command) != 0U))
        {
            /* A full ACK queue drops this retry, not the idempotence record.
             * Re-executing the command here would duplicate its side effects. */
            if (TelemetryService_AckFrameQueue(entry->frame) == 0U) { return 1U; }
            return 1U;
        }
    }
    return 0U;
}

''' + s[end:]
start = s.index('static uint8_t TelemetryService_AckQueue(')
end = s.index('static AirAckResult TelemetryService_DeviceResultMap(', start)
s = s[:start] + '''static uint8_t TelemetryService_AckRawQueue(uint8_t command_sequence,
                                            uint8_t command_id,
                                            AirAckResult result,
                                            const AirCmdPayload *command)
{
    uint8_t frame[AIR_ACK_LEN];
    uint8_t length = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (Air_AckBuild(s_tx_sequence++, command_sequence, command_id,
                     (uint8_t)result, TelemetryService_AirTimeMs(),
                     frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        s_diagnostics.ack_queue_failure_count++;
        return 0U;
    }
    if (command != NULL)
    {
        SILVERSTAR_ASSERT(s_ack_cache_next < TELEMETRY_ACK_CACHE_DEPTH,
            SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        (void)memcpy(s_ack_cache[s_ack_cache_next].frame, frame, AIR_ACK_LEN);
        s_ack_cache[s_ack_cache_next].command = *command;
        s_ack_cache[s_ack_cache_next].recorded_us = SystemTime_GetMonotonicUs();
        s_ack_cache[s_ack_cache_next].valid = 1U;
        s_ack_cache_next = TelemetryService_AckCacheNext(s_ack_cache_next);
    }
    return TelemetryService_AckFrameQueue(frame);
}

static uint8_t TelemetryService_AckQueue(const AirCmdPayload *command,
                                         AirAckResult result)
{
    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    return TelemetryService_AckRawQueue(command->seq, command->cmd_id, result, command);
}

''' + s[end:]
s=s.replace('TelemetryService_AckQueue(command->seq, command->cmd_id,', 'TelemetryService_AckQueue(command,')
s=s.replace('TelemetryService_AckQueue(s_start_cmd_sequence,\n                AIR_CMD_START_MISSION, ack_result)', 'TelemetryService_AckQueue(&s_start_command, ack_result)')
s=s.replace('TelemetryService_AckQueue(frame[1], frame[2], ack_result)', 'TelemetryService_AckRawQueue(frame[1], frame[2], ack_result, NULL)')
s=s.replace('    s_start_cmd_sequence = command->seq;', '    s_start_cmd_sequence = command->seq;\n    s_start_command = *command;')
s=s.replace('        (command->seq == s_start_cmd_sequence) &&\n        (command->cmd_id == AIR_CMD_START_MISSION)', '        (TelemetryService_CommandEqual(command, &s_start_command) != 0U)')
s=s.replace('    s_capability_state = TELEMETRY_CAPABILITY_ACKED;', '''    if ((s_capability_ack_known == 0U) ||
        (s_capability_ack_sequence != command->param0))
    {
        /* A newly validated handshake invalidates prior-session business ACKs.
         * CAPABILITY_ACK itself always validates the current advertised frame. */
        (void)memset(s_ack_cache, 0, sizeof(s_ack_cache));
        s_capability_ack_sequence = command->param0;
        s_capability_ack_known = 1U;
    }
    s_capability_state = TELEMETRY_CAPABILITY_ACKED;''')
block='''    if (command->cmd_id == AIR_CMD_CAPABILITY_ACK)
    {
        TelemetryService_CapabilityCommand(command);
        return;
    }
'''
s=s.replace(block, '')
needle='    if (TelemetryService_CachedAckQueue(command->seq, command->cmd_id) != 0U)'
s=s.replace(needle, block + '    if (TelemetryService_CachedAckQueue(command) != 0U)')
s=s.replace('    s_ack_cache_next = 0U;', '    s_ack_cache_next = 0U;\n    s_capability_ack_known = 0U;\n    s_capability_ack_sequence = 0U;\n    (void)memset(&s_start_command, 0, sizeof(s_start_command));')
p.write_text(s, encoding='utf-8')
