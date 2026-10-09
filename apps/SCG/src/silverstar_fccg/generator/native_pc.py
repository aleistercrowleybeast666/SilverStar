"""Private native CDC publication owner; normal generator stays unchanged."""
from silverstar_fccg.generator.ground_pc_usb_cdc import PcUsbCdc_Render
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet


def NativePcAdapter_Render(*, indexed: bool) -> str:
    adapter = PcUsbCdc_Render().replace('#include "pc_byte_stream.h"',
        '#include "pc_byte_stream.h"\n#include "native_runtime.h"\n#include "native_clock.h"', 1)
    marker = '    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||'
    if adapter.count(marker) != 1:
        raise ValueError('Native PC publication gate owner changed')
    adapter = adapter.replace(marker, '    if (NativeRuntime_ReadyGet() == 0U)\n'
        '    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_BUSY; }\n'+marker, 1)
    start, _opening, end = NativeC_FunctionSpanGet(adapter, 'PcByteStream_WriteSession')
    write = adapter[start:end]
    marker = '    saved_mask = __get_PRIMASK();'
    if write.count(marker) != 1:
        raise ValueError('Native PC write context owner changed')
    write = write.replace(marker, '''    /* The native tick must advance before publication. Probe with interrupts
     * enabled; recheck READY/session below after taking the publication lock. */
    if ((NativeRuntime_ReadyGet() == 0U) || (NativeClock_ContextAllowedGet() == 0U))
    { return PC_BYTE_STREAM_WRITE_BUSY; }
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok)
    { return PC_BYTE_STREAM_WRITE_ERROR; }
'''+marker, 1)
    adapter = adapter[:start]+write+adapter[end:]
    if indexed:
        adapter = adapter.replace('hUsbDeviceFS.pClassData', 'hUsbDeviceFS.pClassDataCmsit[0]')
        marker='    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||'
        adapter = adapter.replace(marker,
            '    if ((hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED) &&\n'
            '        ((hUsbDeviceFS.classId != 0U) || (hUsbDeviceFS.pClassDataCmsit[0] == NULL) ||\n'
            '         (hUsbDeviceFS.pClassData != hUsbDeviceFS.pClassDataCmsit[0])))\n'
            '    { NativeRuntime_TransportFaultRecord(); __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_ERROR; }\n'
            +marker, 1)
    return adapter
