#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nrf24_device.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "project_resources.h"
#include "silverstar_assert.h"
#include "air_protocol.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"

static uint64_t s_us;
static uint8_t s_registers[32][5];
static uint8_t s_ce;
static uint64_t s_ce_since;
static uint8_t s_csn = 1U;
static uint8_t s_rx[3][32];
static uint8_t s_rx_lengths[3];
static uint8_t s_rx_count;
static uint8_t s_fail;
static uint8_t s_gpio_fail;
static uint8_t s_absent;
static uint8_t s_max_rt;
static uint8_t s_suppress_tx;
static uint32_t s_delay_tx_us;
static uint64_t s_tx_due_us;
static uint8_t s_delayed_pending;
static uint8_t s_locked_feature;
static uint8_t s_activate_count;
static uint8_t s_tx_present;
static uint8_t s_tx_packet[32];
static uint8_t s_tx_length;
static uint32_t s_flush_tx;
static uint32_t s_spi_calls;
static uint8_t s_wire[512][32];
static uint8_t s_wire_lengths[512];
static uint16_t s_wire_count;
static uint8_t s_inject_fault_send;
static Nrf24Result s_injected_result;

uint32_t PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(uint32_t lock)
{
    (void)lock;
    if (s_inject_fault_send != 0U)
    {
        const uint8_t command[9] = {0x30U};
        s_inject_fault_send = 0U;
        s_injected_result = Nrf24_Send(0U,command,9U,1U,NULL);
    }
}
uint64_t PlatformTime_Us(void) { return s_us; }
uint32_t PlatformTime_Ms(void) { return (uint32_t)(s_us / 1000ULL); }
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{ if (condition == 0U) { fprintf(stderr, "ASSERT %u %u %s:%u\n", module, reason, file, line); abort(); } }

void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module, const char *file, uint32_t line)
{
    SilverStarAssert_Check((uint8_t)(object != NULL),module,file,line,SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SilverStarAssert_Check((uint8_t)(alignment != 0U && ((uintptr_t)object % alignment) == 0U),
        module,file,line,SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

SystemDeviceResult ProjectNrf24Resources_Get(uint8_t instance, ProjectNrf24Resources *resources)
{
    if (instance != 0U || resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    resources->spi = PLATFORM_SPI_1; resources->csn = PLATFORM_GPIO_0;
    resources->ce = PLATFORM_GPIO_1; resources->time = PLATFORM_TIME_1;
    return SYSTEM_DEVICE_OK;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    if (s_gpio_fail != 0U) { return PLATFORM_IO_ERROR; }
    if (id == PLATFORM_GPIO_0) { s_csn = high; }
    else if (id == PLATFORM_GPIO_1)
    {
        if (high != 0U && s_ce == 0U) { s_ce_since = s_us; }
        if (high == 0U && s_ce != 0U && s_tx_present != 0U)
        {
            assert(s_us - s_ce_since >= 15ULL);
            if (s_delay_tx_us != 0U)
            { s_tx_due_us = s_ce_since + s_delay_tx_us; s_delayed_pending = 1U; }
            else if (s_suppress_tx == 0U)
            {
                s_registers[7][0] |= s_max_rt != 0U ? 0x10U : 0x20U;
                if (s_max_rt == 0U)
                {
                    assert(s_wire_count < 512U);
                    memcpy(s_wire[s_wire_count], s_tx_packet, s_tx_length);
                    s_wire_lengths[s_wire_count++] = s_tx_length; s_tx_present = 0U;
                }
            }
        }
        s_ce = high;
    }
    else { return PLATFORM_INVALID_ARGUMENT; }
    return PLATFORM_OK;
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout)
{
    uint8_t op = tx[0];
    uint8_t index;
    assert(id == PLATFORM_SPI_1 && s_csn == 0U && length <= 33U && timeout == 2U);
    s_spi_calls++; memset(rx, 0, length);
    if (s_fail != 0U) { return PLATFORM_TIMEOUT; }
    if (s_absent != 0U) { memset(rx, 255, length); return PLATFORM_OK; }
    if (s_delayed_pending != 0U && s_us >= s_tx_due_us)
    {
        s_registers[7][0] |= 0x20U;
        assert(s_wire_count < 512U);
        memcpy(s_wire[s_wire_count],s_tx_packet,s_tx_length);
        s_wire_lengths[s_wire_count++]=s_tx_length;
        s_tx_present=0U; s_delayed_pending=0U;
    }
    if (op <= 0x1FU)
    {
        if (op == 0x17U) { rx[1] = s_rx_count == 0U ? 1U : 0U; }
        else { memcpy(&rx[1], s_registers[op], length - 1U); }
    }
    else if (op >= 0x20U && op <= 0x3FU)
    {
        uint8_t reg = op & 0x1FU;
        if (reg == 7U) { s_registers[7][0] &= (uint8_t)~tx[1]; }
        else if (reg != 0x1DU || s_locked_feature == 0U)
        { memcpy(s_registers[reg], &tx[1], length - 1U); }
    }
    else if (op == 0x50U) { assert(tx[1] == 0x73U); s_locked_feature = 0U; s_activate_count++; }
    else if (op == 0x60U) { rx[1] = s_rx_lengths[0]; }
    else if (op == 0x61U)
    {
        assert(s_rx_count > 0U); memcpy(&rx[1], s_rx[0], length - 1U);
        s_rx_count--;
        for (index = 0U; index < 2U; index++)
        { memcpy(s_rx[index], s_rx[index + 1U], 32U); s_rx_lengths[index] = s_rx_lengths[index + 1U]; }
    }
    else if (op == 0xA0U)
    { assert(s_tx_present == 0U); memcpy(s_tx_packet, &tx[1], length - 1U); s_tx_length = (uint8_t)(length - 1U); s_tx_present = 1U; }
    else if (op == 0xE1U) { s_tx_present = 0U; s_delayed_pending = 0U; s_flush_tx++; }
    else if (op == 0xE2U) { s_rx_count = 0U; }
    else { assert(0); }
    return PLATFORM_OK;
}

static void Tick(uint32_t us)
{
    uint32_t before = s_spi_calls;
    s_us += us; Nrf24_Process(0U);
    assert(s_spi_calls - before <= 30U); /* Bounded configuration and FIFO rounds. */
    assert(s_csn == 1U);
}

static void Start(void)
{
    Nrf24Stats stats;
    assert(Nrf24_Init(0U) == Nrf24Result_Ok);
    assert(Nrf24_Start(0U) == Nrf24Result_Ok);
    Tick(99999U); assert(s_spi_calls == 0U && s_ce == 0U);
    Tick(1U); Tick(1U);
    assert(s_ce == 0U); Tick(4999U); assert(s_ce == 0U);
    Tick(1U); Tick(129U); assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 0U);
    Tick(1U); assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 1U);
    assert(s_registers[0][0] == 0x0FU && s_registers[3][0] == 3U);
    assert(s_registers[0x1D][0] == 4U && s_registers[0x1C][0] == 1U);
}

static void FragmentTests(void)
{
    uint8_t data[62], out[64], packet[3][32], lengths[3];
    uint16_t length;
    uint8_t size, index;
    Nrf24FragmentRx rx;
    for (index = 0U; index < 62U; index++) { data[index] = index; }
    assert(Nrf24Fragment_Crc((const uint8_t *)"123456789", 9U) == 0x29B1U);
    for (size = 1U; size <= 61U; size++)
    {
        uint8_t count = (uint8_t)((size + 21U) / 22U);
        memset(&rx, 0, sizeof(rx)); memset(out, 0xA5, sizeof(out));
        for (index = 0U; index < count; index++)
        { assert(Nrf24Fragment_Encode(data, size, 1U, 5U, index, packet[index], &lengths[index]) == Nrf24FragmentResult_Ok); }
        for (index = count; index > 0U; index--)
        {
            assert(Nrf24Fragment_Accept(&rx, packet[index - 1U], lengths[index - 1U], 0xFFFFFFF0U) ==
                (index == 1U ? Nrf24FragmentResult_Ok : Nrf24FragmentResult_Pending));
            if (index > 1U)
            { length = 999U; assert(Nrf24Fragment_Read(&rx, out, 64U, &length) == Nrf24FragmentResult_Empty && length == 0U && out[0] == 0xA5U); }
        }
        assert(Nrf24Fragment_Read(&rx, out, size - 1U, &length) == Nrf24FragmentResult_Invalid);
        assert(Nrf24Fragment_Read(&rx, out, 64U, &length) == Nrf24FragmentResult_Ok && length == size && memcmp(out, data, size) == 0);
        assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 1U) == Nrf24FragmentResult_Duplicate);
    }
    assert(Nrf24Fragment_Encode(data, 62U, 1U, 1U, 0U, packet[0], &lengths[0]) == Nrf24FragmentResult_Invalid);
    memset(&rx, 0, sizeof(rx));
    assert(Nrf24Fragment_Encode(data, 50U, 1U, 65535U, 0U, packet[0], &lengths[0]) == Nrf24FragmentResult_Ok);
    assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 0xFFFFFF80U) == Nrf24FragmentResult_Pending);
    assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 0xFFFFFF81U) == Nrf24FragmentResult_Duplicate);
    packet[0][10] ^= 1U; assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 0xFFFFFF82U) == Nrf24FragmentResult_Conflict);
    packet[0][10] ^= 1U; assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 0xFFFFFF80U) == Nrf24FragmentResult_Pending);
    Nrf24Fragment_Expire(&rx, 200U); assert(rx.active == 0U);
    for (index = 0U; index < 3U; index++)
    {
        assert(Nrf24Fragment_Encode(data, 50U, 2U, 0U, index, packet[index], &lengths[index]) == Nrf24FragmentResult_Ok);
        if (index == 2U) { packet[index][10] ^= 1U; }
        assert(Nrf24Fragment_Accept(&rx, packet[index], lengths[index], 300U) == (index == 2U ? Nrf24FragmentResult_Integrity : Nrf24FragmentResult_Pending));
    }
    assert(rx.ready == 0U);
    packet[0][6] = 61U; assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 400U) == Nrf24FragmentResult_Pending);
    packet[1][6] = 49U; assert(Nrf24Fragment_Accept(&rx, packet[1], lengths[1], 400U) == Nrf24FragmentResult_Conflict);
    assert(rx.ready == 0U);
    /* A peer reboot can reuse its volatile tag/sequence. A bounded duplicate
     * window must expire rather than suppress its new telemetry for hours. */
    memset(&rx, 0, sizeof(rx));
    assert(Nrf24Fragment_Encode(data, 9U, 1U, 30000U, 0U, packet[0], &lengths[0]) == Nrf24FragmentResult_Ok);
    assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 0U) == Nrf24FragmentResult_Ok);
    assert(Nrf24Fragment_Read(&rx, out, 64U, &length) == Nrf24FragmentResult_Ok);
    assert(Nrf24Fragment_Encode(data, 9U, 1U, 1U, 0U, packet[0], &lengths[0]) == Nrf24FragmentResult_Ok);
    assert(Nrf24Fragment_Accept(&rx, packet[0], lengths[0], 251U) == Nrf24FragmentResult_Ok);
}

static void TxTests(void)
{
    uint8_t data[61], control[9] = {0x30U, 1U, 7U, 0U, 0U, 0U, 0U, 0U, 0U};
    uint32_t id, age, i;
    Nrf24Stats stats;
    memset(data, 0xAB, sizeof(data)); Start();
    assert(Nrf24_Send(0U, data, 61U, 0U, NULL) == Nrf24Result_Ok);
    assert(Nrf24_Send(0U, data, 61U, 0U, NULL) == Nrf24Result_Ok);
    assert(Nrf24_Send(0U, data, 61U, 0U, NULL) == Nrf24Result_Busy);
    assert(Nrf24_Send(0U, control, 9U, 1U, &id) == Nrf24Result_Ok);
    assert(Nrf24_ReceiptGet(0U, id, &age) == Nrf24Result_Busy);
    Tick(1U); Tick(14U); assert(s_wire_count == 0U);
    Tick(1U); assert(s_wire_count == 1U && memcmp(&s_wire[0][10], control, 9U) == 0);
    assert(Nrf24_ReceiptGet(0U, id, &age) == Nrf24Result_Busy);
    Tick(1U); assert(Nrf24_ReceiptGet(0U, id, &age) == Nrf24Result_Ok);
    for (i = 0U; i < 80U; i++) { Tick(1000U); }
    assert(s_wire_count == 7U); assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.tx_ok == 3U);
    s_max_rt = 1U; assert(Nrf24_Send(0U, control, 9U, 1U, &id) == Nrf24Result_Ok);
    Tick(1U); Tick(15U); Tick(1U);
    assert(Nrf24_ReceiptGet(0U, id, &age) == Nrf24Result_Timeout && s_flush_tx == 2U && s_tx_present == 0U);
    s_max_rt = 0U; Tick(130U);
    s_suppress_tx = 1U; assert(Nrf24_Send(0U, control, 9U, 1U, &id) == Nrf24Result_Ok);
    Tick(1U); Tick(15U); Tick(60000U);
    assert(Nrf24_ReceiptGet(0U, id, &age) == Nrf24Result_Timeout && s_tx_present == 0U);
}

static void RxFaultTests(void)
{
    uint8_t data[50], out[64], index;
    uint16_t length = 0U;
    Nrf24Stats stats;
    memset(data, 0x11, 50U); Start();
    for (index = 0U; index < 3U; index++)
    { assert(Nrf24Fragment_Encode(data, 50U, 99U, 1U, index, s_rx[index], &s_rx_lengths[index]) == Nrf24FragmentResult_Ok); }
    s_rx_count = 2U; Tick(1U); assert(Nrf24_Receive(0U, out, 64U, &length) == Nrf24Result_Empty && length == 0U);
    s_rx_count = 1U; /* The mock shifted the remaining third fragment into slot zero. */
    Tick(1U); assert(Nrf24_Receive(0U, out, 64U, &length) == Nrf24Result_Ok && length == 50U && memcmp(out, data, 50U) == 0);
    s_rx_lengths[0] = 33U; s_rx_count = 1U; Tick(1U); assert(s_rx_count == 0U);
    s_fail = 1U; Tick(1U); assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 0U && stats.spi_timeout > 0U);
    Tick(1000000U); Tick(1U); s_fail = 0U;
    Tick(1000000U); Tick(1U); Tick(5000U); Tick(130U);
    assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 1U && stats.recovery_attempts == 2U);
    assert(Nrf24_Stop(0U) == Nrf24Result_Ok); assert(Nrf24_Send(0U, data, 50U, 0U, NULL) == Nrf24Result_Offline);
}

static void RecoveryWrapTests(void)
{
    uint32_t i;
    Nrf24Stats stats;
    s_absent = 1U;
    assert(Nrf24_Init(0U) == Nrf24Result_Ok);
    assert(Nrf24_Start(0U) == Nrf24Result_Ok);
    Tick(100000U); Tick(1U);
    for (i = 0U; i < 65537U; i++) { Tick(1000000U); Tick(1U); }
    assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok);
    assert(stats.ready == 0U && stats.recovery_attempts == 65537U);
    s_absent = 0U;
    Tick(1000000U); Tick(1U); Tick(5000U); Tick(130U);
    assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 1U);
}

static void AirRoundtrip(const char *name, const uint8_t *frame, uint8_t size)
{
    Nrf24FragmentRx peer = {0};
    uint8_t packet[32], received[61], width, i;
    uint16_t length = 0U;
    uint8_t count = (uint8_t)((size + 21U) / 22U);
    for (i = 0U; i < count; i++)
    {
        assert(Nrf24Fragment_Encode(frame,size,1U,1U,i,packet,&width) == Nrf24FragmentResult_Ok);
        assert(Nrf24Fragment_Accept(&peer,packet,width,0U) ==
            (i + 1U == count ? Nrf24FragmentResult_Ok : Nrf24FragmentResult_Pending));
    }
    assert(Nrf24Fragment_Read(&peer,received,sizeof(received),&length) == Nrf24FragmentResult_Ok);
    assert(length == size && memcmp(received,frame,size) == 0);
    assert(Air_FrameValidate(received,size) == AIR_PARSE_OK);
    printf("GOLDEN_%s ",name);
    for (i=0U; i<size; i++) { printf("%02x",received[i]); }
    puts("");
}

static void AirCodecTests(void)
{
    AirFlightStatePayload state = {0};
    AirCapabilityPayload capability = {0U,1U,1U,9U,16U,2000U};
    AirCmdPayload command;
    uint8_t frame[50], length;
    const uint8_t capability_ack[9] = {0x30U,7U,5U,0U,0U,0U,0U,6U,0U};
    state.time_ms = 0x01020304U;
    assert(Air_FlightStateBuild(0x42U,&state,frame,sizeof(frame),&length) == AIR_BUILD_OK);
    assert(length == 50U); AirRoundtrip("FLIGHT_STATE",frame,length);
    assert(Air_CapabilityBuild(6U,&capability,frame,sizeof(frame),&length) == AIR_BUILD_OK);
    AirRoundtrip("CAPABILITY",frame,length);
    assert(Air_CmdParse(capability_ack,9U,&command) == AIR_PARSE_OK);
    assert(command.seq == 7U && command.cmd_id == AIR_CMD_CAPABILITY_ACK && command.param0 == 6U);
    AirRoundtrip("CMD",capability_ack,9U);
    assert(Air_AckBuild(8U,7U,AIR_CMD_CAPABILITY_ACK,AIR_ACK_RESULT_OK,
        state.time_ms,frame,sizeof(frame),&length) == AIR_BUILD_OK);
    AirRoundtrip("ACK",frame,length);
}

static void CollisionTests(void)
{
    uint8_t old[50] = {0}, newer[50] = {0}, packet[32], out[61], width, i;
    uint16_t length;
    Nrf24FragmentRx rx = {0};
    newer[0]=1U; newer[20]=0x35U; newer[21]=0xB3U;
    newer[22]=1U; newer[42]=0x35U; newer[43]=0xB3U;
    assert(Nrf24Fragment_Crc(old,50U) == Nrf24Fragment_Crc(newer,50U));
    for (i=0U;i<3U;i++)
    {
        assert(Nrf24Fragment_Encode(i==0U ? old : newer,50U,1U,1U,i,packet,&width) == Nrf24FragmentResult_Ok);
        assert(Nrf24Fragment_Accept(&rx,packet,width,0U) ==
            (i==2U ? Nrf24FragmentResult_Ok : Nrf24FragmentResult_Pending));
    }
    assert(Nrf24Fragment_Read(&rx,out,sizeof(out),&length) == Nrf24FragmentResult_Ok);
    assert(length==50U && memcmp(out,old,50U)!=0 && memcmp(out,newer,50U)!=0);
    puts("KNOWN_LIMIT: identity reuse plus CRC16 collision permits a mixed complete frame");
}

static void LateCompletionTests(void)
{
    const uint8_t frame[9]={0x30U,1U,2U,0U,0U,0U,0U,0U,0U};
    uint32_t id,age;
    Start();
    assert(Nrf24_Send(0U,frame,9U,1U,&id)==Nrf24Result_Ok);
    Tick(1U); Tick(15U); assert(s_wire_count==1U);
    Tick(60000U);
    assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Ok);
}

static void SlowConfigurationTests(void)
{
    const uint8_t frame[61]={0x10U};
    uint32_t id,age,i;
    Start(); s_delay_tx_us=85000U;
    assert(Nrf24_Send(0U,frame,61U,1U,&id)==Nrf24Result_Ok);
    Tick(1U); Tick(15U); Tick(59999U);
    assert(s_wire_count==0U && s_tx_present==1U);
    assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Busy);
    for(i=0U;i<260U;i++) { Tick(1000U); }
    assert(s_wire_count==3U);
    assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Ok);
}

static void SlowFragmentStreamTests(void)
{
    uint8_t data[61]={0x10U},packet[3][32],width[3],out[61],i;
    uint16_t length;
    const uint32_t arrival[3]={1U,90U,265U};
    Nrf24FragmentRx rx={0};
    for(i=0U;i<3U;i++)
    {
        assert(Nrf24Fragment_Encode(data,61U,1U,1U,i,packet[i],&width[i])==Nrf24FragmentResult_Ok);
        assert(Nrf24Fragment_Accept(&rx,packet[i],width[i],arrival[i])==
            (i==2U ? Nrf24FragmentResult_Ok : Nrf24FragmentResult_Pending));
    }
    assert(Nrf24Fragment_Read(&rx,out,sizeof(out),&length)==Nrf24FragmentResult_Ok);
    assert(length==61U && memcmp(out,data,61U)==0);
    memset(&rx,0,sizeof(rx));
    assert(Nrf24Fragment_Accept(&rx,packet[0],width[0],0U)==Nrf24FragmentResult_Pending);
    assert(Nrf24Fragment_Accept(&rx,packet[0],width[0],249U)==Nrf24FragmentResult_Duplicate);
    Nrf24Fragment_Expire(&rx,250U); assert(rx.active==0U);
    memset(&rx,0,sizeof(rx));
    assert(Nrf24Fragment_Accept(&rx,packet[0],width[0],UINT32_MAX-20U)==Nrf24FragmentResult_Pending);
    assert(Nrf24Fragment_Accept(&rx,packet[1],width[1],100U)==Nrf24FragmentResult_Pending);
    assert(Nrf24Fragment_Accept(&rx,packet[2],width[2],300U)==Nrf24FragmentResult_Ok);
}

static void FaultPublicationTests(void)
{
    Start(); s_fail=1U; s_inject_fault_send=1U;
    Tick(1U);
    assert(s_injected_result==Nrf24Result_Offline);
    s_fail=0U; Tick(1000000U); Tick(100000U); Tick(1U); Tick(5000U); Tick(130U);
    assert(s_wire_count==0U); /* No command entered during failure publication. */
}

static void InitGpioFaultTests(void)
{
    Nrf24Stats stats;
    s_gpio_fail=1U;
    assert(Nrf24_Init(0U)==Nrf24Result_Ok);
    assert(Nrf24_Start(0U)==Nrf24Result_Ok);
    Tick(1000000U); assert(Nrf24_StatsGet(0U,&stats)==Nrf24Result_Ok && stats.ready==0U);
    s_gpio_fail=0U;
    Tick(1000000U); Tick(100000U); Tick(1U); Tick(5000U); Tick(130U);
    assert(Nrf24_StatsGet(0U,&stats)==Nrf24Result_Ok && stats.ready==1U);
}

static void TerminalTests(uint8_t flags)
{
    const uint8_t command[9]={0x30U};
    uint32_t id,age;
    Nrf24Stats stats;
    Start();s_suppress_tx=1U;
    assert(Nrf24_Send(0U,command,9U,1U,&id)==Nrf24Result_Ok);
    Tick(1U);Tick(15U);s_registers[7][0]|=flags;Tick(100000U);
    if(flags==0x30U)
    {
        assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Io);
        assert(Nrf24_StatsGet(0U,&stats)==Nrf24Result_Ok && stats.ready==0U);
    }
    else
    { assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Timeout && s_tx_present==0U); }
}

static void DeadlineTests(void)
{
    const uint8_t command[9]={0x30U};
    uint32_t id,age;
    /* 19B physical payload, 1Mbps, ARD1000, ARC3:
       130 + 4*(225 + 203) + 3000 = 4842us from CE edge. */
    Start();s_suppress_tx=1U;
    assert(Nrf24_Send(0U,command,9U,1U,&id)==Nrf24Result_Ok);
    Tick(1U);Tick(15U);Tick(4826U);
    assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Busy);
    Tick(1U);assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Timeout);
}

static uint8_t Hex_Decode(const char *text,uint8_t *data,uint8_t capacity)
{
    size_t chars=strlen(text);uint8_t i;
    assert(chars>0U && chars%2U==0U && chars/2U<=capacity);
    for(i=0U;i<chars/2U;i++)
    { unsigned int value;assert(sscanf(text+2U*i,"%2x",&value)==1);data[i]=(uint8_t)value; }
    return (uint8_t)(chars/2U);
}

static void Pair_Send(const char *text,uint8_t slow)
{
    uint8_t data[61],length=Hex_Decode(text,data,sizeof(data)),i,j;
    uint32_t id,age;
    Start();
    if(slow!=0U) { s_delay_tx_us=78000U; }
    assert(Nrf24_Send(0U,data,length,(uint8_t)(data[0]==0x30U),&id)==Nrf24Result_Ok);
    Tick(1U);Tick(15U);
    for(i=0U;i<8U;i++) { Tick(slow!=0U ? 200000U : 1000U); }
    assert(Nrf24_ReceiptGet(0U,id,&age)==Nrf24Result_Ok);
    for(i=0U;i<s_wire_count;i++)
    { printf("WIRE ");for(j=0U;j<s_wire_lengths[i];j++) { printf("%02x",s_wire[i][j]); }puts(""); }
}

static void Pair_Receive(const char *text)
{
    char packets[256];char *part;
    uint8_t output[61],i=0U,j;uint16_t length=0U;
    assert(strlen(text)<sizeof(packets));strcpy(packets,text);Start();
    part=strtok(packets,",");
    while(part!=NULL)
    {
        assert(s_rx_count==0U);s_rx_lengths[0]=Hex_Decode(part,s_rx[0],32U);s_rx_count=1U;
        Tick(i==0U ? 1U : 200000U);i++;
        part=strtok(NULL,",");
        if(part!=NULL) { assert(Nrf24_Receive(0U,output,sizeof(output),&length)==Nrf24Result_Empty && length==0U); }
    }
    assert(Nrf24_Receive(0U,output,sizeof(output),&length)==Nrf24Result_Ok);
    printf("RECEIVED ");for(j=0U;j<length;j++) { printf("%02x",output[j]); }puts("");
}

static void SequenceWrapTests(void)
{
    const uint8_t command[9]={0x30U};
    uint32_t count;
    Nrf24FragmentRx peer={0};
    uint8_t received[61];uint16_t length;
    Start();
    for(count=1U;count<=65537U;count++)
    {
        s_wire_count=0U;
        assert(Nrf24_Send(0U,command,9U,1U,NULL)==Nrf24Result_Ok);
        Tick(1U);Tick(15U);Tick(1U);Tick(130U);
        assert(s_wire_count==1U);
        assert(((uint16_t)s_wire[0][4]|((uint16_t)s_wire[0][5]<<8U))==(uint16_t)count);
        assert((uint16_t)((uint16_t)s_wire[0][2]|((uint16_t)s_wire[0][3]<<8U))==(uint16_t)(count>=65536U ? 2U : 1U));
        assert(Nrf24Fragment_Accept(&peer,s_wire[0],s_wire_lengths[0],PlatformTime_Ms())==Nrf24FragmentResult_Ok);
        assert(Nrf24Fragment_Read(&peer,received,sizeof(received),&length)==Nrf24FragmentResult_Ok);
        assert(length==9U && memcmp(received,command,9U)==0);
    }
}

static void GroundAdapterTests(void)
{
    const uint8_t air[9]={0x40U,8U,7U,5U,0U,4U,3U,2U,1U};
    uint8_t received[61],width,length,packet[32],gsp[70];
    int8_t rssi=42,snr=43;GroundRadioStats stats;
    assert(GroundRadio_Init()==GROUND_RADIO_OK && GroundRadio_MetricsSupportedGet()==0U);
    GroundRadio_StatsGet(&stats);assert(stats.radio_state==GSP_RADIO_STATE_NOT_INIT);
    Tick(100000U);Tick(1U);Tick(5000U);Tick(130U);
    GroundRadio_StatsGet(&stats);assert(stats.radio_state==GSP_RADIO_STATE_READY);
    assert(Nrf24Fragment_Encode(air,9U,9U,1U,0U,packet,&width)==Nrf24FragmentResult_Ok);
    memcpy(s_rx[0],packet,width);s_rx_lengths[0]=width;s_rx_count=1U;Tick(1U);
    assert(GroundRadio_RxDequeue(received,&length,&rssi,&snr)==GROUND_RADIO_OK);
    assert(length==9U && memcmp(received,air,9U)==0 && rssi==42 && snr==43);
    assert(GspMin_BuildNrf24AirRxFrame(received,length,gsp,sizeof(gsp))==18U);
    assert(gsp[2]==5U && gsp[3]==12U && gsp[4]==1U && gsp[5]==0U && gsp[6]==9U);
    assert(memcmp(gsp+7U,air,9U)==0);
    assert(GroundRadio_TxEnqueue(air,9U)==GROUND_RADIO_OK);
    Tick(1U);Tick(15U);Tick(1U);assert(s_wire_count==1U);
    Tick(130U);s_rx_count=1U;s_rx_lengths[0]=33U;Tick(1U);
    GroundRadio_StatsGet(&stats);assert(stats.rx_crc_error==0U);
    assert(Nrf24Fragment_Encode(air,9U,9U,2U,0U,packet,&width)==Nrf24FragmentResult_Ok);
    packet[10]^=0x80U;memcpy(s_rx[0],packet,width);s_rx_lengths[0]=width;s_rx_count=1U;Tick(1U);
    GroundRadio_StatsGet(&stats);assert(stats.rx_crc_error==1U);
    assert(GroundRadio_RxDequeue(received,&length,&rssi,&snr)==GROUND_RADIO_EMPTY && length==0U);
}

int main(int argc, char **argv)
{
    assert(argc>=2);
    if (strcmp(argv[1], "pair_send") == 0 || strcmp(argv[1], "pair_slow_send") == 0)
    { assert(argc==3);Pair_Send(argv[2],(uint8_t)(strcmp(argv[1],"pair_slow_send")==0));return 0; }
    if (strcmp(argv[1], "pair_receive") == 0)
    { assert(argc==3);Pair_Receive(argv[2]);return 0; }
    assert(argc==2);
    if (strcmp(argv[1], "fragment") == 0) { FragmentTests(); }
    else if (strcmp(argv[1], "tx") == 0) { TxTests(); }
    else if (strcmp(argv[1], "rx_fault") == 0) { RxFaultTests(); }
    else if (strcmp(argv[1], "recovery_wrap") == 0) { RecoveryWrapTests(); }
    else if (strcmp(argv[1], "air_codec") == 0) { AirCodecTests(); }
    else if (strcmp(argv[1], "collision_limit") == 0) { CollisionTests(); }
    else if (strcmp(argv[1], "late_completion") == 0) { LateCompletionTests(); }
    else if (strcmp(argv[1], "slow_configuration") == 0) { SlowConfigurationTests(); }
    else if (strcmp(argv[1], "init_gpio_fault") == 0) { InitGpioFaultTests(); }
    else if (strcmp(argv[1], "late_max_rt") == 0) { TerminalTests(0x10U); }
    else if (strcmp(argv[1], "conflicting_terminal") == 0) { TerminalTests(0x30U); }
    else if (strcmp(argv[1], "ground_adapter") == 0) { GroundAdapterTests(); }
    else if (strcmp(argv[1], "sequence_wrap") == 0) { SequenceWrapTests(); }
    else if (strcmp(argv[1], "deadline") == 0) { DeadlineTests(); }
    else if (strcmp(argv[1], "fault_publication") == 0) { FaultPublicationTests(); }
    else if (strcmp(argv[1], "slow_fragment_stream") == 0) { SlowFragmentStreamTests(); }
    else if (strcmp(argv[1], "feature") == 0) { s_locked_feature = 1U; Start(); assert(s_activate_count == 1U); }
    else if (strcmp(argv[1], "absent") == 0)
    { Nrf24Stats stats; s_absent = 1U; assert(Nrf24_Init(0U) == Nrf24Result_Ok); assert(Nrf24_Start(0U) == Nrf24Result_Ok); Tick(100000U); Tick(1U); assert(Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok && stats.ready == 0U); }
    else { assert(0); }
    puts("NRF24 host: 0 failures"); return 0;
}
