#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "host_platform_mock.h"
#include "jy901b_device.h"
#define PlatformUart_Read TestReal_Read
#define PlatformUart_RxCountGet TestReal_CountGet
#include "host_platform_mock.c"
#undef PlatformUart_Read
#undef PlatformUart_RxCountGet
static unsigned read_calls;
static uint64_t read_advance_us;
static uint16_t refill_length;
static PlatformResult read_result=PLATFORM_OK,count_result=PLATFORM_OK;
static uint8_t refill[64];
PlatformResult PlatformUart_Read(PlatformUartId id,uint8_t *data,uint16_t cap,uint16_t *len)
{
    PlatformResult result;
    read_calls++;
    if(read_result!=PLATFORM_OK){*len=0U;return read_result;}
    result=TestReal_Read(id,data,cap,len);
    HostPlatformMock_TimeAdvanceUs(read_advance_us);
    if(refill_length){(void)HostPlatformMock_UartRxInject(id,refill,refill_length);}
    return result;
}
PlatformResult PlatformUart_RxCountGet(PlatformUartId id,uint16_t *count)
{
    return count_result==PLATFORM_OK?TestReal_CountGet(id,count):count_result;
}
/* The production translation unit is compiled against UART boundary faults. */
#include "Devices/IMU/JY901B/Src/jy901b_device.c"
static unsigned checks,failures;
#define CHECK(c) do { checks++; if(!(c)){failures++;printf("FAIL %u: %s\n",(unsigned)__LINE__,#c);} } while(0)
static void Frame(uint8_t type,uint16_t value,uint8_t out[11])
{
    unsigned i;memset(out,0,11U);out[0]=0x55U;out[1]=type;
    out[2]=(uint8_t)value;out[3]=(uint8_t)(value>>8U);
    for(i=0;i<10U;i++){out[10]=(uint8_t)(out[10]+out[i]);}
}
static void BeginAt(uint64_t us)
{
    HostPlatformMock_Reset();memset(s_contexts,0,sizeof(s_contexts));
    read_calls=0U;read_advance_us=0U;refill_length=0U;
    read_result=PLATFORM_OK;count_result=PLATFORM_OK;
    CHECK(IMU_LocalGravitySet(0U,9.80665f)==IMU_OK);
    CHECK(IMU_Init(0U)==IMU_OK);HostPlatformMock_TimeSetUs(us);
    CHECK(IMU_RegisterReadAsyncStart(0U,4U)==Jy901bRegisterReadStartResult_Ok);
}
static void Inject(const uint8_t *bytes,uint16_t length)
{ CHECK(HostPlatformMock_UartRxInject(PLATFORM_UART_1,bytes,length)==length); }
static void Expect(uint16_t expected)
{
    uint16_t value=0x1234U;
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Complete);
    CHECK(value==expected);CHECK(s_contexts[0].register_read_active==0U);
}
static void OwnershipAndOverlap(void)
{
    uint8_t bytes[22];uint16_t value=0x1234U;unsigned split;
    for(split=1U;split<22U;split++)
    {
        BeginAt(109000U);Frame(0x51U,0U,bytes);
        bytes[8]=0x55U;bytes[9]=0x5FU;bytes[10]=0x5AU;
        CHECK(IMU_ReadResponseChecksumValid(bytes)!=0U);
        Frame(0x5FU,7U,&bytes[11]);Inject(bytes,(uint16_t)split);
        IMU_Poll(0U);IMU_Poll(0U);
        CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Pending);
        Inject(&bytes[split],(uint16_t)(22U-split));Expect(7U);
    }
}
static void BadCandidateOverlap(void)
{
    uint8_t bytes[30],frame[11];unsigned prefix;
    Frame(0x5FU,7U,frame);
    for(prefix=1U;prefix<11U;prefix++)
    {
        BeginAt(109000U);memset(bytes,0x33U,sizeof(bytes));bytes[0]=0x55U;
        memcpy(&bytes[prefix],frame,11U);Inject(bytes,(uint16_t)(prefix+11U));Expect(7U);
    }
    BeginAt(109000U);Frame(0x5FU,7U,bytes);bytes[10]^=1U;
    Inject(bytes,11U);
    {uint16_t value=0x1234U;CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Pending);CHECK(value==0x1234U);}
    Inject(frame,11U);Expect(7U);
}
static void StreamAndChunkBoundaries(void)
{
    uint8_t bytes[511],reply[11];unsigned prefix,j;
    Frame(0x5FU,7U,reply);
    for(prefix=0U;prefix<=500U;prefix++)
    {
        BeginAt(109000U);memset(bytes,0x33U,prefix);
        for(j=0U;j+11U<=prefix;j+=11U){Frame((j%22U)?0x52U:0x51U,0U,&bytes[j]);}
        memcpy(&bytes[prefix],reply,11U);
        HostPlatformMock_TimeSetUs(708000U);Inject(bytes,(uint16_t)(prefix+11U));Expect(7U);
        CHECK(read_calls<=8U);
    }
}
static void DeadlinesAndContinuousStream(void)
{
    uint8_t bytes[132],reply[11];uint16_t value=0x1234U,count;unsigned i;
    BeginAt(109000U);HostPlatformMock_TimeSetUs(708000U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Pending);
    HostPlatformMock_TimeSetUs(709000U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);
    CHECK(value==0x1234U);CHECK(read_calls==0U);
    BeginAt(109000U);Frame(0x5FU,7U,reply);
    HostPlatformMock_TimeSetUs(710000U);Inject(reply,11U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);
    CHECK(value==0x1234U);CHECK(read_calls==0U);
    BeginAt(109000U);HostPlatformMock_TimeSetUs(708000U);Inject(reply,11U);
    HostPlatformMock_TimeSetUs(709000U);Expect(7U);
    BeginAt(109000U);HostPlatformMock_TimeSetUs(709000U);
    for(i=0;i<12U;i++){Frame(0x51U,0U,&bytes[i*11U]);}
    Frame(0x52U,0U,refill);refill_length=11U;Inject(bytes,sizeof(bytes));
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);
    CHECK(read_calls==3U);CHECK(TestReal_CountGet(PLATFORM_UART_1,&count)==PLATFORM_OK);CHECK(count==33U);
    BeginAt(109000U);HostPlatformMock_TimeSetUs(708000U);Inject(reply,11U);read_advance_us=2000U;
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);CHECK(value==0x1234U);
    BeginAt(109000U);HostPlatformMock_TimeSetUs(708000U);Inject(bytes,sizeof(bytes));
    refill_length=11U;read_advance_us=2000U;
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_Timeout);CHECK(read_calls==1U);
    /* Existing millisecond deadline arithmetic must also survive tick wrap. */
    BeginAt(((uint64_t)UINT32_MAX-100ULL)*1000ULL);
    HostPlatformMock_TimeAdvanceUs(599000U);Inject(reply,11U);Expect(7U);
}
static void FaultsAndInitialization(void)
{
    uint16_t value=0x1234U;uint8_t frame[11];
    BeginAt(109000U);count_result=PLATFORM_IO_ERROR;
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_IoError);CHECK(value==0x1234U);
    BeginAt(109000U);Frame(0x5FU,7U,frame);Inject(frame,11U);read_result=PLATFORM_IO_ERROR;
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_IoError);CHECK(value==0x1234U);
    CHECK(IMU_RegisterReadAsyncPoll(0U,&value)==Jy901bRegisterReadPollResult_NotReady);
    BeginAt(109000U);CHECK(IMU_RegisterReadAsyncStart(0U,4U)==Jy901bRegisterReadStartResult_Busy);
    Frame(0x5FU,7U,frame);Inject(frame,11U);Expect(7U);
    CHECK(IMU_RegisterReadAsyncStart(0U,4U)==Jy901bRegisterReadStartResult_Ok);
    Frame(0x5FU,6U,frame);Inject(frame,11U);Expect(6U);
}
int main(void)
{
    OwnershipAndOverlap();BadCandidateOverlap();StreamAndChunkBoundaries();
    DeadlinesAndContinuousStream();FaultsAndInitialization();
    printf("actual generated JY register stream: %u checks %u failures\n",checks,failures);
    return failures?1:0;
}
