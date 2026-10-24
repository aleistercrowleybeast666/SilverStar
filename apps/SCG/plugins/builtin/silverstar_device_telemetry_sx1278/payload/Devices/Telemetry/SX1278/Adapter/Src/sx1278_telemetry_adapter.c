#include "sx1278_instance.h"
#include "sx1278_device.h"
#include "air_link_config.h"
#include "platform_time.h"
#include <stddef.h>
#include <string.h>

static SystemDeviceResult Sx1278Telemetry_Result(Sx1278Result result)
{
    switch (result)
    {
        case Sx1278Result_Ok: return SYSTEM_DEVICE_OK;
        case Sx1278Result_Busy: return SYSTEM_DEVICE_BUSY;
        case Sx1278Result_Empty: return SYSTEM_DEVICE_NOT_READY;
        case Sx1278Result_Invalid: return SYSTEM_DEVICE_INVALID_ARGUMENT;
        case Sx1278Result_Offline: return SYSTEM_DEVICE_OFFLINE;
        case Sx1278Result_Timeout: return SYSTEM_DEVICE_TIMEOUT;
        case Sx1278Result_NotPresent: return SYSTEM_DEVICE_NOT_PRESENT;
        case Sx1278Result_Io: return SYSTEM_DEVICE_IO_ERROR;
        default: return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
}

const char *Sx1278TelemetryInstance_NameGet(uint8_t instance)
{
    (void)instance; return "E32-400M20S experimental transport";
}

SystemDeviceResult Sx1278TelemetryInstance_Init(uint8_t instance)
{
    Sx1278Result result = Sx1278_Init(instance);
    return (result == Sx1278Result_Busy) ? SYSTEM_DEVICE_ALREADY_MATCHED : Sx1278Telemetry_Result(result);
}

SystemDeviceResult Sx1278TelemetryInstance_Start(uint8_t instance)
{
    return Sx1278Telemetry_Result(Sx1278_Start(instance));
}

SystemDeviceResult Sx1278TelemetryInstance_Stop(uint8_t instance)
{
    Sx1278Result result = Sx1278_Stop(instance);
    return Sx1278Telemetry_Result((result == Sx1278Result_Ok) ?
        Sx1278_StopStatusGet(instance) : result);
}

SystemDeviceResult Sx1278TelemetryInstance_Send(uint8_t instance,
    const uint8_t *data, uint16_t length)
{
    Sx1278Result result = Sx1278_Send(instance, data, length, 0U, NULL);
    return (result == Sx1278Result_Busy) ? SYSTEM_DEVICE_NOT_READY : Sx1278Telemetry_Result(result);
}

SystemDeviceResult Sx1278TelemetryInstance_SendControl(uint8_t instance,
    const uint8_t *data, uint16_t length, uint32_t *transaction_id)
{
    Sx1278Result result = Sx1278_Send(instance, data, length, 1U, transaction_id);
    return (result == Sx1278Result_Busy) ? SYSTEM_DEVICE_NOT_READY : Sx1278Telemetry_Result(result);
}

SystemDeviceResult Sx1278TelemetryInstance_TxResultGet(uint8_t instance,
    uint32_t transaction_id, uint32_t *age_ms)
{
    return Sx1278Telemetry_Result(Sx1278_ReceiptGet(instance, transaction_id, age_ms));
}

SystemDeviceResult Sx1278TelemetryInstance_Receive(uint8_t instance,
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    return Sx1278Telemetry_Result(Sx1278_Receive(instance, data, capacity, length));
}

SystemDeviceResult Sx1278TelemetryInstance_Process(uint8_t instance)
{
    return Sx1278Telemetry_Result(Sx1278_Process(instance));
}

SystemDeviceResult Sx1278TelemetryInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    Sx1278Stats stats;
    if ((mask == NULL) || (Sx1278_StatsGet(instance, &stats) != Sx1278Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_TELEM_CAP_TX | SYSTEM_TELEM_CAP_RX |
        SYSTEM_TELEM_CAP_PACKET_BOUNDARY | SYSTEM_TELEM_CAP_LINK_CRC;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Sx1278TelemetryInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    SystemDeviceResult result;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = Sx1278TelemetryInstance_CapabilitiesGet(instance, &info->capability_mask);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    info->device_name = "E32-400M20S"; info->model_name = "E32-400M20S HARDWARE_UNVERIFIED";
    info->driver_version = "0.1.0"; info->configuration_mask = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Sx1278TelemetryInstance_HealthGet(uint8_t instance, SystemTelemetryHealth *health)
{
    Sx1278Stats stats;
    if ((health == NULL) || (Sx1278_StatsGet(instance, &stats) != Sx1278Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = stats.initialized; health->started = stats.started; health->healthy = stats.ready;
    health->online = (uint8_t)((stats.ready != 0U) && (stats.rx_ok != 0U) &&
        ((uint32_t)(PlatformTime_Ms() - stats.last_rx_ms) <= 3000U));
    health->transmit_packet_count = stats.tx_ok; health->receive_packet_count = stats.rx_ok;
    health->transmit_timeout_count = stats.tx_timeout; health->transmit_error_count = stats.tx_dropped;
    health->receive_error_count = stats.rx_dropped; health->integrity_error_count = stats.rx_crc_error;
    health->last_transmit_timestamp_us = stats.last_tx_us;
    health->last_receive_timestamp_us = stats.last_rx_us;
    /* Capability mask declares both metrics unsupported; values are not measurements. */
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Sx1278TelemetryInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    Sx1278Stats stats;
    if ((diagnostics == NULL) || (Sx1278_StatsGet(instance, &stats) != Sx1278Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    /* Module GPIO, mode-readback and SPI faults share this result path.
     * Report the known aggregate instead of claiming per-SPI attribution. */
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT | SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS |
        SYSTEM_DEVICE_IO_VALID_TIMEOUTS | SYSTEM_DEVICE_IO_VALID_INTEGRITY_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask; diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_SPI;
    diagnostics->transport_error_count = stats.transport_error;
    diagnostics->timeout_count = stats.bus_timeout + stats.tx_timeout;
    diagnostics->integrity_error_count = stats.rx_crc_error;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Sx1278TelemetryInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    Sx1278Stats stats;
    if ((result == NULL) || (Sx1278_StatsGet(instance, &stats) != Sx1278Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result)); result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Sx1278TelemetryInstance_MtuGet(uint8_t instance, uint16_t *mtu)
{
    Sx1278Stats stats;
    if ((mtu == NULL) || (Sx1278_StatsGet(instance, &stats) != Sx1278Result_Ok))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mtu = AIR_LINK_PACKET_MTU; return SYSTEM_DEVICE_OK;
}
