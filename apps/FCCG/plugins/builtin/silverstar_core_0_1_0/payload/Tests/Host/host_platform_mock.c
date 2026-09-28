#include "host_platform_mock.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "platform_i2c.h"
#include "platform_time.h"

#define HOST_PLATFORM_UART_BUFFER_CAPACITY 8192U

typedef struct
{
    uint8_t rx[HOST_PLATFORM_UART_BUFFER_CAPACITY];
    uint8_t tx[HOST_PLATFORM_UART_BUFFER_CAPACITY];
    uint16_t rx_head;
    uint16_t rx_tail;
    uint16_t rx_count;
    uint16_t tx_count;
    uint32_t baudrate;
    PlatformResult init_result;
    PlatformResult write_result;
    PlatformUartDiagnostics diagnostics;
    uint16_t jy901b_registers[128];
    uint8_t jy901b_enabled;
    uint8_t jy901b_ignore_writes;
} HostPlatformUartState;

static HostPlatformUartState s_uart[PLATFORM_UART_COUNT];
static uint64_t s_time_us;
static PlatformResult s_adc_result;
static uint32_t s_adc_sample;
static PlatformResult s_spi_result;
static uint8_t s_gpio[PLATFORM_GPIO_COUNT];
static uint8_t s_gpio_irq[PLATFORM_GPIO_COUNT];

static uint8_t HostPlatformMock_UartIdValid(PlatformUartId id)
{
    return (uint8_t)((id >= PLATFORM_UART_1) &&
                     (id < PLATFORM_UART_COUNT));
}

void HostPlatformMock_Reset(void)
{
    uint8_t index;

    (void)memset(s_uart, 0, sizeof(s_uart));
    (void)memset(s_gpio, 0, sizeof(s_gpio));
    (void)memset(s_gpio_irq, 0, sizeof(s_gpio_irq));
    s_time_us = 0ULL;
    s_adc_result = PLATFORM_OK;
    s_adc_sample = 0U;
    s_spi_result = PLATFORM_OK;
    for (index = 0U; index < PLATFORM_UART_COUNT; index++)
    {
        s_uart[index].baudrate = 115200U;
        s_uart[index].init_result = PLATFORM_OK;
        s_uart[index].write_result = PLATFORM_OK;
    }
}

void HostPlatformMock_TimeSetUs(uint64_t timestamp_us)
{
    s_time_us = timestamp_us;
}

void HostPlatformMock_TimeAdvanceUs(uint64_t delta_us)
{
    s_time_us += delta_us;
}

void HostPlatformMock_UartInitResultSet(PlatformUartId id,
                                        PlatformResult result)
{
    if (HostPlatformMock_UartIdValid(id) != 0U)
    {
        s_uart[id].init_result = result;
    }
}

void HostPlatformMock_UartWriteResultSet(PlatformUartId id,
                                         PlatformResult result)
{
    if (HostPlatformMock_UartIdValid(id) != 0U)
    {
        s_uart[id].write_result = result;
    }
}

void HostPlatformMock_Jy901bEnable(PlatformUartId id, uint8_t enabled,
    uint8_t ignore_writes)
{
    if (HostPlatformMock_UartIdValid(id) == 0U) { return; }
    s_uart[id].jy901b_enabled = enabled;
    s_uart[id].jy901b_ignore_writes = ignore_writes;
}

static void HostPlatformMock_Jy901bRespond(PlatformUartId id,
    const uint8_t *data, uint16_t length)
{
    HostPlatformUartState *uart = &s_uart[id];
    uint8_t response[11] = {0x55U, 0x5FU, 0U};
    uint8_t index;
    uint16_t value;
    if ((uart->jy901b_enabled == 0U) || (length != 5U) ||
        (data[0] != 0xFFU) || (data[1] != 0xAAU) || (data[2] >= 128U)) { return; }
    if (data[2] != 0x27U)
    {
        if (uart->jy901b_ignore_writes == 0U)
        { uart->jy901b_registers[data[2]] = (uint16_t)((uint16_t)data[3] | ((uint16_t)data[4] << 8U)); }
        return;
    }
    if (data[3] >= 128U) { return; }
    value = uart->jy901b_registers[data[3]];
    response[2] = (uint8_t)value;
    response[3] = (uint8_t)(value >> 8U);
    for (index = 0U; index < 10U; index++)
    { response[10] = (uint8_t)(response[10] + response[index]); }
    (void)HostPlatformMock_UartRxInject(id, response, sizeof(response));
}

uint16_t HostPlatformMock_UartRxInject(PlatformUartId id,
                                       const uint8_t *data,
                                       uint16_t length)
{
    uint16_t accepted = 0U;
    HostPlatformUartState *uart;

    if ((HostPlatformMock_UartIdValid(id) == 0U) || (data == NULL))
    {
        return 0U;
    }
    uart = &s_uart[id];
    while ((accepted < length) &&
           (uart->rx_count < HOST_PLATFORM_UART_BUFFER_CAPACITY))
    {
        uart->rx[uart->rx_head] = data[accepted];
        uart->rx_head = (uint16_t)((uart->rx_head + 1U) %
                                   HOST_PLATFORM_UART_BUFFER_CAPACITY);
        uart->rx_count++;
        accepted++;
    }
    uart->diagnostics.rx_bytes += accepted;
    uart->diagnostics.rx_event_count++;
    uart->diagnostics.rx_active = 1U;
    if (accepted != length)
    {
        uart->diagnostics.rx_discarded_bytes +=
            (uint32_t)(length - accepted);
    }
    return accepted;
}

uint16_t HostPlatformMock_UartTxTake(PlatformUartId id,
                                     uint8_t *data,
                                     uint16_t capacity)
{
    uint16_t length;
    HostPlatformUartState *uart;

    if ((HostPlatformMock_UartIdValid(id) == 0U) || (data == NULL))
    {
        return 0U;
    }
    uart = &s_uart[id];
    length = (uart->tx_count < capacity) ? uart->tx_count : capacity;
    (void)memcpy(data, uart->tx, length);
    if (length < uart->tx_count)
    {
        (void)memmove(uart->tx, &uart->tx[length],
                      (size_t)(uart->tx_count - length));
    }
    uart->tx_count = (uint16_t)(uart->tx_count - length);
    return length;
}

void HostPlatformMock_UartDiscontinuityRecord(PlatformUartId id)
{
    if (HostPlatformMock_UartIdValid(id) != 0U)
    {
        s_uart[id].diagnostics.rx_discontinuity_count++;
    }
}

void HostPlatformMock_AdcSet(PlatformResult result, uint32_t sample)
{
    s_adc_result = result;
    s_adc_sample = sample;
}

void HostPlatformMock_GpioSet(PlatformGpioId id, uint8_t logical_high)
{
    if (id < PLATFORM_GPIO_COUNT)
    {
        s_gpio[id] = (uint8_t)(logical_high != 0U);
    }
}

void HostPlatformMock_GpioIrqRaise(PlatformGpioId id)
{
    if (id < PLATFORM_GPIO_COUNT)
    {
        s_gpio_irq[id] = 1U;
    }
}

void HostPlatformMock_SpiResultSet(PlatformResult result)
{
    s_spi_result = result;
}

PlatformResult PlatformUart_Init(PlatformUartId id)
{
    if (HostPlatformMock_UartIdValid(id) == 0U)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart[id].diagnostics.rx_active =
        (uint8_t)(s_uart[id].init_result == PLATFORM_OK);
    return s_uart[id].init_result;
}

PlatformResult PlatformUart_Write(PlatformUartId id,
                                  const uint8_t *data,
                                  uint16_t length,
                                  uint32_t timeout_ms)
{
    HostPlatformUartState *uart;

    (void)timeout_ms;
    if ((HostPlatformMock_UartIdValid(id) == 0U) || (data == NULL) ||
        (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    uart = &s_uart[id];
    if (uart->write_result != PLATFORM_OK)
    {
        uart->diagnostics.transport_error_count++;
        return uart->write_result;
    }
    if (length > (uint16_t)(HOST_PLATFORM_UART_BUFFER_CAPACITY -
                            uart->tx_count))
    {
        uart->diagnostics.tx_discarded_bytes += length;
        return PLATFORM_BUSY;
    }
    (void)memcpy(&uart->tx[uart->tx_count], data, length);
    uart->tx_count = (uint16_t)(uart->tx_count + length);
    uart->diagnostics.tx_bytes += length;
    HostPlatformMock_Jy901bRespond(id, data, length);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_WriteAsync(PlatformUartId id,
                                       const uint8_t *data,
                                       uint16_t length,
                                       PlatformUartTxPriority priority,
                                       uint16_t *accepted_length)
{
    PlatformResult result;

    (void)priority;
    if (accepted_length == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    result = PlatformUart_Write(id, data, length, 0U);
    *accepted_length = (result == PLATFORM_OK) ? length : 0U;
    return result;
}

PlatformResult PlatformUart_Read(PlatformUartId id,
                                 uint8_t *data,
                                 uint16_t capacity,
                                 uint16_t *read_length)
{
    HostPlatformUartState *uart;
    uint16_t count = 0U;

    if ((HostPlatformMock_UartIdValid(id) == 0U) || (data == NULL) ||
        (read_length == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    uart = &s_uart[id];
    while ((count < capacity) && (uart->rx_count != 0U))
    {
        data[count] = uart->rx[uart->rx_tail];
        uart->rx_tail = (uint16_t)((uart->rx_tail + 1U) %
                                   HOST_PLATFORM_UART_BUFFER_CAPACITY);
        uart->rx_count--;
        count++;
    }
    *read_length = count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxFlush(PlatformUartId id)
{
    if (HostPlatformMock_UartIdValid(id) == 0U)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart[id].rx_head = 0U;
    s_uart[id].rx_tail = 0U;
    s_uart[id].rx_count = 0U;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxStop(PlatformUartId id)
{
    if (HostPlatformMock_UartIdValid(id) == 0U)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart[id].diagnostics.rx_active = 0U;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxRestart(PlatformUartId id)
{
    if (HostPlatformMock_UartIdValid(id) == 0U)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart[id].diagnostics.rx_active = 1U;
    s_uart[id].diagnostics.rx_restart_count++;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate)
{
    if ((HostPlatformMock_UartIdValid(id) == 0U) || (baudrate == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart[id].baudrate = baudrate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudGet(PlatformUartId id, uint32_t *baudrate)
{
    if ((HostPlatformMock_UartIdValid(id) == 0U) || (baudrate == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *baudrate = s_uart[id].baudrate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxCountGet(PlatformUartId id, uint16_t *count)
{
    if ((HostPlatformMock_UartIdValid(id) == 0U) || (count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *count = s_uart[id].rx_count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_TxCountGet(PlatformUartId id,
                                       PlatformUartTxPriority priority,
                                       uint16_t *count)
{
    (void)priority;
    if ((HostPlatformMock_UartIdValid(id) == 0U) || (count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *count = s_uart[id].tx_count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id, PlatformUartDiagnostics *diagnostics)
{
    if ((HostPlatformMock_UartIdValid(id) == 0U) ||
        (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *diagnostics = s_uart[id].diagnostics;
    return PLATFORM_OK;
}

void PlatformUart_Process(PlatformUartId id)
{
    (void)id;
}

PlatformResult PlatformSpi_Write(PlatformSpiId id,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t timeout_ms)
{
    (void)timeout_ms;
    if ((id >= PLATFORM_SPI_COUNT) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return s_spi_result;
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
                                    const uint8_t *tx_data,
                                    uint8_t *rx_data,
                                    uint16_t length,
                                    uint32_t timeout_ms)
{
    (void)timeout_ms;
    if ((id >= PLATFORM_SPI_COUNT) || (tx_data == NULL) ||
        (rx_data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    (void)memset(rx_data, 0, length);
    return s_spi_result;
}

PlatformResult PlatformI2c_Write(PlatformI2cId id, uint16_t address,
                                 const uint8_t *data, uint16_t length,
                                 uint32_t timeout_ms)
{
    (void)address;
    (void)timeout_ms;
    return ((id < PLATFORM_I2C_COUNT) && (data != NULL) && (length != 0U)) ?
        PLATFORM_OK : PLATFORM_INVALID_ARGUMENT;
}

PlatformResult PlatformI2c_Read(PlatformI2cId id, uint16_t address,
                                uint8_t *data, uint16_t length,
                                uint32_t timeout_ms)
{
    (void)address;
    (void)timeout_ms;
    if ((id >= PLATFORM_I2C_COUNT) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    (void)memset(data, 0, length);
    return PLATFORM_OK;
}

PlatformResult PlatformI2c_MemoryWrite(
    PlatformI2cId id, uint16_t address, uint16_t memory_address,
    PlatformI2cMemoryAddressSize memory_address_size,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms)
{
    (void)memory_address;
    if ((memory_address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) &&
        (memory_address_size != PLATFORM_I2C_MEMORY_ADDRESS_16_BIT))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformI2c_Write(id, address, data, length, timeout_ms);
}

PlatformResult PlatformI2c_MemoryRead(
    PlatformI2cId id, uint16_t address, uint16_t memory_address,
    PlatformI2cMemoryAddressSize memory_address_size,
    uint8_t *data, uint16_t length, uint32_t timeout_ms)
{
    (void)memory_address;
    if ((memory_address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) &&
        (memory_address_size != PLATFORM_I2C_MEMORY_ADDRESS_16_BIT))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformI2c_Read(id, address, data, length, timeout_ms);
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t logical_high)
{
    if (id >= PLATFORM_GPIO_COUNT) { return PLATFORM_INVALID_ARGUMENT; }
    s_gpio[id] = (uint8_t)(logical_high != 0U);
    return PLATFORM_OK;
}

PlatformResult PlatformGpio_Read(PlatformGpioId id, uint8_t *logical_high)
{
    if ((id >= PLATFORM_GPIO_COUNT) || (logical_high == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *logical_high = s_gpio[id];
    return PLATFORM_OK;
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t pending;

    if (id >= PLATFORM_GPIO_COUNT) { return 0U; }
    pending = s_gpio_irq[id];
    s_gpio_irq[id] = 0U;
    return pending;
}

PlatformResult PlatformAdc_Read(PlatformAdcId id, uint32_t timeout_ms,
                                uint32_t *sample)
{
    (void)timeout_ms;
    if ((id >= PLATFORM_ADC_COUNT) || (sample == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *sample = s_adc_sample;
    return s_adc_result;
}

PlatformResult PlatformTime_Init(void)
{
    s_time_us = 0ULL;
    return PLATFORM_OK;
}

uint32_t PlatformTime_Ms(void)
{
    return (uint32_t)(s_time_us / 1000ULL);
}

uint64_t PlatformTime_Us(void)
{
    return s_time_us;
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    s_time_us += (uint64_t)delay_ms * 1000ULL;
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    return 0U;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    (void)state;
}
