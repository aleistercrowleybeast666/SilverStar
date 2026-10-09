#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"
#include "native_clock.h"
#include "native_runtime.h"
#include <assert.h>
#include <string.h>
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static USBD_CDC_HandleTypeDef cls;
static uint8_t ready=1U,stopped,in_irq,reset_during_probe,fault_during_probe;
static unsigned tx_calls,probes;
uint8_t NativeClock_ContextAllowedGet(void);
uint8_t NativeRuntime_ReadyGet(void) { return ready; }
void NativeRuntime_TransportFaultRecord(void) { assert(0); }
uint8_t NativeClock_ContextAllowedGet(void) { return (usb_test_mask==0U && in_irq==0U) ? 1U : 0U; }
NativeClockResult NativeClock_DelayUs(uint32_t delay)
{
    assert(delay==1U && usb_test_mask==0U && in_irq==0U);probes++;
    if (reset_during_probe!=0U) { PcByteStream_OnUsbReset(); }
    if (fault_during_probe!=0U) { ready=0U; }
    return stopped!=0U ? NativeClockResult_Stopped : NativeClockResult_Ok;
}
uint8_t CDC_Transmit_FS(uint8_t *data,uint16_t length)
{ assert(usb_test_mask==1U && data!=NULL && length==3U);tx_calls++;return USBD_OK; }
int main(int argc,char **argv)
{
    assert(argc==2);uint8_t bytes[3]={1U,2U,3U};
    hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;hUsbDeviceFS.pClassData=&cls;
    assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK);
    uint32_t session=PcByteStream_Session_Get();
    if (strcmp(argv[1],"starting")==0) { ready=0U; }
    if (strcmp(argv[1],"stopped")==0) { stopped=1U; }
    if (strcmp(argv[1],"masked")==0) { usb_test_mask=1U; }
    if (strcmp(argv[1],"irq")==0) { in_irq=1U; }
    if (strcmp(argv[1],"session-reset")==0) { reset_during_probe=1U; }
    if (strcmp(argv[1],"fault-during-probe")==0) { fault_during_probe=1U; }
    uint32_t mask=usb_test_mask;
    PcByteStreamWriteResult result=PcByteStream_WriteSession(bytes,3U,session);
    assert(usb_test_mask==mask);
    if (strcmp(argv[1],"normal")==0) { assert(result==PC_BYTE_STREAM_WRITE_OK && tx_calls==1U && probes==1U); }
    else { assert(result!=PC_BYTE_STREAM_WRITE_OK && tx_calls==0U); }
    if (ready==0U || mask!=0U || in_irq!=0U) { assert(probes==0U || fault_during_probe!=0U); }
    return 0;
}
