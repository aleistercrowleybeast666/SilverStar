"""Execute the actual candidate CDC callback with bounded Host API mocks."""
from pathlib import Path
import argparse, subprocess
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('target',type=Path)
parser.add_argument('--host-cc',default='gcc')
args=parser.parse_args(); root=args.target.resolve()
build=root/'build/callback-host'; build.mkdir(parents=True,exist_ok=True)
(build/'usbd_cdc.h').write_text('''#ifndef __MOCK_USBD_CDC_H
#define __MOCK_USBD_CDC_H
#include <stdint.h>
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
#define CDC_SET_LINE_CODING 0x20U
#define CDC_GET_LINE_CODING 0x21U
typedef struct { uint32_t unused; } USBD_HandleTypeDef;
typedef struct {
int8_t (*Init)(void); int8_t (*DeInit)(void);
int8_t (*Control)(uint8_t,uint8_t*,uint16_t);
int8_t (*Receive)(uint8_t*,uint32_t*);
int8_t (*TransmitCplt)(uint8_t*,uint32_t*,uint8_t);
} USBD_CDC_ItfTypeDef;
extern USBD_CDC_ItfTypeDef USBD_Interface_fops_FS;
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef*,uint8_t*,uint32_t);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef*,uint8_t*);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef*);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef*);
uint8_t CDC_Transmit_FS(uint8_t*,uint16_t);
#endif
''')
(build/'usbd_cdc_if.h').write_text('#include "usbd_cdc.h"\n')
(build/'callback-test.c').write_text('''#include "usbd_cdc_if.h"
#include "pc_byte_stream.h"
#include <assert.h>
#include <string.h>
USBD_HandleTypeDef hUsbDeviceFS;
static unsigned reset_count, received, rearms;
static uint8_t *rx;
static uint8_t fail_tx, fail_rx, transmit_status;
void PcByteStream_OnUsbReset(void) { reset_count++; }
void PcByteStream_OnUsbReceive(const uint8_t *data,uint16_t size) { assert(data!=0); received+=size; }
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *d,uint8_t *p,uint32_t n) { (void)d;(void)p;(void)n;return fail_tx; }
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *d,uint8_t *p) { (void)d; rx=p;return fail_rx; }
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *d) { (void)d;return transmit_status; }
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *d) { (void)d;rearms++;return USBD_OK; }
int main(void)
{
    uint8_t data[65]={0}, line[7]={1,2,3,4,5,6,7}, get[7]={0};
    uint32_t length=3;
    assert(USBD_Interface_fops_FS.Init()==USBD_OK && reset_count==1 && rx!=0);
    assert(USBD_Interface_fops_FS.Receive(data,&length)==USBD_OK && received==3 && rearms==1);
    length=65;
    assert(USBD_Interface_fops_FS.Receive(data,&length)==USBD_FAIL && received==3 && rearms==1);
    assert(USBD_Interface_fops_FS.Receive(data,0)==USBD_FAIL);
    assert(USBD_Interface_fops_FS.Control(CDC_SET_LINE_CODING,line,6)==USBD_FAIL);
    assert(USBD_Interface_fops_FS.Control(CDC_SET_LINE_CODING,line,7)==USBD_OK);
    assert(USBD_Interface_fops_FS.Control(CDC_GET_LINE_CODING,get,7)==USBD_OK && memcmp(line,get,7)==0);
    fail_tx=USBD_FAIL;
    assert(USBD_Interface_fops_FS.Init()==USBD_FAIL && reset_count==2);
    assert(CDC_Transmit_FS(data,3)==USBD_FAIL);
    fail_tx=USBD_OK; transmit_status=USBD_BUSY;
    assert(CDC_Transmit_FS(data,3)==USBD_BUSY);
    fail_rx=USBD_FAIL; length=3;
    assert(USBD_Interface_fops_FS.Receive(data,&length)==USBD_FAIL && rearms==1);
    assert(USBD_Interface_fops_FS.DeInit()==USBD_OK && reset_count==3);
    return 0;
}
''')
source=root/'Platform/STM32C0/Src/usbd_cdc_if.c'
exe=build/'callback-test.exe'
command=[args.host_cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wvla','-I'+str(build),'-I'+str(root/'Ground/Core/Inc'),str(source),str(build/'callback-test.c'),'-o',str(exe)]
subprocess.run(command,check=True)
subprocess.run([str(exe)],check=True)
print('PASS actual C071 CDC callback init/deinit, length bounds, line coding, submit and rearm errors; Host mocks only')
