from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender
from silverstar_fccg.generator.native_pc import NativePcAdapter_Render


@pytest.mark.parametrize('scenario', ['normal','starting','stopped','masked','irq','session-reset','fault-during-probe'])
@pytest.mark.parametrize('indexed',[False,True])
def test_publication_requires_fresh_unmasked_clock_progress(tmp_path, scenario, indexed):
    compiler = shutil.which('gcc')
    if compiler is None:
        pytest.skip('Host GCC unavailable')
    payload = Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_core_ground_0_1_0/payload'
    for name in ('usb_main.h','usb_device.h','usb_cdc_if.h'):
        (tmp_path/({'usb_main.h':'main.h','usb_device.h':'usb_device.h','usb_cdc_if.h':'usbd_cdc_if.h'}[name])).write_bytes((payload/'Tests/Host'/name).read_bytes())
    if indexed:
        path=tmp_path/'usb_device.h'
        path.write_text(path.read_text().replace('void *pClassData;', 'void *pClassData; void *pClassDataCmsit[1]; uint8_t classId;'))
    (tmp_path/'usbd_conf.h').write_text('/* Host USB config. */\n')
    (tmp_path/'native_clock.h').write_bytes(NativeClock_FilesRender(hclk_hz=72000000)['Generated/Inc/native_clock.h'])
    (tmp_path/'native_runtime.h').write_text('#include <stdint.h>\nuint8_t NativeRuntime_ReadyGet(void);\nvoid NativeRuntime_TransportFaultRecord(void);\n')
    (tmp_path/'adapter.c').write_text(NativePcAdapter_Render(indexed=indexed))
    (tmp_path/'test.c').write_text('''#include "pc_byte_stream.h"
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
''')
    if indexed:
        path=tmp_path/'test.c'
        path.write_text(path.read_text().replace('hUsbDeviceFS.pClassData=&cls;', 'hUsbDeviceFS.pClassData=&cls;hUsbDeviceFS.pClassDataCmsit[0]=&cls;'))
    api = Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    core = Path(__file__).resolve().parents[1]/'plugins/builtin/silverstar_core_0_1_0/payload'
    command = [compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion',
        '-Wsign-conversion','-Wshadow','-Wundef','-Wstrict-prototypes','-Wmissing-prototypes','-fanalyzer',
        '-I'+str(tmp_path),'-I'+str(api),'-I'+str(payload/'Ground/Core/Inc'),
        '-I'+str(payload/'Ground/Protocol/Inc'),'-I'+str(core/'Common/Inc'),
        str(tmp_path/'adapter.c'),str(core/'Common/Src/silverstar_assert.c'),str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')]
    result = subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    result = subprocess.run([str(tmp_path/'test.exe'),scenario],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
