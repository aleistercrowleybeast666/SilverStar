from pathlib import Path
import re,subprocess,sys,shutil
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
git=['git','-c','core.longpaths=true','-c','safe.directory='+repo.as_posix(),'-C',str(repo)]
relative='apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Modules/Src/telemetry_service.c'
p=repo/relative
saved=repo/'.work/fairness_proposal';saved.mkdir(exist_ok=False)
shutil.copy2(p,saved/'telemetry_service.c')
shutil.copy2(repo/'apps/FCCG/tests/fixtures/flight_state_scheduler_host.c',saved/'flight_state_scheduler_host.c')
shutil.copy2(repo/'apps/FCCG/tests/test_flight_state_scheduler_generated_host.py',saved/'test_flight_state_scheduler_generated_host.py')
s=subprocess.check_output(git+['show','9931b397de9b7ce0d58f3a743d0d3ea5460e5b1d:'+relative],text=True,encoding='utf8')
def remove_function(text,name):
 match=re.search(r'^static [^\n]*\b'+re.escape(name)+r'\(',text,re.M)
 assert match,name
 start=match.start();brace=text.index('{',start);depth=0
 for end in range(brace,len(text)):
  depth+=(text[end]=='{')-(text[end]=='}')
  if depth==0: break
 return text[:start]+text[end+1:].lstrip('\n')
functions=['TelemetryService_NavigationReset','TelemetryService_NavigationSubscribe','TelemetryService_NavigationPreparationGet','TelemetryService_NavigationFrameSend','TelemetryService_NavigationAge','TelemetryService_NavigationValue','TelemetryService_NavigationGnssMetric','TelemetryService_NavigationImuGeneration','TelemetryService_NavigationImuMetric','TelemetryService_NavigationLoggerMetric','TelemetryService_NavigationSystemMetric','TelemetryService_NavigationHistoryMetric','TelemetryService_NavigationMetricGet','TelemetryService_NavigationHealthSend','TelemetryService_NavigationSend']
for name in functions:s=remove_function(s,name)
s=re.sub(r'^#define TELEMETRY_NAV_.*\n','',s,flags=re.M)
s=re.sub(r'^static [^\n]+ s_(?:navigation\w*|next_navigation\w*);\n','',s,flags=re.M)
block='''    if (command->cmd_id == AIR_CMD_NAV_SUBSCRIBE)
    {
        /* A new subscriber nonce must not be swallowed by the old seq/id ACK cache. */
        TelemetryService_NavigationSubscribe(command);
        return;
    }
'''
assert s.count(block)==1;s=s.replace(block,'')
assert s.count('    TelemetryService_NavigationReset();')==1;s=s.replace('    TelemetryService_NavigationReset();\n','')
assert s.count('    if (TelemetryService_NavigationSend() != 0U) { return; }')==1;s=s.replace('    if (TelemetryService_NavigationSend() != 0U) { return; }\n','')
p.write_text(s,encoding='utf8')
# Retain board START admission, internal preparation/generation and protocol decode compatibility.
p=repo/'apps/GSHC/app.py';s=p.read_text(encoding='utf8')
assert s.count('        self.Navigation_Subscribe()')==1;s=s.replace('        self.Navigation_Subscribe()\n','')
start=s.index('    def Navigation_Subscribe(self)');end=s.index('    def _check_air_cmd_timeouts(',start);s=s[:start]+s[end:]
s=s.replace('    TOKEN_NAV_SUBSCRIBE,\n','')
assert 'secrets.' not in s;s=s.replace('import secrets\n','')
s=s.replace('self._set_radio_message("navigation.start_blocked")','self._set_radio_message("radio.start_not_ready")')
s=s.replace('detail="navigation readiness expired"','detail="M0 board prerequisites expired"')
block='''        if cmd_id in {int(AirCmdId.CAL_START), int(AirCmdId.CAL_FACE), int(AirCmdId.CAL_RESET),
                      int(AirCmdId.ALIGN_START), int(AirCmdId.ALIGN_STOP), int(AirCmdId.ALIGN_RESET)}:
            self.state.navigation.Navigation_Invalidate("WAITING")
            self.state.navigation.awaiting_generation = True
'''
assert s.count(block)==1;s=s.replace(block,'')
p.write_text(s,encoding='utf8')
p=repo/'apps/GSHC/ui/main_window.py';s=p.read_text(encoding='utf8')
for block in ['from ui.navigation_panel import NavigationPanel\n','        self.navigation_preparation_panel = NavigationPanel(self.i18n, preflight=True)\n','        # Preserve the monitoring rows from the pre-navigation GSHC layout.\n','        # Supplemental preparation diagnostics must not displace the original\n        # status, commands and event monitoring rows.\n        root.addWidget(self.navigation_preparation_panel)\n','        self.navigation_health_panel = NavigationPanel(self.i18n, preflight=False)\n        status_layout.addWidget(self.navigation_health_panel)\n','        self.navigation_preparation_panel.Navigation_Render(state)\n        self.navigation_health_panel.Navigation_Render(state)\n']:
 assert s.count(block)==1,block;s=s.replace(block,'')
p.write_text(s,encoding='utf8')
# Update the owning generated Host regression to the explicitly changed release contract.
p=repo/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Tests/Host/test_telemetry.c';s=p.read_text(encoding='utf8')
for name in ['Test_NavigationSubscription','Test_NavigationHealth','Test_NavigationDetails']:
 s=remove_function(s,name)
 s=s.replace('    '+name+'();\n','')
new='''static void Test_NavigationDeferred(void)
{
    const TestFrame *frame;
    Test_Reset();
    Test_CommandQueue(20U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    TelemetryService_Process();
    frame = Test_AckGet(20U, AIR_CMD_NAV_SUBSCRIBE);
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return; }
    TEST_CHECK(frame->data[4] == AIR_ACK_RESULT_BAD_CMD);
    Test_Authorize();
    s_navigation_preparation.generation = 7U;
    s_navigation_preparation.algorithm_id = 2U;
    s_navigation_preparation.initialized = 1U;
    Test_CommandQueue(21U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    for (uint8_t index = 0U; index < 32U; index++)
    {
        TelemetryService_Process();
        s_now_us += 20000ULL;
    }
    frame = Test_AckGet(21U, AIR_CMD_NAV_SUBSCRIBE);
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return; }
    TEST_CHECK(frame->data[4] == AIR_ACK_RESULT_BAD_CMD);
    TEST_CHECK(s_navigation_preparation.generation == 7U);
    TEST_CHECK(s_navigation_preparation.initialized == 1U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_NAV_CAPABILITY) == 0U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_NAV_PREPARATION) == 0U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_NAV_HEALTH) == 0U);
}

'''
s=s.replace('int main(void)',new+'int main(void)')
s=s.replace('    return Test_Finish("telemetry");','    Test_NavigationDeferred();\n    return Test_Finish("telemetry");')
p.write_text(s,encoding='utf8')
print('M0 owner patch complete; source/test diff ready',flush=True)
