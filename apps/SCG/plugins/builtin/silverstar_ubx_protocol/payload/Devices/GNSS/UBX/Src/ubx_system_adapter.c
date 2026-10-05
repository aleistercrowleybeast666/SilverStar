#include "ubx_system_adapter.h"
#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>
#include "platform_time.h"
#include "platform_critical.h"
#include "system_gnss_quality.h"

#define UBX_ADAPTER_TX_TIMEOUT_MS 20U
#define UBX_ADAPTER_STALE_US 1500000U
#define UBX_ADAPTER_CONFIG_MASK (SYSTEM_GNSS_CFG_NAVIGATION_RATE | \
    SYSTEM_GNSS_CFG_CONSTELLATIONS | SYSTEM_GNSS_CFG_DYNAMIC_MODEL | SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL | \
    SYSTEM_GNSS_CFG_ENABLED_MESSAGES)
#define UBX_ADAPTER_SAMPLE_FIELDS (SYSTEM_GNSS_FIELD_FIX_TYPE | \
    SYSTEM_GNSS_FIELD_FIX_OK | SYSTEM_GNSS_FIELD_SATELLITE_COUNT | \
    SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HEIGHT | \
    SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY | SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY | \
    SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL | SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL | \
    SYSTEM_GNSS_FIELD_SPEED_ACCURACY)

static UbxReceiverResult UbxSystemAdapter_Send(void *context,
    const uint8_t *frame, uint16_t length)
{
    UbxSystemAdapter *adapter = context;
    if (adapter == NULL) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    return (PlatformUart_Write(adapter->uart, frame, length,
        UBX_ADAPTER_TX_TIMEOUT_MS) == PLATFORM_OK) ? UBX_RECEIVER_OK : UBX_RECEIVER_IO_ERROR;
}

static UbxReceiverResult UbxSystemAdapter_BaudSet(void *context, uint32_t baud)
{
    UbxSystemAdapter *adapter = context;
    if (adapter == NULL) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    if (PlatformUart_BaudSet(adapter->uart, baud) != PLATFORM_OK)
    {
        return UBX_RECEIVER_IO_ERROR;
    }
    return (PlatformUart_RxFlush(adapter->uart) == PLATFORM_OK) ?
        UBX_RECEIVER_OK : UBX_RECEIVER_IO_ERROR;
}

SystemDeviceResult UbxSystemAdapter_Init(UbxSystemAdapter *adapter,
    PlatformUartId uart, UbxReceiverModel model)
{
    UbxReceiverPort port;
    PlatformResult result;
    if ((adapter == NULL) || (uart >= PLATFORM_UART_COUNT))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(adapter, 0, sizeof(*adapter));
    adapter->uart = uart;
    result = PlatformUart_Init(uart);
    if ((result != PLATFORM_OK) && (result != PLATFORM_ALREADY_INITIALIZED))
    {
        return SYSTEM_DEVICE_IO_ERROR;
    }
    port.context = adapter;
    port.send = UbxSystemAdapter_Send;
    port.set_baud = UbxSystemAdapter_BaudSet;
    /* Persistent writes are explicit maintenance transactions. Normal startup
     * configures/verifies RAM and never guesses whether NVM differs. */
    if (UbxReceiver_Init(&adapter->receiver, &port, model, 1U,
        UBX_RECEIVER_LAYER_RAM, PlatformTime_Us()) != UBX_RECEIVER_BUSY)
    {
        return SYSTEM_DEVICE_IO_ERROR;
    }
    adapter->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult UbxSystemAdapter_ProcessOwned(UbxSystemAdapter *adapter)
{
    uint8_t bytes[UBX_RECEIVER_INPUT_MAX];
    uint16_t count = 0U;
    UbxReceiverResult result;
    uint64_t now_us;
    if ((adapter == NULL) || (adapter->started == 0U)) { return SYSTEM_DEVICE_NOT_READY; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    PlatformUart_Process(adapter->uart);
    if (PlatformUart_Read(adapter->uart, bytes, sizeof(bytes), &count) != PLATFORM_OK)
    {
        adapter->health.error_count++;
        return SYSTEM_DEVICE_IO_ERROR;
    }
    now_us = PlatformTime_Us();
    if (count != 0U)
    {
        result = UbxReceiver_Feed(&adapter->receiver, bytes, count, now_us);
        if ((result != UBX_RECEIVER_OK) && (result != UBX_RECEIVER_BUSY) &&
            (result != UBX_RECEIVER_DUPLICATE_EPOCH)) { adapter->health.error_count++; }
    }
    result = UbxReceiver_Process(&adapter->receiver, now_us);
    if ((result != UBX_RECEIVER_OK) && (result != UBX_RECEIVER_BUSY))
    {
        adapter->health.healthy = 0U;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        adapter->health.sample_count = adapter->receiver.latest.sequence;
        adapter->health.last_receive_timestamp_us = adapter->receiver.latest.receive_timestamp_us;
        adapter->health.last_sample_timestamp_us = adapter->receiver.latest.receive_timestamp_us;
        adapter->health.online = adapter->receiver.latest.sequence != 0U;
        adapter->health.healthy = adapter->receiver.state == UBX_RECEIVER_READY;
        adapter->health.checksum_error_count = adapter->receiver.checksum_errors;
        adapter->published = adapter->receiver.latest;
        PlatformCritical_Exit(lock);
    }
    return (result == UBX_RECEIVER_OK) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult UbxSystemAdapter_Process(UbxSystemAdapter *adapter)
{
    PlatformCriticalState lock;
    SystemDeviceResult result;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if ((adapter->io_busy != 0U) || (adapter->maintenance_owner != 0U))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_NOT_READY; }
    adapter->io_busy = 1U;
    PlatformCritical_Exit(lock);
    result = UbxSystemAdapter_ProcessOwned(adapter);
    lock = PlatformCritical_Enter();
    adapter->io_busy = 0U;
    PlatformCritical_Exit(lock);
    return result;
}

SystemDeviceResult UbxSystemAdapter_SampleGet(UbxSystemAdapter *adapter,
    SystemGnssSample *sample)
{
    UbxReceiverSample snapshot;
    const UbxReceiverSample *raw = &snapshot;
    uint8_t axis;
    uint64_t now_us = PlatformTime_Us();
    if ((adapter == NULL) || (sample == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        snapshot = adapter->published;
        PlatformCritical_Exit(lock);
    }
    if ((raw->sequence == 0U) || (adapter->receiver.state != UBX_RECEIVER_READY))
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    memset(sample, 0, sizeof(*sample));
    /* Native iTOW remains in receiver.latest and TimeGet. No PPS-to-MCU mapping
     * is claimed: the existing scheduler receives an explicitly untrusted
     * receive-time fallback, never a fake precise sample timestamp. */
    sample->sample_timestamp_us = raw->receive_timestamp_us;
    sample->receive_timestamp_us = raw->receive_timestamp_us;
    sample->measurement_timestamp_trusted = 0U;
    sample->sequence = raw->sequence;
    sample->supported_fields = UBX_ADAPTER_SAMPLE_FIELDS;
    sample->valid_fields = UBX_ADAPTER_SAMPLE_FIELDS;
    sample->latitude_e7 = raw->latitude_e7;
    sample->longitude_e7 = raw->longitude_e7;
    sample->ellipsoid_height_mm = raw->height_ellipsoid_mm;
    sample->msl_height_mm = raw->height_msl_mm;
    sample->horizontal_accuracy_m = (float)raw->hacc_mm * 0.001F;
    sample->vertical_accuracy_m = (float)raw->vacc_mm * 0.001F;
    sample->speed_accuracy_mps = (float)raw->sacc_mmps * 0.001F;
    for (axis = 0U; axis < 3U; axis++)
    {
        sample->velocity_enu_mps[axis] = (float)raw->velocity_enu_mmps[axis] * 0.001F;
        sample->velocity_variance_m2ps2[axis] =
            sample->speed_accuracy_mps * sample->speed_accuracy_mps;
    }
    sample->fix_type = raw->fix_type;
    sample->fix_ok = (raw->flags & 1U) != 0U;
    sample->satellite_count = raw->satellites;
    sample->velocity_valid_mask = raw->valid_solution != 0U ?
        SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N | SYSTEM_GNSS_VEL_VALID_U : 0U;
    sample->online = (now_us >= raw->receive_timestamp_us) &&
        (now_us - raw->receive_timestamp_us <= UBX_ADAPTER_STALE_US);
    return SystemGnssQuality_Evaluate(sample, now_us);
}

static SystemDeviceResult UbxSystemAdapter_ProfileConfigGet(UbxSystemAdapter *adapter,
    SystemGnssConfig *config)
{
    if ((adapter == NULL) || (config == NULL) || (adapter->receiver.profile == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    memset(config, 0, sizeof(*config));
    config->requested_mask = UBX_ADAPTER_CONFIG_MASK;
    config->navigation_rate_hz = 1000U / adapter->receiver.profile->measurement_ms;
    config->constellation_mask = adapter->receiver.profile->constellation_mask;
    config->dynamic_model = (adapter->receiver.profile->dynamic_model == 8U) ?
        SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G : SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE;
    config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    config->enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    return SYSTEM_DEVICE_OK;
}

static uint32_t UbxSystemAdapter_ReadbackMaskGet(const UbxReceiver *receiver)
{
    uint16_t items = receiver->readback.valid_items;
    uint16_t signal_items = receiver->profile->glonass_supported != 0U ? 0x0780U : 0x0380U;
    uint32_t mask = 0U;
    if ((items & 0x0800U) != 0U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_BAUD; }
    if ((items & 0x0048U) == 0x0048U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_RATE; }
    if ((items & 0x0020U) != 0U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_DYNAMIC; }
    if ((items & signal_items) == signal_items) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_CONSTELLATIONS; }
    if ((items & 0x0001U) != 0U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_PROTOCOL_IN; }
    if ((items & 0x0006U) == 0x0006U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_PROTOCOL_OUT; }
    if ((items & 0x0010U) != 0U) { mask |= SYSTEM_GNSS_HW_CONFIG_VALID_NAV_PVT; }
    return mask;
}

static void UbxSystemAdapter_ReadbackCopy(const UbxReceiver *receiver,
    SystemGnssHardwareConfig *config)
{
    const UbxReceiverReadback *actual = &receiver->readback;
    uint32_t period_ms = (uint32_t)actual->measurement_ms * actual->navigation_cycles;
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssHardwareConfig, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(config, 0, sizeof(*config));
    config->valid_mask = UbxSystemAdapter_ReadbackMaskGet(receiver);
    config->baudrate = actual->baud;
    config->constellation_mask = actual->constellation_mask;
    if ((period_ms != 0U) && ((1000U % period_ms) == 0U))
    { config->navigation_rate_hz = (uint16_t)(1000U / period_ms); }
    else { config->valid_mask &= ~SYSTEM_GNSS_HW_CONFIG_VALID_RATE; }
    switch (actual->dynamic_model)
    {
        case 0U: config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE; break;
        case 2U: config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY; break;
        case 6U: config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G; break;
        case 7U: config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G; break;
        case 8U: config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G; break;
        default: config->valid_mask &= ~SYSTEM_GNSS_HW_CONFIG_VALID_DYNAMIC; break;
    }
    if (actual->protocol_out == 1U) { config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX; }
    else if (actual->protocol_out == 2U) { config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA; }
    else if (actual->protocol_out == 3U) { config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA; }
    else { config->valid_mask &= ~SYSTEM_GNSS_HW_CONFIG_VALID_PROTOCOL_OUT; }
    config->protocol_in = actual->protocol_in;
    config->nav_pvt_rate = actual->nav_pvt_rate;
    config->nav_pvt_known = (config->valid_mask & SYSTEM_GNSS_HW_CONFIG_VALID_NAV_PVT) != 0U;
    config->transaction_id = receiver->read_transaction_id;
    config->response_length = actual->response_length;
    config->received_class = actual->response_class; config->received_id = actual->response_id;
    config->response_version = actual->response_version;
    config->read_result = SYSTEM_GNSS_CONFIG_READ_NOT_READY;
    config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_NOT_READY;
}

SystemDeviceResult UbxSystemAdapter_ConfigGet(UbxSystemAdapter *adapter,
    SystemGnssConfig *config)
{
    SystemGnssHardwareConfig actual;
    if ((adapter == NULL) || (config == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(config, 0, sizeof(*config));
    if (adapter->receiver.state != UBX_RECEIVER_READY)
    { return SYSTEM_DEVICE_NOT_READY; }
    UbxSystemAdapter_ReadbackCopy(&adapter->receiver, &actual);
    if ((actual.valid_mask & 0x007FU) != 0x007FU) { return SYSTEM_DEVICE_NOT_READY; }
    config->requested_mask = UBX_ADAPTER_CONFIG_MASK;
    config->navigation_rate_hz = actual.navigation_rate_hz;
    config->constellation_mask = actual.constellation_mask;
    config->dynamic_model = actual.dynamic_model;
    config->output_protocol = actual.output_protocol;
    config->enabled_message_mask = actual.nav_pvt_rate != 0U ? SYSTEM_GNSS_MESSAGE_NAV_PVT : 0U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult UbxSystemAdapter_ConfigValidate(UbxSystemAdapter *adapter,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    SystemGnssConfig actual;
    uint32_t mismatch = 0U;
    if ((config == NULL) || (report == NULL) ||
        (UbxSystemAdapter_ProfileConfigGet(adapter, &actual) != SYSTEM_DEVICE_OK))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->owner_active != 0U) { return SYSTEM_DEVICE_BUSY; }
    memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = UBX_ADAPTER_CONFIG_MASK;
    report->unsupported_required_mask = config->required_mask & ~UBX_ADAPTER_CONFIG_MASK;
    report->unsupported_optional_mask = config->requested_mask & ~UBX_ADAPTER_CONFIG_MASK;
    if (config->navigation_rate_hz != actual.navigation_rate_hz) { mismatch |= SYSTEM_GNSS_CFG_NAVIGATION_RATE; }
    if (config->constellation_mask != actual.constellation_mask) { mismatch |= SYSTEM_GNSS_CFG_CONSTELLATIONS; }
    if (config->dynamic_model != actual.dynamic_model) { mismatch |= SYSTEM_GNSS_CFG_DYNAMIC_MODEL; }
    if (config->output_protocol != actual.output_protocol) { mismatch |= SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL; }
    if (config->enabled_message_mask != actual.enabled_message_mask) { mismatch |= SYSTEM_GNSS_CFG_ENABLED_MESSAGES; }
    report->failed_mask = mismatch & config->requested_mask;
    if ((report->failed_mask != 0U) || (report->unsupported_required_mask != 0U))
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult UbxSystemAdapter_ConfigCheck(UbxSystemAdapter *adapter,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    SystemGnssConfig actual;
    SystemDeviceResult result = UbxSystemAdapter_ConfigValidate(adapter, config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    result = UbxSystemAdapter_ConfigGet(adapter, &actual);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if ((config->navigation_rate_hz != actual.navigation_rate_hz) ||
        (config->constellation_mask != actual.constellation_mask) ||
        (config->dynamic_model != actual.dynamic_model) ||
        (config->output_protocol != actual.output_protocol) ||
        (config->enabled_message_mask != actual.enabled_message_mask))
    { report->verify_failed_mask = config->requested_mask; return SYSTEM_DEVICE_VERIFY_FAILED; }
    report->matched_mask = config->requested_mask & UBX_ADAPTER_CONFIG_MASK;
    report->success = 1U;
    return SYSTEM_DEVICE_ALREADY_MATCHED;
}

SystemDeviceResult UbxSystemAdapter_ConfigApply(UbxSystemAdapter *adapter,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    uint32_t attempt;
    SystemDeviceResult result = UbxSystemAdapter_ConfigValidate(adapter, config, report);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (adapter->started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    for (attempt = 0U; attempt < 5000U; attempt++)
    {
        if (adapter->receiver.state == UBX_RECEIVER_READY)
        {
            result = UbxSystemAdapter_ConfigCheck(adapter, config, report);
            report->applied_mask = report->matched_mask;
            return result;
        }
        result = UbxSystemAdapter_Process(adapter);
        if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_NOT_READY))
        { report->failed_mask = config->requested_mask; return result; }
        PlatformTime_DelayMs(1U);
    }
    report->failed_mask = config->requested_mask;
    return SYSTEM_DEVICE_TIMEOUT;
}

static SystemDeviceResult UbxSystemAdapter_MaintenanceBegin(UbxSystemAdapter *adapter)
{
    PlatformCriticalState lock;
    if (adapter == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if ((adapter->owner_active != 0U) || (adapter->io_busy != 0U) ||
        (adapter->maintenance_owner != 0U))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_BUSY; }
    if ((adapter->started == 0U) || (adapter->receiver.state != UBX_RECEIVER_READY))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_NOT_READY; }
    adapter->maintenance_owner = 1U;
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult UbxSystemAdapter_MaintenanceWait(UbxSystemAdapter *adapter)
{
    uint32_t attempt;
    SystemDeviceResult result = SYSTEM_DEVICE_TIMEOUT;
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (attempt = 0U; attempt < 5000U; attempt++)
    {
        result = UbxSystemAdapter_ProcessOwned(adapter);
        if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_NOT_READY)) { break; }
        if (adapter->receiver.state == UBX_RECEIVER_READY) { break; }
        PlatformTime_DelayMs(1U);
    }
    if (attempt == 5000U)
    {
        adapter->receiver.state = UBX_RECEIVER_FAILED;
        adapter->receiver.result = UBX_RECEIVER_TIMEOUT;
        result = SYSTEM_DEVICE_TIMEOUT;
    }
    return result;
}

static void UbxSystemAdapter_MaintenanceEnd(UbxSystemAdapter *adapter)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    adapter->maintenance_owner = 0U;
    PlatformCritical_Exit(lock);
}

static void UbxSystemAdapter_ReadResultCopy(const UbxReceiver *receiver,
    SystemDeviceResult result, SystemGnssHardwareConfig *config)
{
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssHardwareConfig, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((result == SYSTEM_DEVICE_OK) || (receiver->result == UBX_RECEIVER_VERIFY_FAILED))
    {
        /* A valid response containing a different value is a verification
         * failure, while its actual value remains useful diagnostic evidence. */
        config->read_result = SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK;
        config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK;
    }
    else if (receiver->result == UBX_RECEIVER_TIMEOUT)
    { config->read_result = SYSTEM_GNSS_CONFIG_READ_TIMEOUT; config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT; }
    else if (receiver->result == UBX_RECEIVER_NAK)
    {
        config->read_result = SYSTEM_GNSS_CONFIG_READ_NAK;
        config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_NAK;
        config->nak_class = receiver->payload[0]; config->nak_id = receiver->payload[1];
    }
    else if (receiver->result == UBX_RECEIVER_BAD_FRAME)
    { config->read_result = SYSTEM_GNSS_CONFIG_READ_MALFORMED_RESPONSE; config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LENGTH; }
    else if (receiver->result == UBX_RECEIVER_IO_ERROR)
    { config->read_result = SYSTEM_GNSS_CONFIG_READ_IO_ERROR; config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_TX_ERROR; }
}

SystemDeviceResult UbxSystemAdapter_HardwareConfigRead(UbxSystemAdapter *adapter,
    SystemGnssHardwareConfig *config)
{
    uint64_t start_us;
    SystemDeviceResult result;
    if ((adapter == NULL) || (config == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(config, 0, sizeof(*config));
    config->read_result = SYSTEM_GNSS_CONFIG_READ_NOT_READY;
    result = UbxSystemAdapter_MaintenanceBegin(adapter);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    start_us = PlatformTime_Us();
    if (UbxReceiver_ConfigReadStart(&adapter->receiver, start_us) != UBX_RECEIVER_BUSY)
    { UbxSystemAdapter_MaintenanceEnd(adapter); return SYSTEM_DEVICE_BAD_STATE; }
    result = UbxSystemAdapter_MaintenanceWait(adapter);
    UbxSystemAdapter_ReadbackCopy(&adapter->receiver, config);
    UbxSystemAdapter_ReadResultCopy(&adapter->receiver, result, config);
    config->elapsed_ms = (uint32_t)((PlatformTime_Us() - start_us) / 1000U);
    UbxSystemAdapter_MaintenanceEnd(adapter);
    return result;
}

SystemDeviceResult UbxSystemAdapter_ConfigPersist(UbxSystemAdapter *adapter,
    uint8_t persistent_layer, SystemDeviceConfigReport *report)
{
    UbxReceiverResult start_result;
    SystemDeviceResult result;
    if ((adapter == NULL) || (report == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(report, 0, sizeof(*report));
    report->requested_mask = UBX_ADAPTER_CONFIG_MASK;
    report->supported_mask = UBX_ADAPTER_CONFIG_MASK;
    result = UbxSystemAdapter_MaintenanceBegin(adapter);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    start_result = UbxReceiver_ConfigPersistStart(&adapter->receiver, persistent_layer, PlatformTime_Us());
    if (start_result != UBX_RECEIVER_BUSY)
    {
        UbxSystemAdapter_MaintenanceEnd(adapter);
        return start_result == UBX_RECEIVER_UNSUPPORTED_LAYER ? SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_BAD_STATE;
    }
    result = UbxSystemAdapter_MaintenanceWait(adapter);
    if ((result == SYSTEM_DEVICE_OK) && (adapter->receiver.persistent_verified != 0U))
    {
        report->matched_mask = UBX_ADAPTER_CONFIG_MASK;
        report->persisted = 1U; report->success = 1U;
    }
    else { report->failed_mask = UBX_ADAPTER_CONFIG_MASK; }
    UbxSystemAdapter_MaintenanceEnd(adapter);
    return result;
}

SystemDeviceResult UbxSystemAdapter_LastConfigReportGet(UbxSystemAdapter *adapter,
    SystemGnssConfigTransactionReport *report)
{
    SystemGnssHardwareConfig actual;
    SystemGnssConfig effective;
    SystemDeviceResult result;
    if ((adapter == NULL) || (report == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(adapter, UbxSystemAdapter, SILVERSTAR_ASSERT_MODULE_DEVICE);
    memset(report, 0, sizeof(*report));
    /* This compact implementation retains readback evidence, not an invented
     * history of write/settle/recovery stages. Unrecorded stages stay explicit. */
    report->uart_baudrate_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->uart_settle_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->protocol_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->nav_pvt_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->rate_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->dynamic_model_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->signals_result = SYSTEM_DEVICE_NOT_EXECUTED;
    report->pvt_recovery_result = SYSTEM_DEVICE_NOT_EXECUTED;
    result = UbxSystemAdapter_ConfigGet(adapter, &effective);
    UbxSystemAdapter_ReadbackCopy(&adapter->receiver, &actual);
    UbxSystemAdapter_ReadResultCopy(&adapter->receiver, result, &actual);
    report->verify_result = result;
    report->verify_valid_mask = actual.valid_mask;
    report->verify_read_result = actual.read_result;
    report->verify_detailed_result = actual.detailed_result;
    report->verify_response_length = actual.response_length;
    report->verify_received_class = actual.received_class;
    report->verify_received_id = actual.received_id;
    report->verify_response_version = actual.response_version;
    report->failed_stage = result == SYSTEM_DEVICE_OK ? SYSTEM_GNSS_CONFIG_STAGE_NONE : SYSTEM_GNSS_CONFIG_STAGE_VERIFY;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult UbxSystemAdapter_HealthGet(UbxSystemAdapter *adapter,
    SystemDeviceHealth *health)
{
    uint64_t now_us = PlatformTime_Us();
    if ((adapter == NULL) || (health == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        *health = adapter->health;
        PlatformCritical_Exit(lock);
    }
    if ((health->sample_count == 0U) || (now_us < health->last_receive_timestamp_us) ||
        (now_us - health->last_receive_timestamp_us > UBX_ADAPTER_STALE_US))
    {
        health->healthy = 0U;
        health->online = 0U;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult UbxSystemAdapter_TimeGet(UbxSystemAdapter *adapter,
    SystemGnssTime *time)
{
    PlatformCriticalState lock;
    if ((adapter == NULL) || (time == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(time, 0, sizeof(*time));
    lock = PlatformCritical_Enter();
    time->time_of_week_ms = adapter->published.itow_ms;
    time->receive_timestamp_us = adapter->published.receive_timestamp_us;
    time->sequence = adapter->published.sequence;
    PlatformCritical_Exit(lock);
    return (time->sequence != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
