#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#undef assert
#define assert(c) do { if (!(c)) { fprintf(stderr,"assertion failed at %d: %s\n",__LINE__,#c); exit(1); } } while (0)
#include <stdint.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "platform_critical.h"
#include "platform_stm32f4_resources.h"
static UART_HandleTypeDef handles[6];
static DMA_HandleTypeDef dma[6];
static HAL_StatusTypeDef tx_result = HAL_OK;
static unsigned calls, depth, last_id;
static uint16_t sent_length;
static uint8_t sent[128];
void *PlatformStm32f4Resource_UartHandleGet(PlatformUartId id)
{ return ((unsigned)id < 6U) ? &handles[id] : NULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return depth++; }
void PlatformCritical_Exit(PlatformCriticalState old) { assert(depth == old+1U); depth=old; }
uint8_t PlatformMemory_IsDmaAccessible(const void *p, size_t n) { return p != NULL && n != 0U; }
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_DeInit(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(UART_HandleTypeDef *h,uint8_t *p,uint16_t n)
{ assert(h && p && n); return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit_DMA(UART_HandleTypeDef *h,uint8_t *p,uint16_t n)
{ assert(h && p && n && n<=sizeof(sent)); calls++; last_id=(unsigned)(h-handles); sent_length=n; memcpy(sent,p,n); return tx_result; }
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *h,uint8_t *p,uint16_t n,uint32_t t)
{ (void)t; return HAL_UART_Transmit_DMA(h,p,n); }
HAL_UART_RxEventTypeTypeDef HAL_UARTEx_GetRxEventType(UART_HandleTypeDef *h) { (void)h; return HAL_UART_RXEVENT_IDLE; }
#include "platform_uart_stm32f4.c"
#ifdef UART_SENSOR_TEST
#include "jy901b_device.h"
#include "jy901b_config.h"
#include "neo_m9n_device.h"
static uint32_t now_ms;
uint32_t PlatformTime_Ms(void) { return now_ms; }
uint64_t PlatformTime_Us(void) { return (uint64_t)now_ms * 1000U; }
void PlatformTime_DelayMs(uint32_t delay) { now_ms += delay; }
int main(void)
{
    for (unsigned i=0;i<2;i++) { handles[i].hdmatx=&dma[i]; }
    assert(PlatformUart_Init(PLATFORM_UART_1)==PLATFORM_OK);
    assert(IMU_RegisterReadAsyncStart(0,IMU_REG_RSW)==Jy901bRegisterReadStartResult_Ok);
    assert(calls==1 && last_id==0 && sent_length==5 && sent[0]==0xFF && sent[1]==0xAA);
    HAL_UART_TxCpltCallback(&handles[0]);
    assert(GnssNeoM9n_Init(0)==GnssNeoM9n_InitOk);
    calls=0;
    assert(GnssNeoM9n_ProbeStart(0,921600)==GnssNeoM9nProbeStartResult_Ok);
    now_ms=200;
    assert(GnssNeoM9n_ProbePoll(0)==GnssNeoM9nProbePollResult_Pending);
    assert(GnssNeoM9n_ProbePoll(0)==GnssNeoM9nProbePollResult_Pending);
    assert(calls==1 && last_id==1 && sent_length==8 && sent[0]==0xB5 && sent[1]==0x62);
    HAL_UART_TxCpltCallback(&handles[1]);
    assert(depth==0); return 0;
}
#else
int main(int argc,char **argv)
{
    uint8_t a[5]={0xFF,0xAA,0x27,0x03,0};
    uint8_t b[8]={0xB5,0x62,0x0A,0x04,0,0,0x0E,0x34};
    uint8_t full[256]={0}; uint16_t count, accepted;
    PlatformUartDiagnostics d;
    assert(argc==2);
    unsigned id=(unsigned)(argv[1][0]-'0'); assert(id<6U);
    handles[id].hdmatx=&dma[id];
    assert(PlatformUart_Init((PlatformUartId)id)==PLATFORM_OK);
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,a,5,PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK);
    assert(calls==1 && last_id==id && sent_length==5 && memcmp(sent,a,5)==0);
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,b,8,PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK);
    assert(calls==1); HAL_UART_TxCpltCallback(&handles[id]);
    assert(calls==2 && memcmp(sent,b,8)==0); HAL_UART_TxCpltCallback(&handles[id]);
    assert(PlatformUart_DiagnosticsGet((PlatformUartId)id,&d)==PLATFORM_OK && d.tx_bytes==13 && !d.tx_active);
    tx_result=HAL_BUSY;
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,a,5,PLATFORM_UART_TX_NORMAL)==PLATFORM_OK);
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,b,8,PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK);
    assert(PlatformUart_TxCountGet((PlatformUartId)id,PLATFORM_UART_TX_NORMAL,&count)==PLATFORM_OK && count==5);
    tx_result=HAL_ERROR; PlatformUart_Process((PlatformUartId)id);
    assert(PlatformUart_TxCountGet((PlatformUartId)id,PLATFORM_UART_TX_PRIORITY,&count)==PLATFORM_OK && count==8);
    tx_result=HAL_OK; PlatformUart_Process((PlatformUartId)id);
    assert(memcmp(sent,b,8)==0); HAL_UART_TxCpltCallback(&handles[id]); assert(memcmp(sent,a,5)==0); HAL_UART_TxCpltCallback(&handles[id]);
    uint8_t maximum[136];
    for (unsigned i=0;i<sizeof(maximum);i++) { maximum[i]=(uint8_t)i; }
    tx_result=HAL_OK;
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,maximum,sizeof(maximum),PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK);
    unsigned offset=0;
    while (s_uart[id].tx_active != 0U)
    {
        assert(offset+sent_length<=sizeof(maximum));
        assert(memcmp(sent,maximum+offset,sent_length)==0);
        offset+=sent_length;
        HAL_UART_TxCpltCallback(&handles[id]);
    }
    assert(offset==sizeof(maximum));
    /* A second maximum frame exercises ring wrap as well as the 128-byte chunk. */
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,maximum,sizeof(maximum),PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK);
    offset=0;
    while (s_uart[id].tx_active != 0U)
    {
        assert(offset+sent_length<=sizeof(maximum));
        assert(memcmp(sent,maximum+offset,sent_length)==0);
        offset+=sent_length;
        HAL_UART_TxCpltCallback(&handles[id]);
    }
    assert(offset==sizeof(maximum));
    tx_result=HAL_BUSY;
    unsigned capacity=s_uart[id].tx_priority_size-1U;
    assert(capacity<=1023U);
    for(unsigned i=0;i<capacity;i++) { assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,a,1,PLATFORM_UART_TX_PRIORITY)==PLATFORM_OK); }
    unsigned before=calls;
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,b,8,PLATFORM_UART_TX_PRIORITY)==PLATFORM_BUSY && calls==before);
    assert(PlatformUart_TxCountGet((PlatformUartId)id,PLATFORM_UART_TX_PRIORITY,&count)==PLATFORM_OK && count==capacity);
    assert(PlatformUart_WriteAsync((PlatformUartId)id,full,256,PLATFORM_UART_TX_PRIORITY,&accepted)==PLATFORM_BUSY && accepted==0);
    handles[id].hdmatx=NULL;
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,a,5,PLATFORM_UART_TX_PRIORITY)==PLATFORM_UNSUPPORTED);
    before=calls; PlatformUart_Process((PlatformUartId)id); assert(calls==before);
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)99,a,5,PLATFORM_UART_TX_PRIORITY)==PLATFORM_INVALID_ARGUMENT);
    assert(PlatformUart_WriteFrameAsync((PlatformUartId)id,a,5,(PlatformUartTxPriority)99)==PLATFORM_INVALID_ARGUMENT);
    assert(depth==0); return 0;
}

#endif
