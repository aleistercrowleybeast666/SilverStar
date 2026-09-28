#include "system_version.h"
#include "system_telemetry_transport_if.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "platform_time.h"
#include "project_resources.h"
#include "silverstar_assert.h"
#include "sx1281_config.h"
#include "sx1281_bus.h"
#include "sx1281_device.h"
#include "sx1281_instance.h"

typedef struct
{
    volatile uint8_t initialized;
    volatile uint8_t started;
    SystemTelemetryHealth health;
    SystemDeviceIoDiagnostics io_diagnostics;
    LoraStats previous_stats;
    Sx1281BusStatus previous_bus_status;
} Sx1281TransportContext;

static Sx1281TransportContext
    s_transport_contexts[PROJECT_SX1281_INSTANCE_COUNT];

_Static_assert(PROJECT_SX1281_INSTANCE_COUNT <=
               PROJECT_SX1281_INSTANCE_COUNT_MAX,
               "SX1281 transport context count exceeds generated resource bound");

#define s_initialized         (s_transport_contexts[instance].initialized)
#define s_started             (s_transport_contexts[instance].started)
#define s_health              (s_transport_contexts[instance].health)
#define s_io_diagnostics      (s_transport_contexts[instance].io_diagnostics)
#define s_previous_stats      (s_transport_contexts[instance].previous_stats)
#define s_previous_bus_status (s_transport_contexts[instance].previous_bus_status)

static void Sx1281Transport_IoDiagnosticsUpdate(uint8_t instance,
    const LoraStats *stats,
    const Sx1281BusStatus *bus_status)
{
    (void)instance;
    if (bus_status == NULL) { return; }
    s_io_diagnostics.transport_error_count = bus_status->spi_error_count;
    s_io_diagnostics.spi_error_count = bus_status->spi_error_count;
    s_io_diagnostics.spi_timeout_count = bus_status->spi_timeout_count;
    s_io_diagnostics.busy_timeout_count = bus_status->busy_timeout_count;
    s_io_diagnostics.timeout_count = bus_status->spi_timeout_count +
        bus_status->busy_timeout_count;
    if (stats != NULL)
    {
        s_io_diagnostics.integrity_error_count = stats->rx_crc_error;
    }
}

static uint32_t Sx1281Transport_IrqLock(uint8_t instance)
{
    (void)instance;
    return PlatformCritical_Enter();
}

static void Sx1281Transport_IrqUnlock(uint8_t instance, uint32_t primask)
{
    (void)instance;
    PlatformCritical_Exit(primask);
}

static SystemDeviceResult Sx1281Transport_Init(uint8_t instance)
{
    (void)instance;
    LoraInitResult init_result;
    LoraChipStatus chip_status;
    Sx1281BusStatus bus_status;
    uint32_t primask;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_started <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    primask = Sx1281Transport_IrqLock(instance);
    (void)memset(&s_health, 0, sizeof(s_health));
    (void)memset(&s_previous_stats, 0, sizeof(s_previous_stats));
    (void)memset(&s_previous_bus_status, 0, sizeof(s_previous_bus_status));
    (void)memset(&s_io_diagnostics, 0, sizeof(s_io_diagnostics));
    s_io_diagnostics.supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT |
        SYSTEM_DEVICE_IO_VALID_INTEGRITY_ERRORS |
        SYSTEM_DEVICE_IO_VALID_TIMEOUTS |
        SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS |
        SYSTEM_DEVICE_IO_VALID_SPI_ERRORS |
        SYSTEM_DEVICE_IO_VALID_SPI_TIMEOUTS |
        SYSTEM_DEVICE_IO_VALID_BUSY_TIMEOUTS;
    s_io_diagnostics.valid_mask = s_io_diagnostics.supported_mask;
    s_io_diagnostics.transport_type = SYSTEM_DEVICE_TRANSPORT_SPI;
    s_io_diagnostics.owner = SYSTEM_DEVICE_IO_OWNER_SELF;
    Sx1281Transport_IrqUnlock(instance, primask);
    init_result = Lora_Init(instance);
    Sx1281Bus_StatusGet(instance, &bus_status);
    Sx1281Transport_IoDiagnosticsUpdate(instance, NULL, &bus_status);
    if (init_result != LORA_INIT_OK)
    {
        return ((bus_status.busy_timeout_count != 0U) ||
                (bus_status.spi_timeout_count != 0U)) ?
            SYSTEM_DEVICE_TIMEOUT : SYSTEM_DEVICE_IO_ERROR;
    }
    if ((Lora_ChipStatusGet(instance, &chip_status) != LORA_DIAG_RESULT_OK) ||
        (chip_status.verified == 0U))
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    primask = Sx1281Transport_IrqLock(instance);
    s_initialized = 1U;
    s_health.initialized = 1U;
    s_health.healthy = 1U;
    s_previous_bus_status = bus_status;
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_Start(uint8_t instance)
{
    (void)instance;
    Sx1281BusStatus before;
    Sx1281BusStatus after;
    uint32_t primask;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_started <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_started != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    Sx1281Bus_StatusGet(instance, &before);
    Lora_StartRx(instance);
    Sx1281Bus_StatusGet(instance, &after);
    if ((after.spi_error_count != before.spi_error_count) ||
        (after.spi_timeout_count != before.spi_timeout_count) ||
        (after.busy_timeout_count != before.busy_timeout_count))
    {
        return ((after.busy_timeout_count != before.busy_timeout_count) ||
                (after.spi_timeout_count != before.spi_timeout_count)) ?
            SYSTEM_DEVICE_TIMEOUT : SYSTEM_DEVICE_IO_ERROR;
    }
    primask = Sx1281Transport_IrqLock(instance);
    s_started = 1U;
    s_health.started = 1U;
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_Stop(uint8_t instance)
{
    (void)instance;
    uint32_t primask = Sx1281Transport_IrqLock(instance);

    s_started = 0U;
    s_health.started = 0U;
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_Send(uint8_t instance, const uint8_t *data,
                                                uint16_t length)
{
    (void)instance;
    LoraTxEnqueueResult result;

    if ((data == NULL) || (length == 0U) ||
        (length > LORA_MAX_PAYLOAD_LEN) || (length > UINT8_MAX))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    result = Lora_TxEnqueue(instance, data, (uint8_t)length);
    if (result == LORA_TX_ENQUEUE_OK) { return SYSTEM_DEVICE_OK; }
    if (result == LORA_TX_ENQUEUE_QUEUE_FULL) { return SYSTEM_DEVICE_NOT_READY; }
    if (result == LORA_TX_ENQUEUE_NOT_INIT) { return SYSTEM_DEVICE_OFFLINE; }
    return SYSTEM_DEVICE_INVALID_ARGUMENT;
}

static SystemDeviceResult Sx1281Transport_Receive(uint8_t instance, uint8_t *data,
                                                  uint16_t capacity,
                                                  uint16_t *length)
{
    (void)instance;
    uint8_t packet_length = 0U;
    uint8_t packet[LORA_MAX_PAYLOAD_LEN];
    int8_t rssi = 0;
    int8_t snr = 0;
    LoraRxDequeueResult result;
    uint32_t primask;

    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(data, uint8_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    *length = 0U;
    result = Lora_RxDequeue(instance, packet, &packet_length, &rssi, &snr);
    if (result == LORA_RX_DEQUEUE_EMPTY) { return SYSTEM_DEVICE_NOT_READY; }
    if (result != LORA_RX_DEQUEUE_OK) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (packet_length > capacity)
    {
        primask = Sx1281Transport_IrqLock(instance);
        s_health.receive_error_count++;
        Sx1281Transport_IrqUnlock(instance, primask);
        return SYSTEM_DEVICE_IO_ERROR;
    }
    (void)memcpy(data, packet, packet_length);
    *length = packet_length;
    primask = Sx1281Transport_IrqLock(instance);
    s_health.last_rssi_dbm = rssi;
    s_health.last_snr_q4 = (int8_t)(snr * 4);
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static void Sx1281Transport_HealthStatsApply(uint8_t instance,
    SystemTelemetryHealth *health,
    const LoraStats *stats,
    const LoraStats *previous_stats,
    uint64_t now_us)
{
    (void)instance;
    SILVERSTAR_ASSERT_OBJECT(health, SystemTelemetryHealth,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(stats, LoraStats,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (stats->tx_ok != previous_stats->tx_ok)
    {
        health->last_transmit_timestamp_us = now_us;
    }
    if (stats->rx_ok != previous_stats->rx_ok)
    {
        health->last_receive_timestamp_us = now_us;
    }
    health->transmit_packet_count = stats->tx_ok;
    health->receive_packet_count = stats->rx_ok;
    health->transmit_timeout_count = stats->tx_timeout;
    health->transmit_error_count = stats->tx_timeout + stats->tx_dropped;
    health->receive_error_count = stats->rx_timeout + stats->rx_error +
                                  stats->rx_dropped;
    health->integrity_error_count = stats->rx_crc_error;
    health->last_rssi_dbm = stats->last_rx_rssi;
    health->last_snr_q4 = (int8_t)(stats->last_rx_snr * 4);
}

static void Sx1281Transport_Process(uint8_t instance)
{
    (void)instance;
    LoraStats stats;
    LoraStats previous_stats;
    LoraChipStatus chip_status;
    Sx1281BusStatus bus_status;
    Sx1281BusStatus previous_bus_status;
    SystemTelemetryHealth health;
    uint64_t now_us;
    uint32_t primask;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_started <= 1U,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_started == 0U) { return; }
    (void)memset(&chip_status, 0, sizeof(chip_status));
    Lora_Process(instance);
    Lora_GetStats(instance, &stats);
    now_us = PlatformTime_Us();
    primask = Sx1281Transport_IrqLock(instance);
    previous_stats = s_previous_stats;
    previous_bus_status = s_previous_bus_status;
    health = s_health;
    Sx1281Transport_IrqUnlock(instance, primask);
    Sx1281Transport_HealthStatsApply(instance,
        &health, &stats, &previous_stats, now_us);
    Sx1281Bus_StatusGet(instance, &bus_status);
    if (Lora_ChipStatusGet(instance, &chip_status) != LORA_DIAG_RESULT_OK)
    {
        chip_status.verified = 0U;
    }
    health.online = (uint8_t)((health.last_receive_timestamp_us != 0U) &&
        (now_us >= health.last_receive_timestamp_us) &&
        ((now_us - health.last_receive_timestamp_us) <=
         ((uint64_t)LORA_REMOTE_ONLINE_TIMEOUT_MS * 1000ULL)));
    health.healthy = (uint8_t)((chip_status.verified != 0U) &&
        (bus_status.spi_error_count == previous_bus_status.spi_error_count) &&
        (bus_status.spi_timeout_count ==
         previous_bus_status.spi_timeout_count) &&
        (bus_status.busy_timeout_count ==
         previous_bus_status.busy_timeout_count));
    primask = Sx1281Transport_IrqLock(instance);
    Sx1281Transport_IoDiagnosticsUpdate(instance, &stats, &bus_status);
    s_health = health;
    s_previous_stats = stats;
    s_previous_bus_status = bus_status;
    Sx1281Transport_IrqUnlock(instance, primask);
}

static SystemDeviceResult Sx1281Transport_GetInfo(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "SX1281 Telemetry Transport";
    info->model_name = "E28-2G4M12SX / SX1281";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_TELEM_CAP_TX |
                            SYSTEM_TELEM_CAP_RX |
                            SYSTEM_TELEM_CAP_PACKET_BOUNDARY |
                            SYSTEM_TELEM_CAP_LINK_CRC |
                            SYSTEM_TELEM_CAP_RSSI |
                            SYSTEM_TELEM_CAP_SNR;
    info->configuration_mask = 0U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_GetCapabilities(uint8_t instance, uint32_t *mask)
{
    (void)instance;
    SystemDeviceInfo info;

    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)Sx1281Transport_GetInfo(instance, &info);
    *mask = info.capability_mask;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_GetHealth(uint8_t instance, SystemTelemetryHealth *health)
{
    (void)instance;
    uint32_t primask;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = Sx1281Transport_IrqLock(instance);
    *health = s_health;
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_GetIoDiagnostics(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    (void)instance;
    uint32_t primask;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = Sx1281Transport_IrqLock(instance);
    *diagnostics = s_io_diagnostics;
    Sx1281Transport_IrqUnlock(instance, primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Sx1281Transport_SelfTest(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance;
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Sx1281Transport_GetMtu(uint8_t instance, uint16_t *mtu)
{
    (void)instance;
    if (mtu == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mtu = LORA_MAX_PAYLOAD_LEN;
    return SYSTEM_DEVICE_OK;
}

const char *Sx1281TelemetryInstance_NameGet(uint8_t instance) {
    (void)instance; return "SX1281 Transport"; }
SystemDeviceResult Sx1281TelemetryInstance_Init(uint8_t instance) {
    (void)instance; return Sx1281Transport_Init(instance); }
SystemDeviceResult Sx1281TelemetryInstance_Start(uint8_t instance) {
    (void)instance; return Sx1281Transport_Start(instance); }
SystemDeviceResult Sx1281TelemetryInstance_Stop(uint8_t instance) {
    (void)instance; return Sx1281Transport_Stop(instance); }
SystemDeviceResult Sx1281TelemetryInstance_Send(uint8_t instance, const uint8_t *data, uint16_t length)
{
    (void)instance; return Sx1281Transport_Send(instance, data, length); }
SystemDeviceResult Sx1281TelemetryInstance_Receive(uint8_t instance, uint8_t *data,
                                           uint16_t capacity,
                                           uint16_t *length)
{
    (void)instance; return Sx1281Transport_Receive(instance, data, capacity, length); }
SystemDeviceResult Sx1281TelemetryInstance_Process(uint8_t instance)
{
    Sx1281Transport_Process(instance);
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult Sx1281TelemetryInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance; return Sx1281Transport_GetInfo(instance, info); }
SystemDeviceResult Sx1281TelemetryInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    (void)instance; return Sx1281Transport_GetCapabilities(instance, mask); }
SystemDeviceResult Sx1281TelemetryInstance_HealthGet(uint8_t instance, SystemTelemetryHealth *health)
{
    (void)instance; return Sx1281Transport_GetHealth(instance, health); }
SystemDeviceResult Sx1281TelemetryInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    (void)instance; return Sx1281Transport_GetIoDiagnostics(instance, diagnostics); }
SystemDeviceResult Sx1281TelemetryInstance_SelfTestRun(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance; return Sx1281Transport_SelfTest(instance, result); }
SystemDeviceResult Sx1281TelemetryInstance_MtuGet(uint8_t instance, uint16_t *mtu)
{
    (void)instance; return Sx1281Transport_GetMtu(instance, mtu); }
