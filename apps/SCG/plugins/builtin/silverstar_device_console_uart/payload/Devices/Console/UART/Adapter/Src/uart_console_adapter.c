#include "system_version.h"
#include "system_console_if.h"

#include <stddef.h>
#include <string.h>

#include "console_uart_device.h"
#include "platform_critical.h"
#include "silverstar_assert.h"

static uint8_t s_initialized;
static uint8_t s_started;
static SystemConsoleHealth s_health;

static void UartConsoleAdapter_HealthRefresh(void)
{
    PlatformCriticalState state;
    PlatformUartDiagnostics diagnostics;
    SystemConsoleHealth health;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_started <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    ConsoleUart_DiagnosticsGet(&diagnostics);
    state = PlatformCritical_Enter();
    health = s_health;
    PlatformCritical_Exit(state);
    health.received_byte_count = diagnostics.rx_bytes;
    health.transmitted_byte_count = diagnostics.tx_bytes;
    health.receive_overrun_count = diagnostics.rx_discarded_bytes;
    health.transmit_error_count = diagnostics.tx_discarded_bytes +
                                  diagnostics.transport_error_count;
    health.online = (uint8_t)((s_started != 0U) &&
                              (diagnostics.rx_active != 0U));
    health.healthy = (uint8_t)((health.online != 0U) &&
                               (diagnostics.rx_restart_failure_count == 0U));
    state = PlatformCritical_Enter();
    s_health = health;
    PlatformCritical_Exit(state);
}

const char *SystemConsoleDevice_NameGet(void)
{
    return "UART3 Console";
}

SystemDeviceResult SystemConsoleDevice_Init(void)
{
    PlatformCriticalState state;

    if (s_initialized != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    state = PlatformCritical_Enter();
    (void)memset(&s_health, 0, sizeof(s_health));
    PlatformCritical_Exit(state);
    if (ConsoleUart_Init() != CONSOLE_UART_INIT_OK)
    {
        return SYSTEM_DEVICE_IO_ERROR;
    }
    state = PlatformCritical_Enter();
    s_initialized = 1U;
    s_health.initialized = 1U;
    PlatformCritical_Exit(state);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_Start(void)
{
    PlatformCriticalState state;

    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_started != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    state = PlatformCritical_Enter();
    s_started = 1U;
    s_health.started = 1U;
    PlatformCritical_Exit(state);
    UartConsoleAdapter_HealthRefresh();
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_Stop(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();

    s_started = 0U;
    s_health.started = 0U;
    s_health.online = 0U;
    s_health.healthy = 0U;
    PlatformCritical_Exit(state);
    return SYSTEM_DEVICE_OK;
}

void SystemConsoleDevice_Process(void)
{
    if (s_started == 0U) { return; }
    ConsoleUart_Process();
    UartConsoleAdapter_HealthRefresh();
}

SystemDeviceResult SystemConsoleDevice_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "UART Console Adapter";
    info->model_name = "Project Console UART";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_CONSOLE_CAP_RX |
                            SYSTEM_CONSOLE_CAP_TX |
                            SYSTEM_CONSOLE_CAP_STREAM;
    info->configuration_mask = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_CapabilitiesGet(
    uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_CONSOLE_CAP_RX |
                       SYSTEM_CONSOLE_CAP_TX |
                       SYSTEM_CONSOLE_CAP_STREAM;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_HealthGet(SystemConsoleHealth *health)
{
    PlatformCriticalState state;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    UartConsoleAdapter_HealthRefresh();
    state = PlatformCritical_Enter();
    *health = s_health;
    PlatformCritical_Exit(state);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{
    PlatformUartDiagnostics source;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    ConsoleUart_DiagnosticsGet(&source);
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT |
        SYSTEM_DEVICE_IO_VALID_RX_BYTES |
        SYSTEM_DEVICE_IO_VALID_TX_BYTES |
        SYSTEM_DEVICE_IO_VALID_RX_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_IDLE_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_TC_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_DISCARDED |
        SYSTEM_DEVICE_IO_VALID_UART_OVERRUN |
        SYSTEM_DEVICE_IO_VALID_UART_FRAMING |
        SYSTEM_DEVICE_IO_VALID_UART_NOISE |
        SYSTEM_DEVICE_IO_VALID_UART_PARITY |
        SYSTEM_DEVICE_IO_VALID_DMA_ERRORS |
        SYSTEM_DEVICE_IO_VALID_RX_RESTARTS |
        SYSTEM_DEVICE_IO_VALID_RX_RESTART_FAILS |
        SYSTEM_DEVICE_IO_VALID_DISCONTINUITIES |
        SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS |
        SYSTEM_DEVICE_IO_VALID_RX_ACTIVE;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_UART;
    diagnostics->owner = SYSTEM_DEVICE_IO_OWNER_SELF;
    diagnostics->rx_bytes = source.rx_bytes;
    diagnostics->tx_bytes = source.tx_bytes;
    diagnostics->rx_event_count = source.rx_event_count;
    diagnostics->rx_idle_event_count = source.rx_idle_event_count;
    diagnostics->rx_transfer_complete_count =
        source.rx_transfer_complete_count;
    diagnostics->rx_discarded_bytes = source.rx_discarded_bytes;
    diagnostics->uart_overrun_error_count =
        source.uart_overrun_error_count;
    diagnostics->uart_framing_error_count =
        source.uart_framing_error_count;
    diagnostics->uart_noise_error_count = source.uart_noise_error_count;
    diagnostics->uart_parity_error_count = source.uart_parity_error_count;
    diagnostics->dma_error_count = source.dma_error_count;
    diagnostics->rx_restart_count = source.rx_restart_count;
    diagnostics->rx_restart_failure_count = source.rx_restart_failure_count;
    diagnostics->rx_discontinuity_count = source.rx_discontinuity_count;
    diagnostics->transport_error_count = source.transport_error_count;
    diagnostics->rx_active = source.rx_active;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemConsoleDevice_Read(uint8_t *data,
                                             uint16_t capacity,
                                             uint16_t *length)
{
    uint16_t read_length;

    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *length = 0U;
    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    read_length = ConsoleUart_Read(data, capacity);
    if (read_length == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *length = read_length;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemConsoleDevice_Write(const uint8_t *data,
                                              uint16_t length)
{
    if ((data == NULL) || (length == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    return (ConsoleUart_Write(data, length) == length) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
