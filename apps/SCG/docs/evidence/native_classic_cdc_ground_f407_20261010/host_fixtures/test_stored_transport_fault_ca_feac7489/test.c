#include "native_runtime.h"
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
static uint8_t transport_bad_init,transport_bad_process;
static uint8_t platform_started;
static uint32_t retired,quiesced,pc_reset,bridge_reset,process_calls,published;
NativeClockResult NativeClock_StatusGet(void) { return clock_result; }
NativeClockResult NativeClock_DelayUs(uint32_t delay) { assert(delay==1U);return clock_result; }
NativeClockResult NativeClock_Read(uint64_t *time)
{ if (clock_result!=NativeClockResult_Ok) { return clock_result; } *time=1234000ULL;return clock_result; }
PlatformResult PlatformTime_Init(void) { return clock_init; }
PlatformResult NativePlatform_Init(void) { if (platform_init==PLATFORM_OK) { platform_started=1U; } return platform_init; }
void NativePlatform_Quiesce(void)
{ assert(retired==(platform_started!=0U ? 1U : 0U));quiesced++; }
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
    if (transport_bad_init!=0U) { NativeRuntime_TransportFaultRecord(); }
    return bridge_init;
}
GroundBridgeResult GroundBridge_Process(uint32_t now_ms)
{
    assert(now_ms==1234U);process_calls++;
    if (transport_bad_process!=0U) { NativeRuntime_TransportFaultRecord(); }
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
    if (strcmp(argv[1],"transport-before-init")==0) { NativeRuntime_TransportFaultRecord(); }
    if (strcmp(argv[1],"transport-during-init")==0) { transport_bad_init=1U; }
    NativeRuntimeResult init=NativeRuntime_Init();
    if (strncmp(argv[1],"transport-",10U)==0 && strstr(argv[1],"init")!=NULL) { assert(init==NativeRuntimeResult_PcFailure); }assert(published==0U);
    if (radio_not_initialized!=0U || radio_unverified!=0U)
    { assert(init==NativeRuntimeResult_RadioFailure); }
    if (init!=NativeRuntimeResult_Ok)
    {
        if (strcmp(argv[1],"unknown-init")==0) { assert(init==NativeRuntimeResult_NotReady); }
        assert(NativeRuntime_ReadyGet()==0U && pc_reset==1U && bridge_reset==1U && quiesced==1U);
        assert(NativeRuntime_Process()==init && process_calls==0U);
        assert(retired==(platform_started!=0U ? 1U : 0U));
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
    if (strcmp(argv[1],"transport-before-process")==0) { NativeRuntime_TransportFaultRecord();assert(NativeRuntime_ReadyGet()==0U); }
    if (strcmp(argv[1],"transport-during-process")==0) { transport_bad_process=1U; }
    NativeRuntimeResult result=NativeRuntime_Process();
    if (strncmp(argv[1],"transport-",10U)==0)
    { assert(result==NativeRuntimeResult_PcFailure && NativeRuntime_ReadyGet()==0U);
      assert(retired==1U && quiesced==1U && pc_reset==1U && bridge_reset==1U);
      uint32_t before=process_calls;assert(NativeRuntime_Process()==result && process_calls==before);return 0; }
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
