/* Host-only fault interception. Never part of a target source graph. */
#include "bmp390_core.h"
#include "mmc5983ma_core.h"
#include "silverstar_assert.h"

#include <assert.h>
#include <setjmp.h>
#include <stddef.h>
#include <string.h>

static jmp_buf s_trap;
static unsigned int s_io_count;
static SilverStarAssertReasonId s_reason;
static Bmp390Context s_bmp;
static Mmc5983maContext s_mmc;

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    assert(module == SILVERSTAR_ASSERT_MODULE_DEVICE);
    assert(file != NULL && line != 0U);
    if (condition == 0U) { s_reason = reason; longjmp(s_trap, 1); }
}

Bmp390BusResult Bmp390Bus_Read(void *bus, uint8_t address, uint8_t *bytes, uint8_t length)
{
    (void)bus; (void)address; (void)bytes; (void)length;
    s_io_count++;
    return Bmp390BusError;
}

Bmp390BusResult Bmp390Bus_Write(void *bus, uint8_t address, uint8_t value)
{
    (void)bus; (void)address; (void)value;
    s_io_count++;
    return Bmp390BusError;
}

Mmc5983maBusResult Mmc5983maBus_Read(void *bus, uint8_t address, uint8_t *bytes, uint8_t length)
{
    (void)bus; (void)address; (void)bytes; (void)length;
    s_io_count++;
    return Mmc5983maBusError;
}

Mmc5983maBusResult Mmc5983maBus_Write(void *bus, uint8_t address, uint8_t value)
{
    (void)bus; (void)address; (void)value;
    s_io_count++;
    return Mmc5983maBusError;
}

static void Faults_BmpCheck(void)
{
    Bmp390Port port = { &s_io_count };
    Bmp390_Init(&s_bmp, &port);
    s_bmp.state = (Bmp390State)UINT32_MAX;
    if (setjmp(s_trap) == 0) { (void)Bmp390_Step(&s_bmp, 0U); assert(0); }
    assert(s_reason == SILVERSTAR_ASSERT_REASON_ENUM_RANGE && s_io_count == 0U);
    Bmp390_Init(&s_bmp, &port);
    s_bmp.port.bus = NULL;
    if (setjmp(s_trap) == 0) { (void)Bmp390_Step(&s_bmp, 0U); assert(0); }
    assert(s_reason == SILVERSTAR_ASSERT_REASON_STATE_INVARIANT && s_io_count == 0U);
    Bmp390_Init(&s_bmp, &port);
    assert(Bmp390_Step(&s_bmp, 0U) == Bmp390StepBusError);
    assert(s_bmp.state == Bmp390StateFailed && s_bmp.sequence == 0U);
    assert(Bmp390_Step(&s_bmp, 1000U) == Bmp390StepVerifyFailed && s_io_count == 1U);
    Bmp390_Init(&s_bmp, NULL);
    assert(Bmp390_Step(&s_bmp, 2000U) == Bmp390StepVerifyFailed && s_io_count == 1U);
}

static void Faults_MmcCheck(void)
{
    Mmc5983maPort port = { &s_io_count };
    s_io_count = 0U;
    Mmc5983ma_Init(&s_mmc, &port);
    s_mmc.state = Mmc5983maStateApplyConfig;
    s_mmc.config_index = 2U;
    if (setjmp(s_trap) == 0) { (void)Mmc5983ma_Step(&s_mmc, 0U); assert(0); }
    assert(s_reason == SILVERSTAR_ASSERT_REASON_INDEX_RANGE && s_io_count == 0U);
    s_mmc.state = Mmc5983maStateVerifyConfig;
    s_mmc.config_index = UINT8_MAX;
    if (setjmp(s_trap) == 0) { (void)Mmc5983ma_Step(&s_mmc, 0U); assert(0); }
    assert(s_reason == SILVERSTAR_ASSERT_REASON_INDEX_RANGE && s_io_count == 0U);
    Mmc5983ma_Init(&s_mmc, &port);
    assert(Mmc5983ma_Step(&s_mmc, 0U) == Mmc5983maStepBusError);
    assert(s_mmc.state == Mmc5983maStateFailed && s_mmc.sequence == 0U);
    assert(Mmc5983ma_Step(&s_mmc, 1000U) == Mmc5983maStepVerifyFailed && s_io_count == 1U);
    Mmc5983ma_Init(&s_mmc, NULL);
    assert(Mmc5983ma_Step(&s_mmc, 2000U) == Mmc5983maStepVerifyFailed && s_io_count == 1U);
}

int main(void)
{
    Faults_BmpCheck();
    Faults_MmcCheck();
    return 0;
}
