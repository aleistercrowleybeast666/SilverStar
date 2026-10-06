#include "nrf24_instance.h"
#include "nrf24_device.h"
#include "air_link_config.h"
#include "platform_time.h"
#include <stddef.h>
#include <string.h>

static SystemDeviceResult Nrf24Telemetry_Result(Nrf24Result result)
{
    switch (result)
    {
        case Nrf24Result_Ok: return SYSTEM_DEVICE_OK;
        case Nrf24Result_Busy: return SYSTEM_DEVICE_BUSY;
        case Nrf24Result_Empty: return SYSTEM_DEVICE_NOT_READY;
        case Nrf24Result_Invalid: return SYSTEM_DEVICE_INVALID_ARGUMENT;
        case Nrf24Result_Offline: return SYSTEM_DEVICE_OFFLINE;
        case Nrf24Result_Timeout: return SYSTEM_DEVICE_TIMEOUT;
        case Nrf24Result_NotPresent: return SYSTEM_DEVICE_NOT_PRESENT;
        case Nrf24Result_Io: return SYSTEM_DEVICE_IO_ERROR;
        default: return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
}

const char *Nrf24TelemetryInstance_NameGet(uint8_t instance)
{
    (void)instance; return "NRF24L01+ paired transport";
}

SystemDeviceResult Nrf24TelemetryInstance_Init(uint8_t instance)
{
    Nrf24Result result = Nrf24_Init(instance);
    return (result == Nrf24Result_Busy) ? SYSTEM_DEVICE_ALREADY_MATCHED : Nrf24Telemetry_Result(result);
}

SystemDeviceResult Nrf24TelemetryInstance_Start(uint8_t instance)
{
    return Nrf24Telemetry_Result(Nrf24_Start(instance));
}

SystemDeviceResult Nrf24TelemetryInstance_Stop(uint8_t instance)
{
    return Nrf24Telemetry_Result(Nrf24_Stop(instance));
}

SystemDeviceResult Nrf24TelemetryInstance_Send(uint8_t instance,
    const uint8_t *data, uint16_t length)
{
    Nrf24Result result = Nrf24_Send(instance, data, length, 0U, NULL);
    return (result == Nrf24Result_Busy) ? SYSTEM_DEVICE_NOT_READY : Nrf24Telemetry_Result(result);
}

SystemDeviceResult Nrf24TelemetryInstance_SendControl(uint8_t instance,
    const uint8_t *data, uint16_t length, uint32_t *transaction_id)
{
    Nrf24Result result = Nrf24_Send(instance, data, length, 1U, transaction_id);
    return (result == Nrf24Result_Busy) ? SYSTEM_DEVICE_NOT_READY : Nrf24Telemetry_Result(result);
}

SystemDeviceResult Nrf24TelemetryInstance_TxResultGet(uint8_t instance,
    uint32_t transaction_id, uint32_t *age_ms)
{
    return Nrf24Telemetry_Result(Nrf24_ReceiptGet(instance, transaction_id, age_ms));
}

SystemDeviceResult Nrf24TelemetryInstance_Receive(uint8_t instance,
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    return Nrf24Telemetry_Result(Nrf24_Receive(instance, data, capacity, length));
}

SystemDeviceResult Nrf24TelemetryInstance_Process(uint8_t instance)
{
    Nrf24Stats stats;
    Nrf24_Process(instance);
    return Nrf24Telemetry_Result(Nrf24_StatsGet(instance, &stats));
}

SystemDeviceResult Nrf24TelemetryInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    Nrf24Stats stats;
    if ((mask == NULL) || (Nrf24_StatsGet(instance, &stats) != Nrf24Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_TELEM_CAP_TX | SYSTEM_TELEM_CAP_RX |
        SYSTEM_TELEM_CAP_PACKET_BOUNDARY | SYSTEM_TELEM_CAP_LINK_CRC;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Nrf24TelemetryInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    SystemDeviceResult result;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Nrf24TelemetryInstance_CapabilitiesGet(instance, &info->capability_mask);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    info->device_name = "NRF24L01+"; info->model_name = "NRF24L01+ HARDWARE_UNVERIFIED";
    info->driver_version = "0.1.0"; info->configuration_mask = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Nrf24TelemetryInstance_HealthGet(uint8_t instance, SystemTelemetryHealth *health)
{
    Nrf24Stats stats;
    if ((health == NULL) || (Nrf24_StatsGet(instance, &stats) != Nrf24Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = stats.ready; health->started = stats.ready; health->healthy = stats.ready;
    health->online = (uint8_t)((stats.ready != 0U) && (stats.rx_ok != 0U) &&
        ((uint32_t)(PlatformTime_Ms() - stats.last_rx_ms) <= 3000U));
    health->transmit_packet_count = stats.tx_ok; health->receive_packet_count = stats.rx_ok;
    health->transmit_timeout_count = stats.tx_timeout; health->transmit_error_count = stats.tx_dropped;
    health->receive_error_count = stats.rx_dropped; health->integrity_error_count = stats.integrity_error;
    health->last_transmit_timestamp_us = (uint64_t)stats.last_tx_ms * 1000ULL;
    health->last_receive_timestamp_us = (uint64_t)stats.last_rx_ms * 1000ULL;
    /* Capability mask declares both metrics unsupported; values are not measurements. */
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Nrf24TelemetryInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    Nrf24Stats stats;
    if ((diagnostics == NULL) || (Nrf24_StatsGet(instance, &stats) != Nrf24Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT | SYSTEM_DEVICE_IO_VALID_SPI_ERRORS |
        SYSTEM_DEVICE_IO_VALID_SPI_TIMEOUTS | SYSTEM_DEVICE_IO_VALID_INTEGRITY_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask; diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_SPI;
    diagnostics->spi_error_count = stats.spi_error; diagnostics->spi_timeout_count = stats.spi_timeout;
    diagnostics->integrity_error_count = stats.integrity_error;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Nrf24TelemetryInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    Nrf24Stats stats;
    if ((result == NULL) || (Nrf24_StatsGet(instance, &stats) != Nrf24Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result)); result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Nrf24TelemetryInstance_MtuGet(uint8_t instance, uint16_t *mtu)
{
    Nrf24Stats stats;
    if ((mtu == NULL) || (Nrf24_StatsGet(instance, &stats) != Nrf24Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mtu = AIR_LINK_PACKET_MTU; return SYSTEM_DEVICE_OK;
}
