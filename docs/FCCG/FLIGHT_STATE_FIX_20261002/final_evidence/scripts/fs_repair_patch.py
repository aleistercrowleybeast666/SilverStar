from pathlib import Path
import sys,shutil
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\FlightStateTelemetryHotfix_20261002')
p=repo/'apps/FCCG/plugins/builtin/silverstar_core_0_1_0/payload/Modules/Src/telemetry_service.c'
s=p.read_text(encoding='utf8');assert s.count('static uint64_t s_next_stream_us;')==1
s=s.replace('static uint64_t s_next_stream_us;','static uint64_t s_next_stream_us;\nstatic uint8_t s_stream_send_preferred;')
start=s.index('static uint8_t TelemetryService_NavigationHealthSend(');end=s.index('static uint8_t TelemetryService_NavigationSend(',start)
part=s[start:end];assert part.count('    return 1U;')==1
part=part.replace('        }\n    }\n    return 1U;','        }\n        return 1U;\n    }\n    return 0U;');s=s[:start]+part+s[end:]
start=s.index('static uint8_t TelemetryService_NavigationSend(');end=s.index('static void TelemetryService_StreamSend(',start)
part=s[start:end];assert part.count('        return 1U;')==1
part=part.replace('s_next_navigation_preparation_us = now_us + TELEMETRY_NAV_PREPARATION_PERIOD_US;\n        }\n        return 1U;', 's_next_navigation_preparation_us = now_us + TELEMETRY_NAV_PREPARATION_PERIOD_US;\n            return 1U;\n        }\n        return 0U;');s=s[:start]+part+s[end:]
start=s.index('static void TelemetryService_StreamSend(');end=s.index('SystemDeviceResult TelemetryService_Init(',start)
part=s[start:end].replace('static void TelemetryService_StreamSend','static uint8_t TelemetryService_StreamSend').replace('return;','return 0U;')
part=part.replace('    now_us = SystemTime_GetMonotonicUs();','    now_us = SystemTime_GetMonotonicUs();\n    SILVERSTAR_ASSERT(now_us <= (UINT64_MAX - SYSTEM_TELEMETRY_STREAM_PERIOD_US),\n        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);')
part=part.replace('s_next_stream_us = now_us + SYSTEM_TELEMETRY_STREAM_PERIOD_US;\n    }\n}', 's_next_stream_us = now_us + SYSTEM_TELEMETRY_STREAM_PERIOD_US;\n        return 1U;\n    }\n    return 0U;\n}')
part+='''static void TelemetryService_NormalSend(void)
{
    SILVERSTAR_ASSERT(s_stream_send_preferred <= 1U,
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    /* Retain a class's turn while busy; change preference only after enqueue. */
    if (s_stream_send_preferred != 0U)
    {
        if (TelemetryService_StreamSend() != 0U)
        {
            s_stream_send_preferred = 0U;
            return;
        }
        if (TelemetryService_NavigationSend() != 0U) { s_stream_send_preferred = 1U; }
        return;
    }
    if (TelemetryService_NavigationSend() != 0U)
    {
        s_stream_send_preferred = 1U;
        return;
    }
    if (TelemetryService_StreamSend() != 0U) { s_stream_send_preferred = 0U; }
}

'''
s=s[:start]+part+s[end:]
s=s.replace('    s_next_stream_us = 0ULL;\n    TelemetryService_NavigationReset();','    s_next_stream_us = 0ULL;\n    s_stream_send_preferred = 0U;\n    TelemetryService_NavigationReset();')
assert s.count('    if (TelemetryService_NavigationSend() != 0U) { return; }\n    TelemetryService_StreamSend();')==1
s=s.replace('    if (TelemetryService_NavigationSend() != 0U) { return; }\n    TelemetryService_StreamSend();','    TelemetryService_NormalSend();')
p.write_text(s,encoding='utf8')
fixture=repo/'apps/FCCG/tests/fixtures/flight_state_scheduler_host.c'
shutil.copy2(repo/'.work/fs_counter_evidence/flight_state_scheduler_host_v4.c',fixture)
print(str(p),str(fixture),flush=True)
