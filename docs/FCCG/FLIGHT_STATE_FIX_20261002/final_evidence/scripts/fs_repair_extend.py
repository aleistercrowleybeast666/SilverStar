from pathlib import Path
import sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
p=repo/'apps/FCCG/tests/fixtures/flight_state_scheduler_host.c';s=p.read_text(encoding='utf8')
extra='''static void Flight_FairTurns(void)
{
    uint8_t frame[AIR_NAV_CAPABILITY_LEN] = {AIR_TYPE_NAV_HEALTH};
    LoraTxPacket packet;
    Flight_Init();
    for (uint32_t cycle = 0U; cycle < 24U; cycle++)
    {
        Radio_Clock(1000U + cycle * 250U);
        TEST_CHECK(s_stream_send_preferred == 0U);
        TEST_CHECK(SystemTelemetry_Send(frame, sizeof(frame)) == SYSTEM_DEVICE_OK);
        TEST_CHECK(SystemTelemetry_Send(frame, sizeof(frame)) == SYSTEM_DEVICE_OK);
        uint64_t stream_deadline = s_next_stream_us;
        TelemetryService_NormalSend();
        TEST_CHECK(s_stream_send_preferred == 0U);
        TEST_CHECK(s_next_stream_us == stream_deadline);
        TEST_CHECK(s_contexts[0].tx_count == 2U);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
        TelemetryService_NormalSend();
        TEST_CHECK(s_stream_send_preferred == 1U);
        TelemetryService_NormalSend();
        TEST_CHECK(s_stream_send_preferred == 1U);
        TEST_CHECK(s_next_stream_us == stream_deadline);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
        TelemetryService_NormalSend();
        TEST_CHECK(s_stream_send_preferred == 0U);
        TEST_CHECK(s_next_stream_us == s_now_us + SYSTEM_TELEMETRY_STREAM_PERIOD_US);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
        TEST_CHECK(packet.data[0] != AIR_TYPE_FLIGHT_STATE);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
        TEST_CHECK(packet.data[0] == AIR_TYPE_FLIGHT_STATE);
        TEST_CHECK(packet.len == AIR_FLIGHT_STATE_LEN);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) == 0U);
    }
}
static void Flight_Recovery(void)
{
    Flight_Init(); s_lifecycle_state = SYSTEM_STATE_RECOVERY; Flight_Run(1500U);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) > 0U);
}
static void Flight_OutsideMission(void)
{
    LoraTxPacket packet;
    static const SystemLifecycleState states[] = {SYSTEM_STATE_PREFLIGHT,
        SYSTEM_STATE_LANDED, SYSTEM_STATE_POSTFLIGHT, SYSTEM_STATE_FAULT};
    Flight_Init(); s_navigation_session = 0U;
    for (uint8_t i = 0U; i < 4U; i++)
    {
        s_lifecycle_state = states[i]; Radio_Clock(1000U + 250U * i);
        TelemetryService_NormalSend();
        TEST_CHECK(s_contexts[0].tx_count == 0U);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) == 0U);
        TEST_CHECK(s_next_stream_us == 0ULL);
    }
}
'''
s=s.replace('int main(int argc, char **argv)',extra+'\nint main(int argc, char **argv)')
s=s.replace('    else { return 2; }\n    return Test_Finish(argv[1]);', '    else if (strcmp(argv[1], "fair_turns") == 0) { Flight_FairTurns(); }\n    else if (strcmp(argv[1], "recovery") == 0) { Flight_Recovery(); }\n    else if (strcmp(argv[1], "outside_mission") == 0) { Flight_OutsideMission(); }\n    else { return 2; }\n    return Test_Finish(argv[1]);')
p.write_text(s,encoding='utf8')
