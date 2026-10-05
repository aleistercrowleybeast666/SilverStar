/*
  ______                              _
 / _____)             _              | |
( (____  _____ ____ _| |_ _____  ____| |__
 \____ \| ___ |    (_   _) ___ |/ ___)  _ \
 _____) ) ____| | | || |_| ____( (___| | | |
(______/|_____)_|_|_| \__)_____)\____)_| |_|
    (C)2016 Semtech

Description: Handling of the node configuration protocol

License: Revised BSD License, see LICENSE.TXT file include in the project

Maintainer: Miguel Luis, Matthieu Verdy and Benjamin Boulet
*/
#include "hw.h"
#include "sx1280-hal.h"

#include <string.h>

#include "platform_critical.h"
#include "platform_time.h"
#include "sx1281_config.h"

/* Ground supports the complete uint8_t packet-buffer operations plus
 * command/register requests through 256 bytes. All larger internal requests
 * fail before access/publication. Flight retains the historical 4095 bytes.
 * IRAM clearing below chunks writes to the same addresses and total length. */
#ifdef AIR_LINK_HAL_BUFFER_SIZE
#include "silverstar_assert.h"
#define MAX_HAL_BUFFER_SIZE AIR_LINK_HAL_BUFFER_SIZE
_Static_assert((MAX_HAL_BUFFER_SIZE >= 259U) && (MAX_HAL_BUFFER_SIZE <= 4095U),
               "Ground HAL capacity must cover 255 bytes plus four header bytes");
#else
#define MAX_HAL_BUFFER_SIZE 0x0FFFU
#endif

typedef struct
{
    uint8_t tx_buffer[MAX_HAL_BUFFER_SIZE];
    uint8_t rx_buffer[MAX_HAL_BUFFER_SIZE];
} Sx1280HalContext;

static Sx1280HalContext s_hal_contexts[PROJECT_SX1281_INSTANCE_COUNT];

_Static_assert(PROJECT_SX1281_INSTANCE_COUNT <=
               PROJECT_SX1281_INSTANCE_COUNT_MAX,
               "SX1280 HAL context count exceeds generated resource bound");

#define SX1280_HAL_TX_BUFFER (s_hal_contexts[instance].tx_buffer)
#define SX1280_HAL_RX_BUFFER (s_hal_contexts[instance].rx_buffer)

static void SX1280HalTransfer_Validate(
    uint8_t instance, const uint8_t *buffer, uint16_t size, uint16_t overhead)
{
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((size <= (MAX_HAL_BUFFER_SIZE - overhead)) &&
        ((size == 0U) || (buffer != NULL)),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
#else
    /* Preserve the legacy Flight adapter contract and link dependencies. */
    (void)instance;
    (void)buffer;
    (void)size;
    (void)overhead;
#endif
}

void SX1280HalWaitOnBusy(uint8_t instance)
{
    (void)GpioWaitLow(instance, RADIO_BUSY, LORA_BUSY_TIMEOUT_MS);
}

void SX1280HalInit(uint8_t instance)
{
    SX1280HalReset(instance);
}

void SX1280HalReset(uint8_t instance)
{
    PlatformTime_DelayMs(20U);
    GpioWrite(instance, RADIO_RESET, 0U);
    PlatformTime_DelayMs(50U);
    GpioWrite(instance, RADIO_RESET, 1U);
    PlatformTime_DelayMs(20U);
}

void SX1280HalClearInstructionRam(uint8_t instance)
{
    SX1280HalTransfer_Validate(instance, NULL, 0U, 3U);
    uint16_t remain = IRAM_SIZE;
    uint16_t address = IRAM_START_ADDRESS;
    uint16_t chunk;
    uint16_t hal_size;

    while (remain > 0U)
    {
        chunk = remain;
        if (chunk > (MAX_HAL_BUFFER_SIZE - 3U))
        {
            chunk = (MAX_HAL_BUFFER_SIZE - 3U);
        }

        SX1280_HAL_TX_BUFFER[0] = RADIO_WRITE_REGISTER;
        SX1280_HAL_TX_BUFFER[1] = (uint8_t)((address >> 8U) & 0x00FFU);
        SX1280_HAL_TX_BUFFER[2] = (uint8_t)(address & 0x00FFU);
        (void)memset(&SX1280_HAL_TX_BUFFER[3], 0, chunk);
        hal_size = (uint16_t)(chunk + 3U);

        SX1280HalWaitOnBusy(instance);
        GpioWrite(instance, RADIO_NSS, 0U);
        SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
        GpioWrite(instance, RADIO_NSS, 1U);
        SX1280HalWaitOnBusy(instance);

        address = (uint16_t)(address + chunk);
        remain = (uint16_t)(remain - chunk);
    }
}

void SX1280HalWakeup(uint8_t instance)
{
    SX1280HalTransfer_Validate(instance, NULL, 0U, 2U);
    PlatformCriticalState critical_state = PlatformCritical_Enter();
    uint16_t hal_size = 2U;

    GpioWrite(instance, RADIO_NSS, 0U);
    SX1280_HAL_TX_BUFFER[0] = RADIO_GET_STATUS;
    SX1280_HAL_TX_BUFFER[1] = 0U;
    SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
    PlatformCritical_Exit(critical_state);
}

void SX1280HalWriteCommand(
    uint8_t instance, RadioCommands_t command, uint8_t *buffer, uint16_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 1U);
    uint16_t hal_size = (uint16_t)(size + 1U);

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SX1280_HAL_TX_BUFFER[0] = (uint8_t)command;
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(&SX1280_HAL_TX_BUFFER[1], buffer, size); }
#else
    (void)memcpy(&SX1280_HAL_TX_BUFFER[1], buffer, size);
#endif
    SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
    GpioWrite(instance, RADIO_NSS, 1U);
    if (command != RADIO_SET_SLEEP)
    {
        SX1280HalWaitOnBusy(instance);
    }
}

void SX1280HalReadCommand(
    uint8_t instance, RadioCommands_t command, uint8_t *buffer, uint16_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 2U);
    uint16_t index;
    uint16_t hal_size = (uint16_t)(size + 2U);

    SX1280_HAL_TX_BUFFER[0] = (uint8_t)command;
    SX1280_HAL_TX_BUFFER[1] = 0U;
    for (index = 0U; index < size; index++)
    {
        SX1280_HAL_TX_BUFFER[2U + index] = 0U;
    }

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SpiInOut(instance, SX1280_HAL_TX_BUFFER, SX1280_HAL_RX_BUFFER, hal_size);
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[2], size); }
#else
    (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[2], size);
#endif
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
}

void SX1280HalWriteRegisters(
    uint8_t instance, uint16_t address, uint8_t *buffer, uint16_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 3U);
    uint16_t hal_size = (uint16_t)(size + 3U);

    SX1280_HAL_TX_BUFFER[0] = RADIO_WRITE_REGISTER;
    SX1280_HAL_TX_BUFFER[1] = (uint8_t)((address & 0xFF00U) >> 8U);
    SX1280_HAL_TX_BUFFER[2] = (uint8_t)(address & 0x00FFU);
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(&SX1280_HAL_TX_BUFFER[3], buffer, size); }
#else
    (void)memcpy(&SX1280_HAL_TX_BUFFER[3], buffer, size);
#endif

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
}

void SX1280HalWriteRegister(uint8_t instance, uint16_t address, uint8_t value)
{
    SX1280HalWriteRegisters(instance, address, &value, 1U);
}

void SX1280HalReadRegisters(
    uint8_t instance, uint16_t address, uint8_t *buffer, uint16_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 4U);
    uint16_t index;
    uint16_t hal_size = (uint16_t)(size + 4U);

    SX1280_HAL_TX_BUFFER[0] = RADIO_READ_REGISTER;
    SX1280_HAL_TX_BUFFER[1] = (uint8_t)((address & 0xFF00U) >> 8U);
    SX1280_HAL_TX_BUFFER[2] = (uint8_t)(address & 0x00FFU);
    SX1280_HAL_TX_BUFFER[3] = 0U;
    for (index = 0U; index < size; index++)
    {
        SX1280_HAL_TX_BUFFER[4U + index] = 0U;
    }

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SpiInOut(instance, SX1280_HAL_TX_BUFFER, SX1280_HAL_RX_BUFFER, hal_size);
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[4], size); }
#else
    (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[4], size);
#endif
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
}

uint8_t SX1280HalReadRegister(uint8_t instance, uint16_t address)
{
    uint8_t data = 0U;

    SX1280HalReadRegisters(instance, address, &data, 1U);
    return data;
}

void SX1280HalWriteBuffer(
    uint8_t instance, uint8_t offset, uint8_t *buffer, uint8_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 2U);
    uint16_t hal_size = (uint16_t)size + 2U;

    SX1280_HAL_TX_BUFFER[0] = RADIO_WRITE_BUFFER;
    SX1280_HAL_TX_BUFFER[1] = offset;
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(&SX1280_HAL_TX_BUFFER[2], buffer, size); }
#else
    (void)memcpy(&SX1280_HAL_TX_BUFFER[2], buffer, size);
#endif

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SpiIn(instance, SX1280_HAL_TX_BUFFER, hal_size);
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
}

void SX1280HalReadBuffer(
    uint8_t instance, uint8_t offset, uint8_t *buffer, uint8_t size)
{
    SX1280HalTransfer_Validate(instance, buffer, size, 3U);
    uint16_t index;
    uint16_t hal_size = (uint16_t)size + 3U;

    SX1280_HAL_TX_BUFFER[0] = RADIO_READ_BUFFER;
    SX1280_HAL_TX_BUFFER[1] = offset;
    SX1280_HAL_TX_BUFFER[2] = 0U;
    for (index = 0U; index < size; index++)
    {
        SX1280_HAL_TX_BUFFER[3U + index] = 0U;
    }

    SX1280HalWaitOnBusy(instance);
    GpioWrite(instance, RADIO_NSS, 0U);
    SpiInOut(instance, SX1280_HAL_TX_BUFFER, SX1280_HAL_RX_BUFFER, hal_size);
#ifdef AIR_LINK_HAL_BUFFER_SIZE
    if (size != 0U) { (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[3], size); }
#else
    (void)memcpy(buffer, &SX1280_HAL_RX_BUFFER[3], size);
#endif
    GpioWrite(instance, RADIO_NSS, 1U);
    SX1280HalWaitOnBusy(instance);
}

uint8_t SX1280HalGetDioStatus(uint8_t instance)
{
    uint8_t status = GpioRead(instance, RADIO_BUSY);

#if (RADIO_DIO1_ENABLE)
    status = (uint8_t)(status | (uint8_t)(GpioRead(instance, RADIO_DIO1) << 1U));
#endif
#if (RADIO_DIO2_ENABLE)
#error "DIO2 is not supported by the SX1281 resource binding"
#endif
#if (RADIO_DIO3_ENABLE)
#error "DIO3 is not supported by the SX1281 resource binding"
#endif
#if (!RADIO_DIO1_ENABLE && !RADIO_DIO2_ENABLE && !RADIO_DIO3_ENABLE)
#error "Please define a DIO"
#endif

    return status;
}
