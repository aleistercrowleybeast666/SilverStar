"""C071 recovery liveness and per-iteration budget, using the real UART/bridge.

HAL and radio are mocks. No cable-disconnection or MCU timing claim is made.
The same recovery-full case rejects the unchanged pre-fix generated candidate.
"""
from pathlib import Path
import argparse
import subprocess
from c071_uart_host import HEADER, MOCKS

SCENARIOS = ('recovery-full', 'recovery-abort', 'recovery-repeated',
             'recovery-new-error', 'recovery-nonconsuming')

RECOVERY = MOCKS + r'''
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include <stdio.h>
static unsigned radio_pending, forwarded, acknowledgements, inject_error;
static uint32_t tick;
void before_mask(void) { }
void after_restore(void) { }
uint8_t GroundRadio_MetricsSupportedGet(void) { return 1U; }
GroundRadioResult GroundRadio_Init(void) { return GROUND_RADIO_OK; }
void GroundRadio_Process(void) {
 if(inject_error){inject_error=0U;HAL_UART_ErrorCallback(&huart2);}
}
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data,uint8_t length) {
 assert(test_mask==1U && length==1U && data[0]==0x42U);forwarded++;return GROUND_RADIO_OK;
}
GroundRadioResult GroundRadio_RxDequeue(uint8_t *data,uint8_t *length,int8_t *rssi,int8_t *snr) {
 if(!radio_pending)return GROUND_RADIO_EMPTY;
 radio_pending--;data[0]=0x55U;*length=1U;*rssi=-20;*snr=1;return GROUND_RADIO_OK;
}
void GroundRadio_StatsGet(GroundRadioStats *stats) {memset(stats,0,sizeof(*stats));}
static void complete(void) {
 GspMinParser parser;GspMinFrame frame;unsigned frames=0U;
 if(!tx_retained)return;
 GspMinParser_Init(&parser);
 for(uint16_t i=0U;i<tx_length;i++) {
  if(GspMinParser_InputByte(&parser,tx_retained[i],&frame)==GSP_PARSER_FRAME_READY) {
   frames++;
   if(frame.type==GSP_TYPE_ACK) {
    assert(frame.payload[0]==GSP_TYPE_AIR_TX && frame.payload[1]==GSP_ACK_OK);acknowledgements++;
   }
  }
 }
 assert(frames==1U);HAL_UART_TxCpltCallback(&huart2);tx_retained=0;
}
static void process(uint32_t advance) {
 unsigned old_aborts=aborts,old_rx_calls=rx_calls;tick+=advance;
 assert(GroundBridge_Process(tick)==GROUND_BRIDGE_OK);
 assert(aborts-old_aborts<=1U && rx_calls-old_rx_calls<=1U);
}
static unsigned queued(void) {
 GroundBridgeDiagnostics diag;
 assert(GroundBridge_DiagnosticsGet(&diag)==GROUND_BRIDGE_OK);
 return diag.pc_queued_frames;
}
static void drain(void) {
 for(unsigned i=0U;i<40U;i++){complete();process(0U);}
 complete();assert(queued()==0U && acknowledgements==forwarded);
}
static uint16_t command(uint8_t *frame) {
 const uint8_t payload[]={1U,0x42U};
 return GspMin_BuildFrame(GSP_TYPE_AIR_TX,payload,2U,frame,70U);
}
static void full_failure(uint8_t abort_failure) {
 HAL_UART_ErrorCallback(&huart2);radio_pending=4U;
 if(abort_failure){abort_status=HAL_ERROR;}else{rx_status=HAL_BUSY;}
 process(1000U);assert(queued()==4U && tx_retained==0);
}
int main(int argc,char **argv) {
 uint8_t frame[70],byte;uint16_t length=command(frame);uint32_t session;
 unsigned calls,before;assert(argc==2 && length==8U);
 assert(GroundBridge_Init()==GROUND_BRIDGE_OK);complete();
 if(strcmp(argv[1],"recovery-nonconsuming")==0) {
  tx_status=HAL_BUSY;
  for(unsigned i=0U;i<8U;i++)feed(frame,length);
  process(1U);assert(queued()==4U && forwarded==4U);calls=rx_calls;
  for(unsigned i=0U;i<100U;i++)process(1U);
  assert(rx_calls==calls && forwarded==4U);
  tx_status=HAL_OK;drain();assert(forwarded==8U && acknowledgements==8U);
 } else if(strcmp(argv[1],"recovery-repeated")==0) {
  for(unsigned cycle=0U;cycle<8U;cycle++) {
   before=forwarded;feed(frame,5U);process(1U);assert(forwarded==before);
   full_failure(0U);
   rx_status=(cycle%2U)?HAL_ERROR:HAL_BUSY;
   for(unsigned i=0U;i<3U;i++) {
    calls=aborts;process(1U);assert(aborts==calls+1U);
    calls=aborts;
    assert(PcByteStream_ReadSession(&byte,1U,&session)==0U && aborts==calls);
   }
   rx_status=HAL_OK;process(1U);
   feed(frame+5U,(uint16_t)(length-5U));process(1U);assert(forwarded==before);
   feed(frame,length);process(1U);drain();assert(forwarded==before+1U);
  }
 } else if(strcmp(argv[1],"recovery-new-error")==0) {
  HAL_UART_ErrorCallback(&huart2);inject_error=1U;radio_pending=4U;calls=rx_calls;
  process(1000U);assert(rx_calls==calls+1U && queued()==4U && tx_retained==0);
  calls=rx_calls;process(1U);assert(rx_calls==calls+1U);drain();
  feed(frame,length);process(1U);drain();assert(forwarded==1U);
 } else {
  assert(strcmp(argv[1],"recovery-full")==0 || strcmp(argv[1],"recovery-abort")==0);
  full_failure((uint8_t)(strcmp(argv[1],"recovery-abort")==0));
  calls=rx_calls;abort_status=HAL_OK;rx_status=HAL_OK;
  process(1U);
  /* Recovery is required despite a full ACK queue; no explicit read/init. */
  assert(rx_calls==calls+1U);drain();
  for(unsigned i=0U;i<5U;i++)feed(frame,length);
  process(1U);drain();assert(forwarded==5U && acknowledgements==5U);
 }
 printf("PASS %s: bounded recovery, command ACKs and session isolation\n",argv[1]);
 return 0;
}
'''


def Run(root, host_cc):
    root = Path(root)
    build = root/'build/c071-recovery-host'
    build.mkdir(parents=True, exist_ok=True)
    (build/'main.h').write_text(HEADER, encoding='utf-8')
    harness = build/'recovery.c'
    harness.write_text(RECOVERY, encoding='utf-8')
    includes = (build, root/'Ground/Core/Inc', root/'Ground/Protocol/Inc', root/'Common/Inc')
    sources = ('Generated/Src/pc_byte_stream.c', 'Common/Src/silverstar_assert.c',
               'Ground/Core/Src/ground_bridge.c', 'Ground/Protocol/Src/gsp_min_protocol.c',
               'Ground/Protocol/Src/protocol_crc16.c')
    exe = build/'recovery.exe'
    command = [host_cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion',
               '-Wsign-conversion', '-Wshadow', '-Wvla', *['-I'+str(p) for p in includes],
               *[str(root/p) for p in sources], str(harness), '-o', str(exe)]
    print('COMMAND', command, flush=True)
    subprocess.run(command, check=True)
    for scenario in SCENARIOS:
        subprocess.run([str(exe), scenario], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--host-cc', default='gcc')
    args = parser.parse_args()
    Run(args.target, args.host_cc)
