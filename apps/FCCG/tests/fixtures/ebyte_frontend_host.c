/* Real device and real SX128x SetTxParams; fake GPIO/SPI command port.
 * Hardware qualification is outside this deterministic host evidence. */
#include <assert.h>
#define TEST_SX1281_PORTS_ONLY 1
#define PlatformGpio_Write Previous_GpioWrite
#define SX1280SetTxParams Previous_SetTxParams
#include "test_sx1281_device.c"
#undef PlatformGpio_Write
#undef SX1280SetTxParams
PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high);
void SX1280SetTxParams(uint8_t instance, int8_t power, RadioRampTimes_t ramp);
#include "sx1281_device.c"

static uint8_t levels[PLATFORM_GPIO_COUNT];
static uint8_t power_register;
static uint8_t failing_high, failing_off, fail_spi;
static unsigned write_count;
static PlatformGpioId write_ids[128];
static uint8_t write_levels[128];

SystemDeviceResult ProjectSx1281Resources_Get(uint8_t instance, ProjectSx1281Resources *out)
{
    if (out == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    memset(out, 0, sizeof(*out));
    out->reset = (PlatformGpioId)5U;
    out->dio1 = (PlatformGpioId)7U;
    out->rx_en = instance == 0U ? (PlatformGpioId)12U : (PlatformGpioId)PLATFORM_GPIO_COUNT;
    out->tx_en = instance == 0U ? (PlatformGpioId)13U : (PlatformGpioId)PLATFORM_GPIO_COUNT;
    return SYSTEM_DEVICE_OK;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    assert(id < PLATFORM_GPIO_COUNT && high <= 1U && write_count < 128U);
    write_ids[write_count] = id; write_levels[write_count++] = high;
    if ((high != 0U && failing_high != 0U) || (high == 0U && failing_off != 0U))
    { return PLATFORM_IO_ERROR; }
    levels[id] = high;
    assert(!(levels[12] != 0U && levels[13] != 0U));
    return PLATFORM_OK;
}

void SX1280HalWriteCommand(uint8_t instance, RadioCommands_t command, uint8_t *buffer, uint16_t size)
{
    (void)instance;
    assert(command == RADIO_SET_TXPARAMS && size == 2U);
    power_register = buffer[0];
}

static void Expect_Transition(uint8_t mode)
{
    write_count = 0U;
    assert(Lora_RfFrontendSet(0U, mode) == 1U);
    assert(write_ids[0] == 12U && write_levels[0] == 0U);
    assert(write_ids[1] == 13U && write_levels[1] == 0U);
    assert(write_count == (mode == 0U ? 2U : 3U));
    if (mode != 0U) { assert(write_ids[2] == (mode == 1U ? 12U : 13U) && write_levels[2] == 1U); }
}

int main(int argc, char **argv)
{
    (void)argc; (void)argv; (void)fail_spi;
    assert(Lora_Init(0U) == LORA_INIT_OK);
    assert(power_register == EXPECTED_POWER_REGISTER);
    assert(levels[12] == 0U && levels[13] == 0U);
    Expect_Transition(1U); Expect_Transition(2U); Expect_Transition(0U);
    write_count = 0U;
    assert(Lora_RfFrontendSet(1U, 2U) == 1U && write_count == 0U);
    Lora_StartRx(0U); assert(levels[12] == 1U && levels[13] == 0U);
    unsigned rx_before = s_set_rx_count;
    Lora_OnRxDone(0U); assert(s_set_rx_count == rx_before); /* IRQ only latches. */
    assert(Lora_ForceRxContinuousDirect(0U) == LORA_DIAG_RESULT_OK);
    assert(levels[12] == 1U && levels[13] == 0U);
    uint8_t byte = 1U;
    assert(Lora_TxEnqueue(0U, &byte, 1U) == LORA_TX_ENQUEUE_OK);
    Lora_TryStartNextTx(0U); assert(levels[12] == 0U && levels[13] == 1U);
    Lora_OnTxDone(0U); /* No GPIO writes in the callback. */
    assert(levels[13] == 1U);
    Lora_TxCompletionProcess(0U); assert(levels[12] == 0U && levels[13] == 0U);
    Expect_Transition(2U);
    assert(Lora_RadioRecover(0U, 0U) == 1U && levels[13] == 0U);
    failing_high = 1U;
    Lora_StartRx(0U);
    assert(s_contexts[0].inited == 0U && levels[12] == 0U && levels[13] == 0U);
    failing_high = 0U;
    assert(Lora_Init(0U) == LORA_INIT_OK);
    Expect_Transition(2U);
    assert(Lora_Deactivate(0U) == LoraDeactivateResult_Ok);
    assert(levels[12] == 0U && levels[13] == 0U && levels[5] == 0U);
    failing_off = 1U; write_count = 0U;
    assert(Lora_Init(0U) == LORA_INIT_PORT_ERROR && write_count == 2U);
    assert(s_contexts[0].inited == 0U);
    return Test_Finish("ebyte_frontend");
}

