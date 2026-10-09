from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_runtime import NativeRuntime_FilesRender


@pytest.mark.parametrize('scenario', ['normal','clock-init','platform-init','radio-init','pc-init',
    'clock-during-init','clock-before-process','clock-during-process','pc-transient','radio-transient','retirement',
    'unknown-init','unknown-process','usb-retirement','radio-not-initialized','radio-unverified'])
def test_native_lifecycle_prevents_early_and_faulted_publication(tmp_path, scenario):
    compiler=shutil.which('gcc')
    if compiler is None:
        pytest.skip('Host GCC unavailable')
    for path,content in NativeRuntime_FilesRender().items():
        dest=tmp_path/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    headers={
        'native_clock.h':'''#include <stdint.h>
typedef enum { NativeClockResult_Ok, NativeClockResult_Stopped } NativeClockResult;
NativeClockResult NativeClock_StatusGet(void);
NativeClockResult NativeClock_DelayUs(uint32_t delay);
NativeClockResult NativeClock_Read(uint64_t *time);
''',
        'native_platform.h':'''#include "platform_types.h"
PlatformResult NativePlatform_Init(void);
void NativePlatform_Quiesce(void);
''',
        'ground_bridge.h':'''#include <stdint.h>
typedef enum { GROUND_BRIDGE_OK, GROUND_BRIDGE_RADIO_ERROR, GROUND_BRIDGE_PC_ERROR } GroundBridgeResult;
GroundBridgeResult GroundBridge_Init(void);
GroundBridgeResult GroundBridge_Process(uint32_t now_ms);
void GroundBridge_PcReset(void);
''',
        'pc_byte_stream.h':'void PcByteStream_OnUsbReset(void);\n',
        'native_usb_state.h':'''typedef enum { NativeUsbResult_Ok, NativeUsbResult_Failure } NativeUsbResult;
NativeUsbResult NativeUsb_Stop(void);
''',
        'sx1281_device.h':'''#include <stdint.h>
typedef enum { LoraDeactivateResult_Ok, LoraDeactivateResult_PortError } LoraDeactivateResult;
LoraDeactivateResult Lora_Deactivate(uint8_t instance);
typedef enum { LORA_DIAG_RESULT_OK, LORA_DIAG_RESULT_NOT_INIT } LoraDiagResult;
typedef struct { uint16_t firmware_version; uint8_t status_value; uint8_t verified; } LoraChipStatus;
LoraDiagResult Lora_ChipStatusGet(uint8_t instance, LoraChipStatus *status);
''',
        'silverstar_assert.h':'''#include <assert.h>
#define SILVERSTAR_ASSERT_MODULE_GENERATED 1U
#define SILVERSTAR_ASSERT_REASON_STATE_INVARIANT 1U
#define SILVERSTAR_ASSERT(p,m,r) assert(p)
'''}
    for path,content in headers.items():
        (tmp_path/path).write_text(content,encoding='utf-8')
    harness='''#include "native_runtime.h"
#include "native_clock.h"
#include "native_platform.h"
#include "platform_time.h"
#include "ground_bridge.h"
#include "sx1281_device.h"
#include "pc_byte_stream.h"
#include "native_usb_state.h"
#include <assert.h>
#include <string.h>
static NativeClockResult clock_result=NativeClockResult_Ok;
static PlatformResult clock_init=PLATFORM_OK,platform_init=PLATFORM_OK;
static GroundBridgeResult bridge_init=GROUND_BRIDGE_OK,bridge_process=GROUND_BRIDGE_OK;
static uint8_t clock_bad_init,clock_bad_process,retirement_bad,usb_retirement_bad;
static uint8_t radio_not_initialized,radio_unverified;
static uint32_t retired,quiesced,pc_reset,bridge_reset,process_calls,published;
NativeClockResult NativeClock_StatusGet(void) { return clock_result; }
NativeClockResult NativeClock_DelayUs(uint32_t delay) { assert(delay==1U);return clock_result; }
NativeClockResult NativeClock_Read(uint64_t *time)
{ if (clock_result!=NativeClockResult_Ok) { return clock_result; } *time=1234000ULL;return clock_result; }
PlatformResult PlatformTime_Init(void) { return clock_init; }
PlatformResult NativePlatform_Init(void) { return platform_init; }
void NativePlatform_Quiesce(void)
{ assert(retired==(clock_init==PLATFORM_OK && platform_init==PLATFORM_OK ? 1U : 0U));quiesced++; }
LoraDiagResult Lora_ChipStatusGet(uint8_t instance, LoraChipStatus *status)
{
    assert(instance==0U && status!=0 && NativeRuntime_ReadyGet()==0U);
    if (radio_not_initialized!=0U) { return LORA_DIAG_RESULT_NOT_INIT; }
    status->firmware_version=0x1234U;status->status_value=0U;
    status->verified=(uint8_t)(radio_unverified!=0U ? 0U : 1U);
    return LORA_DIAG_RESULT_OK;
}
GroundBridgeResult GroundBridge_Init(void)
{
    /* The real bridge tries to flush its initial STATUS before returning. */
    assert(NativeRuntime_ReadyGet()==0U);
    if (NativeRuntime_ReadyGet()!=0U) { published++; }
    if (clock_bad_init!=0U) { clock_result=NativeClockResult_Stopped; }
    return bridge_init;
}
GroundBridgeResult GroundBridge_Process(uint32_t now_ms)
{
    assert(now_ms==1234U);process_calls++;
    if (clock_bad_process!=0U) { clock_result=NativeClockResult_Stopped; }
    if (NativeRuntime_ReadyGet()!=0U) { published++; }
    return bridge_process;
}
void GroundBridge_PcReset(void) { assert(NativeRuntime_ReadyGet()==0U);bridge_reset++; }
void PcByteStream_OnUsbReset(void) { assert(NativeRuntime_ReadyGet()==0U);pc_reset++; }
NativeUsbResult NativeUsb_Stop(void)
{ assert(NativeRuntime_ReadyGet()==0U);return usb_retirement_bad!=0U ? NativeUsbResult_Failure : NativeUsbResult_Ok; }
LoraDeactivateResult Lora_Deactivate(uint8_t instance)
{ assert(instance==0U && quiesced==0U && NativeRuntime_ReadyGet()==0U);retired++;
  return retirement_bad!=0U ? LoraDeactivateResult_PortError : LoraDeactivateResult_Ok; }
int main(int argc,char **argv)
{
    assert(argc==2);assert(NativeRuntime_ReadyGet()==0U);
    assert(NativeRuntime_Process()==NativeRuntimeResult_NotReady);
    if (strcmp(argv[1],"clock-init")==0) { clock_init=PLATFORM_NOT_READY; }
    if (strcmp(argv[1],"platform-init")==0) { platform_init=PLATFORM_NOT_READY; }
    if (strcmp(argv[1],"radio-init")==0) { bridge_init=GROUND_BRIDGE_RADIO_ERROR; }
    if (strcmp(argv[1],"pc-init")==0) { bridge_init=GROUND_BRIDGE_PC_ERROR; }
    if (strcmp(argv[1],"clock-during-init")==0) { clock_bad_init=1U; }
    if (strcmp(argv[1],"unknown-init")==0) { bridge_init=(GroundBridgeResult)99; }
    if (strcmp(argv[1],"radio-not-initialized")==0) { radio_not_initialized=1U; }
    if (strcmp(argv[1],"radio-unverified")==0) { radio_unverified=1U; }
    NativeRuntimeResult init=NativeRuntime_Init();assert(published==0U);
    if (radio_not_initialized!=0U || radio_unverified!=0U)
    { assert(init==NativeRuntimeResult_RadioFailure); }
    if (init!=NativeRuntimeResult_Ok)
    {
        if (strcmp(argv[1],"unknown-init")==0) { assert(init==NativeRuntimeResult_NotReady); }
        assert(NativeRuntime_ReadyGet()==0U && pc_reset==1U && bridge_reset==1U && quiesced==1U);
        assert(NativeRuntime_Process()==init && process_calls==0U);
        assert(retired==(clock_init==PLATFORM_OK && platform_init==PLATFORM_OK ? 1U : 0U));
        assert(NativeRuntime_Init()==NativeRuntimeResult_NotReady);return 0;
    }
    assert(NativeRuntime_ReadyGet()==1U);
    if (strcmp(argv[1],"clock-before-process")==0) { clock_result=NativeClockResult_Stopped; }
    if (strcmp(argv[1],"clock-during-process")==0) { clock_bad_process=1U; }
    if (strcmp(argv[1],"pc-transient")==0) { bridge_process=GROUND_BRIDGE_PC_ERROR; }
    if (strcmp(argv[1],"radio-transient")==0) { bridge_process=GROUND_BRIDGE_RADIO_ERROR; }
    if (strcmp(argv[1],"retirement")==0) { clock_bad_process=1U;retirement_bad=1U; }
    if (strcmp(argv[1],"usb-retirement")==0) { clock_bad_process=1U;usb_retirement_bad=1U; }
    if (strcmp(argv[1],"unknown-process")==0) { bridge_process=(GroundBridgeResult)99; }
    NativeRuntimeResult result=NativeRuntime_Process();
    if (strcmp(argv[1],"unknown-process")==0)
    {
        assert(result==NativeRuntimeResult_NotReady && NativeRuntime_ReadyGet()==0U);
        assert(retired==1U && quiesced==1U && pc_reset==1U && bridge_reset==1U);
        uint32_t before=process_calls;assert(NativeRuntime_Process()==result && process_calls==before);return 0;
    }
    if (clock_result!=NativeClockResult_Ok)
    {
        assert(result==((retirement_bad!=0U || usb_retirement_bad!=0U) ? NativeRuntimeResult_RetirementFailure : NativeRuntimeResult_ClockFailure));
        assert(NativeRuntime_ReadyGet()==0U && retired==1U && quiesced==1U);
        assert(published==0U && pc_reset==1U && bridge_reset==1U);
        uint32_t before=process_calls;assert(NativeRuntime_Process()==result && process_calls==before);
    }
    else
    {
        assert(NativeRuntime_ReadyGet()==1U && retired==0U && pc_reset==0U && published==1U);
        assert(result==(bridge_process==GROUND_BRIDGE_OK ? NativeRuntimeResult_Ok :
            bridge_process==GROUND_BRIDGE_PC_ERROR ? NativeRuntimeResult_PcFailure : NativeRuntimeResult_RadioFailure));
    }
    return 0;
}
'''
    (tmp_path/'test.c').write_text(harness,encoding='utf-8')
    api=Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion',
        '-Wsign-conversion','-Wshadow','-Wundef','-Wstrict-prototypes','-Wmissing-prototypes','-Wswitch-enum',
        '-fanalyzer','-I'+str(tmp_path),'-I'+str(api),'-I'+str(tmp_path/'Generated/Inc'),
        str(tmp_path/'Generated/Src/native_runtime.c'),str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')]
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    run=subprocess.run([str(tmp_path/'test.exe'),scenario],capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr
