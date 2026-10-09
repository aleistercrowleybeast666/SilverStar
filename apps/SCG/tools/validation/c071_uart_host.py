"""Host fault tests for the actual C071 IT UART/session source and Ground bridge."""
from pathlib import Path
import argparse, subprocess

HEADER = r'''#ifndef __C071_UART_HOST_MAIN_H
#define __C071_UART_HOST_MAIN_H
#include <stdint.h>
typedef enum {HAL_OK=0,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT} HAL_StatusTypeDef;
typedef struct {void *hdmarx;void *hdmatx;} UART_HandleTypeDef;
extern uint32_t test_mask;
void before_mask(void);
void after_restore(void);
static inline uint32_t __get_PRIMASK(void) {before_mask();return test_mask;}
static inline void __disable_irq(void) {test_mask=1U;}
static inline void __set_PRIMASK(uint32_t mask) {test_mask=mask;if(mask==0U)after_restore();}
static inline void __DMB(void) { }
HAL_StatusTypeDef HAL_UART_Abort(UART_HandleTypeDef *uart);
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *uart,uint8_t *data,uint16_t length);
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart,uint8_t *data,uint16_t length);
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart);
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart);
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart);
#endif
'''

MOCKS = r'''#include "main.h"
#include "pc_byte_stream.h"
#include <assert.h>
#include <string.h>
UART_HandleTypeDef huart2;
uint32_t test_mask;
static uint8_t *rx_byte,*tx_retained;
static uint16_t tx_length;
static unsigned aborts,rx_calls,tx_calls;
static HAL_StatusTypeDef abort_status=HAL_OK,rx_status=HAL_OK,tx_status=HAL_OK;
HAL_StatusTypeDef HAL_UART_Abort(UART_HandleTypeDef *uart) {
 assert(uart==&huart2 && test_mask==1U);aborts++;
 if(abort_status==HAL_OK){rx_byte=0;tx_retained=0;}return abort_status;
}
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *uart,uint8_t *data,uint16_t length) {
 assert(uart==&huart2 && data!=0 && length==1U);rx_calls++;
 if(rx_status==HAL_OK){rx_byte=data;}return rx_status;
}
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart,uint8_t *data,uint16_t length) {
 assert(uart==&huart2 && test_mask==1U && data!=0 && length<=70U);tx_calls++;
 if(tx_status==HAL_OK){tx_retained=data;tx_length=length;}return tx_status;
}
static void feed(const uint8_t *data,uint16_t length) {
 for(uint16_t i=0;i<length;i++){assert(rx_byte!=0 && test_mask==0U);*rx_byte=data[i];HAL_UART_RxCpltCallback(&huart2);}
}
'''

TRANSPORT = MOCKS+r'''
void before_mask(void) { }
void after_restore(void) { }
int main(void) {
 uint8_t input[700],output[700];uint32_t old,session,token;unsigned calls;
 UART_HandleTypeDef wrong={0};
 for(uint16_t i=0;i<700U;i++)input[i]=(uint8_t)i;
 abort_status=HAL_ERROR;assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_HARDWARE_ERROR && test_mask==0U);
 abort_status=HAL_OK;rx_status=HAL_ERROR;assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_HARDWARE_ERROR);
 rx_status=HAL_OK;huart2.hdmarx=&wrong;calls=rx_calls;
 assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_HARDWARE_ERROR && rx_calls==calls);huart2.hdmarx=0;
 assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK && rx_byte!=0 && test_mask==0U);
 assert(PcByteStream_ResetPending_Get()==1U && PcByteStream_ResetPending_Get()==0U);
 old=PcByteStream_Session_Get();feed(input,500U);
 assert(PcByteStream_ReadSession(output,490U,&session)==490U && session==old && memcmp(output,input,490U)==0);
 feed(input,500U);assert(PcByteStream_Read(output,700U)==510U);
 assert(memcmp(output,input+490,10U)==0 && memcmp(output+10,input,500U)==0);
 old=PcByteStream_Session_Get();feed(input,512U);
 assert(PcByteStream_OverflowCount_Get()==1U && PcByteStream_Session_Check(old)==0U);
 assert(PcByteStream_Read(output,700U)==0U && PcByteStream_ResetPending_Get()==1U);
 assert(PcByteStream_Write(0,3U)==PC_BYTE_STREAM_WRITE_ERROR && PcByteStream_Write(input,0U)==PC_BYTE_STREAM_WRITE_ERROR);
 assert(PcByteStream_Write(input,71U)==PC_BYTE_STREAM_WRITE_ERROR);
 assert(PcByteStream_Write(input,70U)==PC_BYTE_STREAM_WRITE_OK && tx_length==70U && tx_retained!=input);
 input[0]=99U;calls=tx_calls;
 assert(tx_retained[0]==0U && PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_BUSY && tx_calls==calls && tx_retained[0]==0U);
 HAL_UART_TxCpltCallback(&wrong);assert(PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_BUSY);
 HAL_UART_TxCpltCallback(&huart2);tx_status=HAL_BUSY;
 assert(PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_BUSY);
 tx_status=HAL_ERROR;old=PcByteStream_Session_Get();
 assert(PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_ERROR && PcByteStream_Session_Check(old)==0U);
 tx_status=HAL_OK;assert(PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_OK);
 old=PcByteStream_Session_Get();calls=aborts;HAL_UART_ErrorCallback(&wrong);
 assert(PcByteStream_Session_Check(old)==1U);HAL_UART_ErrorCallback(&huart2);
 assert(PcByteStream_Session_Check(old)==0U && PcByteStream_Write(input,3U)==PC_BYTE_STREAM_WRITE_BUSY && aborts==calls);
 assert(PcByteStream_Read(output,700U)==0U && aborts==calls && tx_retained!=0);
 PcByteStream_Service();
 assert(PcByteStream_Read(output,700U)==0U && aborts==calls+1U && tx_retained==0);
 old=PcByteStream_Session_Get();rx_status=HAL_ERROR;feed(input,1U);
 assert(PcByteStream_Session_Check(old)==0U && PcByteStream_WriteSession(input,3U,old)==PC_BYTE_STREAM_WRITE_BUSY);
 calls=aborts;assert(PcByteStream_ReadSession(output,700U,&session)==0U && test_mask==0U && aborts==calls);
 PcByteStream_Service();assert(aborts==calls+1U);
 rx_status=HAL_OK;PcByteStream_Service();assert(PcByteStream_Read(output,700U)==0U);feed(input,2U);
 assert(PcByteStream_Read(output,700U)==2U && memcmp(output,input,2U)==0);
 old=PcByteStream_Session_Get();test_mask=1U;
 assert(PcByteStream_Session_Enter(old,&token)==1U && token==1U);PcByteStream_Session_Exit(token);
 assert(test_mask==1U);test_mask=0U;
 assert(PcByteStream_Session_Enter(old,0)==0U && PcByteStream_Read(0,1U)==0U);
 HAL_UART_RxCpltCallback(0);HAL_UART_ErrorCallback(0);HAL_UART_TxCpltCallback(0);
 return 0;
}
'''

SESSION = MOCKS+r'''
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
static uint8_t frame[70];static uint16_t frame_len;
static int inject,forwarded,read_error,delivery_error;
void before_mask(void) {
 if(delivery_error==-1){delivery_error=0;HAL_UART_ErrorCallback(&huart2);}
}
void after_restore(void) {
 /* Inject at the final byte, before publication, even with one-byte reads. */
 if(delivery_error>0){delivery_error--;if(delivery_error==0)delivery_error=-1;}
 if(read_error>0){read_error--;if(read_error==0)HAL_UART_ErrorCallback(&huart2);}
}
uint8_t GroundRadio_MetricsSupportedGet(void){return 1U;}
GroundRadioResult GroundRadio_Init(void){return GROUND_RADIO_OK;}
void GroundRadio_Process(void){
 if(inject){inject=0;assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK);feed(frame+5,(uint16_t)(frame_len-5U));}
}
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *p,uint8_t n){
 assert(test_mask==1U && n==2U && p[0]==0x42U && p[1]==0x43U);forwarded++;return GROUND_RADIO_OK;
}
GroundRadioResult GroundRadio_RxDequeue(uint8_t*p,uint8_t*n,int8_t*r,int8_t*s){
 (void)p;(void)n;(void)r;(void)s;return GROUND_RADIO_EMPTY;
}
void GroundRadio_StatsGet(GroundRadioStats*s){memset(s,0,sizeof(*s));}
int main(int argc,char **argv){
 uint8_t payload[]={2,0x42,0x43};tx_status=HAL_BUSY;
 assert(GroundBridge_Init()==GROUND_BRIDGE_OK);
 if(PcByteStream_ResetPending_Get())GroundBridge_PcReset();
 frame_len=GspMin_BuildFrame(GSP_TYPE_AIR_TX,payload,3U,frame,sizeof(frame));
 if(argc>1 && strcmp(argv[1],"normal")==0){feed(frame,frame_len);assert(GroundBridge_Process(1U)==GROUND_BRIDGE_OK);assert(forwarded==1);return 0;}
 if(argc>1 && (strcmp(argv[1],"read-reset")==0 || strcmp(argv[1],"delivery-reset")==0)){
  feed(frame,frame_len);if(strcmp(argv[1],"read-reset")==0)read_error=(int)frame_len;else delivery_error=(int)frame_len;
  assert(GroundBridge_Process(2U)==GROUND_BRIDGE_OK);assert(forwarded==0);return 0;
 }
 feed(frame,5U);assert(GroundBridge_Process(1U)==GROUND_BRIDGE_OK && forwarded==0);
 if(argc>1){assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK);feed(frame+5,(uint16_t)(frame_len-5U));}
 if(argc==1)inject=1;
 assert(GroundBridge_Process(2U)==GROUND_BRIDGE_OK && forwarded==0);return 0;
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',type=Path,nargs='?')
    parser.add_argument('--host-cc',default='gcc')
    args=parser.parse_args()
    root=(args.target or Path(__file__).resolve().parents[1]).resolve()
    build=root/'build/c071-uart-host';build.mkdir(parents=True,exist_ok=True)
    (build/'main.h').write_text(HEADER,encoding='utf-8')
    flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-Wconversion','-Wsign-conversion','-Wshadow','-Wvla']
    flags += ['-I'+str(path) for path in (build,root/'Ground/Core/Inc',root/'Ground/Protocol/Inc',root/'Common/Inc')]
    core=[root/'Generated/Src/pc_byte_stream.c',root/'Common/Src/silverstar_assert.c']
    bridge=[root/'Ground/Core/Src/ground_bridge.c',root/'Ground/Protocol/Src/gsp_min_protocol.c',root/'Ground/Protocol/Src/protocol_crc16.c']
    for name,body,sources in (('transport',TRANSPORT,core),('session',SESSION,core+bridge)):
        harness=build/(name+'.c');harness.write_text(body,encoding='utf-8')
        exe=build/(name+'.exe')
        command=[args.host_cc,*flags,*map(str,sources),str(harness),'-o',str(exe)]
        print('COMMAND',command,flush=True)
        subprocess.run(command,check=True);subprocess.run([str(exe)],check=True)
        if name=='session':
            for scenario in ('control','read-reset','delivery-reset','normal'):
                subprocess.run([str(exe),scenario],check=True)
        print('PASS C071 UART '+name,flush=True)
    from c071_backpressure_host import Run
    Run(root, args.host_cc)
    from c071_recovery_host import Run as Recovery_Run
    Recovery_Run(root, args.host_cc)
    print('HAL/IRQ/radio are Host mocks; UART latency, stack and hardware recovery NOT PROVEN')

if __name__=='__main__':main()
