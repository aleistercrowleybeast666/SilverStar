from pathlib import Path
import re,sys
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
def remove_function(text,name):
 match=re.search(r'^static [^\n]*\b'+re.escape(name)+r'\(',text,re.M);assert match,name
 start=match.start();brace=text.index('{',start);depth=0
 for end in range(brace,len(text)):
  depth+=(text[end]=='{')-(text[end]=='}')
  if depth==0:break
 return text[:start]+text[end+1:].lstrip('\n')
p=repo/'apps/FCCG/tests/fixtures/flight_state_scheduler_host.c'
s=(repo/'.work/fs_counter_evidence/flight_state_scheduler_host_v4.c').read_text(encoding='utf8')
s=s.replace('static void Flight_Init(void)','static uint8_t s_navigation_request = 1U;\nstatic void Flight_Init(void)')
s=s.replace('    s_lifecycle_state = SYSTEM_STATE_FLIGHT;\n    TelemetryService_PreflightDisable();','    s_capability_state = TELEMETRY_CAPABILITY_ACKED;')
s=s.replace('    s_navigation_session = 1U;\n','')
s=s.replace('    s_next_stream_us = 0ULL;','''    if (s_navigation_request != 0U)
    {
        Test_CommandQueue(20U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
        TEST_CHECK(Lora_RxQueuePush(0U, s_rx[s_rx_tail].data,
            (uint8_t)s_rx[s_rx_tail].length, -60, 3) != 0U);
        s_rx_tail = Test_Next(s_rx_tail, TEST_RX_DEPTH);
        TelemetryService_ReceiveProcess();
    }
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TelemetryService_PreflightDisable();
    s_next_stream_us = 0ULL;''')
s=s.replace('Flight_Init(); s_navigation_session = 0U; Flight_Run(1500U);','s_navigation_request = 0U; Flight_Init(); Flight_Run(1500U);')
for name in ['NAV_HEALTH','NAV_CAPABILITY','NAV_PREPARATION']:
 s=s.replace('Flight_Count(AIR_TYPE_'+name+') > 0U','Flight_Count(AIR_TYPE_'+name+') == 0U')
extra='''static void Flight_Recovery(void)
{
    Flight_Init(); s_lifecycle_state = SYSTEM_STATE_RECOVERY; Flight_Run(1500U);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) == 0U);
}
static void Flight_OutsideMission(void)
{
    LoraTxPacket packet;
    static const SystemLifecycleState states[] = {SYSTEM_STATE_PREFLIGHT,
        SYSTEM_STATE_LANDED, SYSTEM_STATE_POSTFLIGHT, SYSTEM_STATE_FAULT};
    s_navigation_request = 0U; Flight_Init();
    for (uint8_t i = 0U; i < 4U; i++)
    {
        s_lifecycle_state = states[i]; Radio_Clock(1000U + 250U * i);
        TelemetryService_StreamSend();
        TEST_CHECK(s_contexts[0].tx_count == 0U);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) == 0U);
        TEST_CHECK(s_next_stream_us == 0ULL);
    }
}
'''
s=s.replace('int main(int argc, char **argv)',extra+'\nint main(int argc, char **argv)')
s=s.replace('    else { return 2; }\n    return Test_Finish(argv[1]);','    else if (strcmp(argv[1], "recovery") == 0) { Flight_Recovery(); }\n    else if (strcmp(argv[1], "outside_mission") == 0) { Flight_OutsideMission(); }\n    else { return 2; }\n    return Test_Finish(argv[1]);')
p.write_text(s,encoding='utf8')
p=repo/'apps/FCCG/tests/test_flight_state_scheduler_generated_host.py';s=p.read_text(encoding='utf8').replace('"no_imu", "fair_turns", "recovery", "outside_mission"','"no_imu", "recovery", "outside_mission"');p.write_text(s,encoding='utf8')
p=repo/'apps/GSHC/app.py';s=p.read_text(encoding='utf8').replace('self._set_radio_message("radio.start_not_ready")','self._set_radio_message("radio.start_blocked", reason=self._tr("common.not_ready"))');p.write_text(s,encoding='utf8')
p=repo/'apps/GSHC/tests/test_navigation_readiness.py';s=p.read_text(encoding='utf8')
# These retained decoder/state tests simulate archived navigation records directly.
s=s.replace('controller.Navigation_Subscribe()','controller.state.navigation.Navigation_Request(42)')
start=s.index('def test_unsupported_subscribe_does_not_break_base_handshake_or_retry():');end=s.index('\ndef ',start+4)
s=s[:start]+'''def test_release_does_not_offer_navigation_subscription():
    controller = make_controller()
    configure_ready(controller)
    assert not hasattr(controller, "Navigation_Subscribe")
    assert controller.state.start_ready()
    assert not controller.worker.sent

'''+s[end+1:]
start=s.index('def test_local_reprepare_old_generation_cannot_restore_ready():');end=s.index('\n@pytest',start)
s=s[:start]+'''def test_local_reprepare_still_waits_for_real_board_alignment():
    controller = make_controller()
    configure_ready(controller)
    controller.send_align_start()
    assert not controller.state.start_ready()  # The real M0 command is pending.
    assert controller.state.navigation.preparation is None

'''+s[end:]
p.write_text(s,encoding='utf8')
p=repo/'apps/GSHC/tests/test_calibration_capability.py';s=p.read_text(encoding='utf8').replace('# Capability ACK, the one-shot NAV_SUBSCRIBE probe, then CAL_START.','# Capability ACK, then CAL_START; this release does not probe NAV.')
# Only the exact expectation at the automatic subscription test is changed below.
lines=s.splitlines()
for i,line in enumerate(lines):
 if 'this release does not probe NAV' in line:
  for j in range(i+1,min(i+8,len(lines))):
   lines[j]=lines[j].replace('len(controller.worker.sent) == 3','len(controller.worker.sent) == 2')
p.write_text('\n'.join(lines)+'\n',encoding='utf8')
p=repo/'apps/GSHC/tests/test_release_layout.py';s=p.read_text(encoding='utf8')
s=s.replace('window.lbl_flight_pos,window.lbl_mission_parachute,\n                   window.navigation_health_panel.summary,window.navigation_health_panel.toggle','window.lbl_flight_pos,window.lbl_mission_parachute')
s=s.replace('def test_collapsed_navigation_summary_does_not_reserve_blank_chart_space','def test_m0_flight_status_does_not_reserve_navigation_chart_space')
s=s.replace('        panel = window.navigation_health_panel','        assert not hasattr(window, "navigation_health_panel")\n        panel = window.flight_status_scroll')
p.write_text(s,encoding='utf8')
print('M0 release Host and compatibility test edits ready',flush=True)
