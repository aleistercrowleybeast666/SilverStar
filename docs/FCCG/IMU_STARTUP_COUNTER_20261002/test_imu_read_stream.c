#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "host_platform_mock.h"
#include "jy901b_device.h"
/* Actual generated translation unit; no private-state replacement. */
#include "Devices/IMU/JY901B/Src/jy901b_device.c"
static unsigned checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("FAIL line %u: %s\n", (unsigned)__LINE__, #c); } } while (0)
static void Frame(uint8_t type, uint16_t value, uint8_t out[11])
{
    unsigned i;
    memset(out, 0, 11U);out[0]=0x55U;out[1]=type;
    out[2]=(uint8_t)value;out[3]=(uint8_t)(value>>8U);
    for(i=0;i<10U;i++){out[10]=(uint8_t)(out[10]+out[i]);}
}
static void Begin(void)
{
    HostPlatformMock_Reset();
    /* MCU BSS boot fixture, so each scenario has no previous reply bytes. */
    memset(s_contexts,0,sizeof(s_contexts));IMU_Reset(0U);
    CHECK(IMU_LocalGravitySet(0U,9.80665f)==IMU_OK);
    CHECK(IMU_Init(0U)==IMU_OK);
    HostPlatformMock_TimeSetUs(109000U);
    CHECK(IMU_RegisterReadAsyncStart(0U,0x04U)==Jy901bRegisterReadStartResult_Ok);
}
static void Ownership(void)
{
    uint8_t frame[11];uint16_t value=0;
    Begin();Frame(0x5FU,7U,frame);
    CHECK(HostPlatformMock_UartRxInject(PLATFORM_UART_1,frame,11U)==11U);
    IMU_Poll(0U);IMU_Poll(0U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Complete);
    CHECK(value==7U);
    printf("normal-reader isolation checked\n");
}
static void PayloadOverlap(void)
{
    uint8_t bytes[22];uint16_t value=0;
    Begin();Frame(0x51U,0U,bytes);
    /* Legal acceleration payload ends with 55 5F; recompute its checksum. */
    bytes[8]=0x55U;bytes[9]=0x5FU;bytes[10]=0x5AU;
    CHECK(IMU_ReadResponseChecksumValid(bytes)!=0U);
    Frame(0x5FU,7U,&bytes[11]);
    CHECK(HostPlatformMock_UartRxInject(PLATFORM_UART_1,bytes,22U)==22U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Complete);
    CHECK(value==7U);
    printf("payload overlap retained frame1=%02x index=%u active=%u\n",s_contexts[0].register_read_frame[1],s_contexts[0].register_read_index,s_contexts[0].register_read_active);
}
static void DeadlineBacklog(void)
{
    uint8_t bytes[143];uint16_t value=0;unsigned i;
    Jy901bRegisterReadPollResult result;
    Begin();
    for(i=0;i<12U;i++){Frame(0x51U,0U,&bytes[i*11U]);}
    Frame(0x5FU,7U,&bytes[132]);
    /* 143 <= real UART1 usable capacity 511. Reply queued before deadline. */
    HostPlatformMock_TimeSetUs(708000U);
    CHECK(HostPlatformMock_UartRxInject(PLATFORM_UART_1,bytes,sizeof(bytes))==sizeof(bytes));
    result=IMU_RegisterReadAsyncPoll(0U,&value);
    CHECK(result!=Jy901bRegisterReadPollResult_Timeout);
    HostPlatformMock_TimeSetUs(709000U);
    if(result==Jy901bRegisterReadPollResult_Pending){result=IMU_RegisterReadAsyncPoll(0U,&value);}
    CHECK(result==Jy901bRegisterReadPollResult_Complete);
    CHECK(value==7U);
    printf("deadline backlog retained frame1=%02x index=%u active=%u\n",s_contexts[0].register_read_frame[1],s_contexts[0].register_read_index,s_contexts[0].register_read_active);
}
static void NoReply(void)
{
    uint16_t value=0x1234U;
    Begin();HostPlatformMock_TimeSetUs(708000U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Pending);
    HostPlatformMock_TimeSetUs(709000U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);
    CHECK(value==0x1234U);
}
int main(void)
{
    Ownership();PayloadOverlap();DeadlineBacklog();NoReply();
    printf("actual generated JY read: %u checks %u failures\n",checks,failures);
    return failures?1:0;
}
