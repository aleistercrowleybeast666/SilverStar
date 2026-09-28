#include "system_version.h"
#include "system_gnss_if.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "neo_m9n_build_capabilities.h"
#include "neo_m9n_config.h"
#include "neo_m9n_device.h"
#include "neo_m9n_instance.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "system_gnss_quality.h"
#include "silverstar_assert.h"

typedef struct
{
    volatile uint8_t initialized;
    volatile uint8_t started;
    SystemDeviceHealth health;
    SystemGnssConfig effective_config;
    SystemGnssConfigTransactionReport config_transaction;
} NeoM9nAdapterContext;

static NeoM9nAdapterContext
    s_contexts[PROJECT_NEO_M9N_INSTANCE_COUNT];

#define s_initialized        (s_contexts[instance].initialized)
#define s_started            (s_contexts[instance].started)
#define s_health             (s_contexts[instance].health)
#define s_effective_config   (s_contexts[instance].effective_config)
#define s_config_transaction (s_contexts[instance].config_transaction)

typedef enum
{
    NeoM9nRuntimeRequestNone = 0,
    NeoM9nRuntimeRequestHardwareConfig,
    NeoM9nRuntimeRequestNavSat,
    NeoM9nRuntimeRequestMonRf
} NeoM9nRuntimeRequest;

typedef enum
{
    NeoM9nRuntimeTransactionIdle = 0,
    NeoM9nRuntimeTransactionSubmitted,
    NeoM9nRuntimeTransactionSendRequest,
    NeoM9nRuntimeTransactionWaitResponse,
    NeoM9nRuntimeTransactionProcessResponse,
    NeoM9nRuntimeTransactionNextStep,
    NeoM9nRuntimeTransactionComplete,
    NeoM9nRuntimeTransactionFailed
} NeoM9nRuntimeTransactionState;

typedef union
{
    SystemGnssHardwareConfig hardware_config;
    SystemGnssSatelliteDiagnostics satellite;
    SystemGnssRfDiagnostics rf;
} NeoM9nRuntimeTransactionOutput;

typedef struct
{
    NeoM9nRuntimeTransactionState state;
    NeoM9nRuntimeRequest request;
    uint32_t transaction_id;
    uint32_t next_transaction_id;
    uint32_t start_ms;
    uint32_t timeout_ms;
    uint32_t expected_key;
    SystemDeviceResult result;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t abandoned;
    GnssNeoM9nConfigSnapshot device_config;
    GnssNeoM9nConfigReadDiagnostics device_config_diagnostics;
    GnssNeoM9nConfigReadResult device_config_result;
    uint32_t device_config_elapsed_ms;
    GnssNeoM9nSatelliteDiagnostics device_satellite;
    GnssNeoM9nRfDiagnostics device_rf;
    NeoM9nRuntimeTransactionOutput output;
} NeoM9nRuntimeTransaction;

typedef struct
{
    int device_result;
    uint32_t step_id;
    uint32_t failed_mask;
    uint8_t layers;
} NeoM9nConfigApplyContext;

typedef struct
{
    NeoM9nRuntimeTransactionState state;
    NeoM9nRuntimeRequest request;
    uint32_t transaction_id;
    uint32_t start_ms;
    uint32_t timeout_ms;
    uint8_t abandoned;
} NeoM9nRuntimeTransactionSnapshot;

static volatile uint8_t
    s_runtime_owner_active_contexts[PROJECT_NEO_M9N_INSTANCE_COUNT];
static NeoM9nRuntimeTransaction
    s_runtime_transactions[PROJECT_NEO_M9N_INSTANCE_COUNT];

#define s_runtime_owner_active \
    (s_runtime_owner_active_contexts[instance])
#define s_runtime_transaction (s_runtime_transactions[instance])

static PlatformUartId NeoM9nAdapter_UartGet(uint8_t instance)
{
    ProjectNeoM9nResources resources;

    if (ProjectNeoM9nResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    {
        return (PlatformUartId)PLATFORM_UART_COUNT;
    }
    return resources.uart;
}

#define NEO_M9N_RUNTIME_TRANSACTION_TIMEOUT_MS \
    (2U * GNSS_CONFIG_READ_TIMEOUT_MS)
#define NEO_M9N_RUNTIME_WAIT_MAX_POLLS 8192U

#define NEO_M9N_SUPPORTED_CONFIG_MASK \
    (SYSTEM_GNSS_CFG_NAVIGATION_RATE | SYSTEM_GNSS_CFG_CONSTELLATIONS | \
     SYSTEM_GNSS_CFG_DYNAMIC_MODEL | SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL | \
     SYSTEM_GNSS_CFG_ENABLED_MESSAGES)

static uint32_t NeoM9nGnssAdapter_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void NeoM9nGnssAdapter_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadHardwareConfigDirect(uint8_t instance,
    SystemGnssHardwareConfig *config);
static SystemDeviceResult NeoM9nGnssAdapter_ReadSatelliteDiagnosticsDirect(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics);
static SystemDeviceResult NeoM9nGnssAdapter_ReadRfDiagnosticsDirect(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics);
static void NeoM9nGnssAdapter_RuntimeTransactionProcess(uint8_t instance);

static void NeoM9nGnssAdapter_TransactionReset(uint8_t instance)
{
    (void)memset(&s_config_transaction, 0, sizeof(s_config_transaction));
    s_config_transaction.uart_baudrate_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.uart_settle_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.protocol_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.nav_pvt_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.rate_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.dynamic_model_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.signals_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.pvt_recovery_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_config_transaction.verify_read_result =
        SYSTEM_GNSS_CONFIG_READ_NOT_READY;
}

static SystemDeviceResult NeoM9nGnssAdapter_Init(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    (void)memset(&s_health, 0, sizeof(s_health));
    (void)memset(&s_effective_config, 0, sizeof(s_effective_config));
    (void)memset(&s_runtime_transaction, 0,
                 sizeof(s_runtime_transaction));
    s_runtime_owner_active = 0U;
    NeoM9nGnssAdapter_TransactionReset(instance);
    s_effective_config.navigation_rate_hz = GNSS_DEFAULT_RATE_HZ;
    s_effective_config.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS |
        SYSTEM_GNSS_CONSTELLATION_BDS | SYSTEM_GNSS_CONSTELLATION_GALILEO;
    s_effective_config.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE;
    s_effective_config.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    s_effective_config.enabled_message_mask = 0U;
    s_effective_config.requested_mask = 0U;
    if (GnssNeoM9n_Init(instance) != GnssNeoM9n_InitOk)
    {
        s_health.error_count++;
        return SYSTEM_DEVICE_IO_ERROR;
    }
    s_initialized = 1U;
    s_health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_Start(uint8_t instance)
{
    uint32_t primask;

    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_started != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    primask = NeoM9nGnssAdapter_IrqLock();
    s_started = 1U;
    s_health.started = 1U;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_Stop(uint8_t instance)
{
    uint32_t primask = NeoM9nGnssAdapter_IrqLock();

    s_started = 0U;
    s_health.started = 0U;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_RuntimeOwnerActivate(uint8_t instance)
{
    uint32_t primask;

    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_owner_active != 0U)
    {
        NeoM9nGnssAdapter_IrqUnlock(primask);
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    s_runtime_owner_active = 1U;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static void NeoM9nGnssAdapter_Process(uint8_t instance)
{
    GnssNeoM9nData data;
    GnssNeoM9nStatusSnapshot status;
    PlatformUartDiagnostics io_diagnostics;
    SystemDeviceHealth health;
    uint64_t now_us;
    uint32_t now_ms;
    uint8_t recent_ubx;
    uint8_t recent_unknown;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_started == 0U) { return; }
    now_us = PlatformTime_Us();
    now_ms = (uint32_t)(now_us / 1000ULL);
    (void)GnssNeoM9n_Process(instance, now_ms);
    NeoM9nGnssAdapter_RuntimeTransactionProcess(instance);
    (void)GnssNeoM9n_GetData(instance, &data);
    GnssNeoM9n_GetStatusSnapshot(instance, &status);
    (void)PlatformUart_DiagnosticsGet(NeoM9nAdapter_UartGet(instance), &io_diagnostics);
    primask = NeoM9nGnssAdapter_IrqLock();
    health = s_health;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    health.last_sample_timestamp_us = data.lastUpdate_us;
    health.last_receive_timestamp_us = data.lastUpdate_us;
    health.sample_count = data.pvtSequence;
    health.checksum_error_count = status.ubx_checksum_error_count +
                                  status.nmea_checksum_error_count;
    recent_ubx = (uint8_t)((status.last_ubx_ms != 0U) &&
                           ((now_ms - status.last_ubx_ms) <= GNSS_TIMEOUT_MS));
    recent_unknown = (uint8_t)((status.last_unknown_ms != 0U) &&
        ((now_ms - status.last_unknown_ms) <= GNSS_TIMEOUT_MS));
    health.online = (uint8_t)((s_started != 0U) && (data.online != 0U));
    health.healthy = (uint8_t)((health.online != 0U) &&
                               (recent_ubx != 0U) &&
                               (recent_unknown == 0U) &&
                               (io_diagnostics.rx_active != 0U));
    primask = NeoM9nGnssAdapter_IrqLock();
    s_health = health;
    NeoM9nGnssAdapter_IrqUnlock(primask);
}

static SystemDeviceResult NeoM9nGnssAdapter_GetInfo(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "NEO-M9N GNSS Adapter";
    info->model_name = "NEO-M9N";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_GNSS_CAP_POSITION |
                            SYSTEM_GNSS_CAP_VELOCITY_2D |
                            SYSTEM_GNSS_CAP_VELOCITY_3D |
                            SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT |
                            SYSTEM_GNSS_CAP_MSL_HEIGHT |
                            SYSTEM_GNSS_CAP_TIME |
                            SYSTEM_GNSS_CAP_ACCURACY_FIELDS |
                            SYSTEM_GNSS_CAP_CONFIG_NAV_RATE |
                            SYSTEM_GNSS_CAP_DYNAMIC_MODEL |
                            SYSTEM_GNSS_CAP_SATELLITE_DIAGNOSTICS |
                            SYSTEM_GNSS_CAP_RF_DIAGNOSTICS;
    info->configuration_mask = NEO_M9N_SUPPORTED_CONFIG_MASK;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_GetCapabilities(uint32_t *mask)
{
    SystemDeviceInfo info;

    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)NeoM9nGnssAdapter_GetInfo(&info);
    *mask = info.capability_mask;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_GetHealth(uint8_t instance, SystemDeviceHealth *health)
{
    uint32_t primask;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = NeoM9nGnssAdapter_IrqLock();
    *health = s_health;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static void NeoM9nGnssAdapter_SampleValiditySet(
    const GnssNeoM9nData *data,
    SystemGnssSample *sample)
{
    if ((data == NULL) || (sample == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(data, GnssNeoM9nData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    sample->supported_fields = SYSTEM_GNSS_FIELD_FIX_TYPE |
        SYSTEM_GNSS_FIELD_FIX_OK | SYSTEM_GNSS_FIELD_SATELLITE_COUNT |
        SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HEIGHT |
        SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL |
        SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL |
        SYSTEM_GNSS_FIELD_SPEED_ACCURACY;
    sample->valid_fields = SYSTEM_GNSS_FIELD_FIX_TYPE |
        SYSTEM_GNSS_FIELD_FIX_OK | SYSTEM_GNSS_FIELD_SATELLITE_COUNT;
    if ((data->gnssFixOK != 0U) && (data->fixType >= 2U))
    {
        sample->valid_fields |= SYSTEM_GNSS_FIELD_POSITION |
            SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
            SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL |
            SYSTEM_GNSS_FIELD_SPEED_ACCURACY;
    }
    if ((data->gnssFixOK != 0U) &&
        ((data->fixType == 3U) || (data->fixType == 4U)))
    {
        sample->valid_fields |= SYSTEM_GNSS_FIELD_HEIGHT |
            SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY |
            SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL;
    }
}

static SystemDeviceResult NeoM9nGnssAdapter_GetSample(uint8_t instance, SystemGnssSample *sample)
{
    GnssNeoM9nData data;
    float speed_std_mps;
    float speed_variance;
    uint8_t index;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (GnssNeoM9n_GetData(instance, &data) == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = data.lastUpdate_us;
    sample->receive_timestamp_us = data.lastUpdate_us;
    sample->sequence = data.pvtSequence;
    NeoM9nGnssAdapter_SampleValiditySet(&data, sample);
    sample->latitude_e7 = data.lat;
    sample->longitude_e7 = data.lon;
    sample->ellipsoid_height_mm = data.height;
    sample->msl_height_mm = data.hMSL;
    sample->velocity_enu_mps[0] = (float)data.velE * 0.001f;
    sample->velocity_enu_mps[1] = (float)data.velN * 0.001f;
    sample->velocity_enu_mps[2] = (float)(-data.velD) * 0.001f;
    speed_std_mps = (float)data.sAcc * 0.001f;
    speed_variance = speed_std_mps * speed_std_mps;
    for (index = 0U; index < 3U; index++)
    {
        sample->velocity_variance_m2ps2[index] = speed_variance;
    }
    sample->horizontal_accuracy_m = (float)data.hAcc * 0.001f;
    sample->vertical_accuracy_m = (float)data.vAcc * 0.001f;
    sample->speed_accuracy_mps = speed_std_mps;
    sample->fix_type = data.fixType;
    sample->fix_ok = data.gnssFixOK;
    sample->satellite_count = data.numSV;
    sample->course_usable = data.courseUsable;
    sample->online = data.online;
    return SystemGnssQuality_Evaluate(sample, PlatformTime_Us());
}

static SystemDeviceResult NeoM9nGnssAdapter_GetIoDiagnostics(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    PlatformUartDiagnostics source;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)PlatformUart_DiagnosticsGet(NeoM9nAdapter_UartGet(instance), &source);
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

static SystemDeviceResult NeoM9nGnssAdapter_GetIoDetail(uint8_t instance,
    SystemGnssIoDetail *detail)
{
    GnssNeoM9nStreamDiagnostics source;

    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    GnssNeoM9n_StreamDiagnosticsGet(instance, &source);
    detail->ubx_frame_count = source.ubx_frame_count;
    detail->ubx_checksum_error_count = source.ubx_checksum_error_count;
    detail->nmea_sentence_count = source.nmea_sentence_count;
    detail->nmea_checksum_ok_count = source.nmea_checksum_ok_count;
    detail->nmea_checksum_error_count = source.nmea_checksum_error_count;
    detail->unknown_byte_count = source.unknown_byte_count;
    detail->parser_resync_count = source.parser_resync_count;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_GetTime(uint8_t instance, SystemGnssTime *time)
{
    GnssNeoM9nData data;

    if (time == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(time, SystemGnssTime,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (GnssNeoM9n_GetData(instance, &data) == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    (void)memset(time, 0, sizeof(*time));
    time->sample_timestamp_us = data.lastUpdate_us;
    time->receive_timestamp_us = data.lastUpdate_us;
    time->sequence = data.pvtSequence;
    time->time_of_week_ms = data.iTOW;
    time->year = data.year;
    time->month = data.month;
    time->day = data.day;
    time->hour = data.hour;
    time->minute = data.min;
    time->second = data.sec;
    time->date_valid = data.validDate;
    time->time_valid = data.validTime;
    time->fully_resolved = (uint8_t)(data.validDate && data.validTime);
    return (time->time_valid != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult NeoM9nGnssAdapter_SelfTest(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult NeoM9nGnssAdapter_ConfigCheck(
    const SystemGnssConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = NEO_M9N_SUPPORTED_CONFIG_MASK;
    report->unsupported_required_mask = config->required_mask &
                                        ~NEO_M9N_SUPPORTED_CONFIG_MASK;
    report->unsupported_optional_mask = (config->requested_mask &
        ~NEO_M9N_SUPPORTED_CONFIG_MASK) & ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        (((config->requested_mask & SYSTEM_GNSS_CFG_NAVIGATION_RATE) != 0U) &&
         ((config->navigation_rate_hz == 0U) ||
          (config->navigation_rate_hz > GNSS_MAX_RATE_HZ))) ||
        (((config->requested_mask & SYSTEM_GNSS_CFG_DYNAMIC_MODEL) != 0U) &&
         (config->dynamic_model > SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G)) ||
        (((config->requested_mask & SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL) != 0U) &&
         (config->output_protocol >
          SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA)) ||
        (((config->requested_mask & SYSTEM_GNSS_CFG_CONSTELLATIONS) != 0U) &&
         ((config->constellation_mask == 0U) ||
          ((config->constellation_mask &
            ~(SYSTEM_GNSS_CONSTELLATION_GPS |
              SYSTEM_GNSS_CONSTELLATION_BDS |
              SYSTEM_GNSS_CONSTELLATION_GALILEO |
              SYSTEM_GNSS_CONSTELLATION_GLONASS)) != 0U))) ||
        (((config->requested_mask & SYSTEM_GNSS_CFG_ENABLED_MESSAGES) != 0U) &&
         ((config->enabled_message_mask &
           ~SYSTEM_GNSS_MESSAGE_NAV_PVT) != 0U)))
    {
        report->verify_failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask &
                           NEO_M9N_SUPPORTED_CONFIG_MASK;
    report->success = 1U;
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static uint8_t NeoM9nGnssAdapter_DynamicModelGet(
    SystemGnssDynamicModel model)
{
    switch (model)
    {
        case SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY: return GNSS_DYNMODEL_STATIONARY;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G: return GNSS_DYNMODEL_AIRBORNE_1G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G: return GNSS_DYNMODEL_AIRBORNE_2G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G: return GNSS_DYNMODEL_AIRBORNE_4G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE:
        default: return GNSS_DYNMODEL_PORTABLE;
    }
}

static uint32_t NeoM9nGnssAdapter_ConstellationMaskGet(uint8_t instance, uint32_t mask)
{
    uint32_t device_mask = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_effective_config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((mask & SYSTEM_GNSS_CONSTELLATION_GPS) != 0U)
    {
        device_mask |= GNSS_CONSTELLATION_GPS;
    }
    if ((mask & SYSTEM_GNSS_CONSTELLATION_BDS) != 0U)
    {
        device_mask |= GNSS_CONSTELLATION_BDS;
    }
    if ((mask & SYSTEM_GNSS_CONSTELLATION_GALILEO) != 0U)
    {
        device_mask |= GNSS_CONSTELLATION_GALILEO;
    }
    if ((mask & SYSTEM_GNSS_CONSTELLATION_GLONASS) != 0U)
    {
        device_mask |= GNSS_CONSTELLATION_GLONASS;
    }
    return device_mask;
}

static SystemDeviceResult NeoM9nGnssAdapter_DeviceResultMap(int result)
{
    if (result == 0) { return SYSTEM_DEVICE_OK; }
    if (result == -2) { return SYSTEM_DEVICE_TIMEOUT; }
    return SYSTEM_DEVICE_IO_ERROR;
}

static SystemGnssConfigReadResult NeoM9nGnssAdapter_ConfigReadResultMap(uint8_t instance,
    GnssNeoM9nConfigReadResult result)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config_transaction,
        SystemGnssConfigTransactionReport, SILVERSTAR_ASSERT_MODULE_DEVICE);
    switch (result)
    {
        case GnssNeoM9nConfigReadResponseOk:
            return SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK;
        case GnssNeoM9nConfigReadNak:
            return SYSTEM_GNSS_CONFIG_READ_NAK;
        case GnssNeoM9nConfigReadTxError:
            return SYSTEM_GNSS_CONFIG_READ_TX_ERROR;
        case GnssNeoM9nConfigReadChecksumError:
            return SYSTEM_GNSS_CONFIG_READ_CHECKSUM_ERROR;
        case GnssNeoM9nConfigReadMalformedResponse:
            return SYSTEM_GNSS_CONFIG_READ_MALFORMED_RESPONSE;
        case GnssNeoM9nConfigReadTimeout:
            return SYSTEM_GNSS_CONFIG_READ_TIMEOUT;
        case GnssNeoM9nConfigReadIoError:
            return SYSTEM_GNSS_CONFIG_READ_IO_ERROR;
        case GnssNeoM9nConfigReadNotReady:
        default:
            return SYSTEM_GNSS_CONFIG_READ_NOT_READY;
    }
}

static SystemDeviceResult NeoM9nGnssAdapter_ConfigReadDeviceResultMap(
    GnssNeoM9nConfigReadResult result)
{
    switch (result)
    {
        case GnssNeoM9nConfigReadResponseOk: return SYSTEM_DEVICE_OK;
        case GnssNeoM9nConfigReadTimeout: return SYSTEM_DEVICE_TIMEOUT;
        case GnssNeoM9nConfigReadNotReady: return SYSTEM_DEVICE_NOT_READY;
        case GnssNeoM9nConfigReadIoError: return SYSTEM_DEVICE_IO_ERROR;
        case GnssNeoM9nConfigReadNak:
        case GnssNeoM9nConfigReadTxError:
        case GnssNeoM9nConfigReadChecksumError:
        case GnssNeoM9nConfigReadMalformedResponse:
        default: return SYSTEM_DEVICE_IO_ERROR;
    }
}

static SystemGnssConfigReadGroup NeoM9nGnssAdapter_ConfigReadGroupMap(
    GnssNeoM9nConfigReadGroup group)
{
    return (SystemGnssConfigReadGroup)group;
}

static SystemGnssTransactionDetail NeoM9nGnssAdapter_DetailMap(
    GnssNeoM9nTransactionDetail detail)
{
    return (SystemGnssTransactionDetail)detail;
}

static SystemGnssDynamicModel NeoM9nGnssAdapter_DynamicModelMap(
    uint8_t model)
{
    switch (model)
    {
        case GNSS_DYNMODEL_STATIONARY:
            return SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY;
        case GNSS_DYNMODEL_AIRBORNE_1G:
            return SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G;
        case GNSS_DYNMODEL_AIRBORNE_2G:
            return SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G;
        case GNSS_DYNMODEL_AIRBORNE_4G:
            return SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
        default:
            return SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE;
    }
}

static SystemGnssOutputProtocol NeoM9nGnssAdapter_OutputProtocolMap(
    uint8_t protocol)
{
    if (protocol == 0x02U) { return SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA; }
    if (protocol == 0x03U) { return SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA; }
    return SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
}

static SystemDeviceResult NeoM9nGnssAdapter_ConfigFailureMap(
    int device_result,
    uint32_t step_id,
    uint32_t failed_mask,
    SystemDeviceConfigReport *report)
{
    if (device_result == 0) { return SYSTEM_DEVICE_OK; }
    report->verify_failed_mask |= failed_mask;
    report->failed_mask |= failed_mask;
    report->detail_code = (step_id << 16) |
        (uint32_t)((device_result < 0) ? -device_result : device_result);
    report->success = 0U;
    if (device_result == -2) { return SYSTEM_DEVICE_TIMEOUT; }
    return SYSTEM_DEVICE_IO_ERROR;
}

static void NeoM9nGnssAdapter_TransportConfigApply(uint8_t instance,
    const SystemGnssConfig *config,
    NeoM9nConfigApplyContext *context)
{
    if ((config == NULL) || (context == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nConfigApplyContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    context->step_id = SYSTEM_GNSS_CONFIG_STAGE_UART;
    context->failed_mask = config->requested_mask;
    context->device_result = GnssNeoM9n_ConfigUartBaudrate(instance,
        context->layers, GNSS_DEFAULT_BAUDRATE);
    s_config_transaction.uart_baudrate_result =
        NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    if (context->device_result == 0)
    {
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_UART_SETTLE;
        context->device_result = GnssNeoM9n_WaitUartConfigSettle(instance,
            GNSS_UART_CONFIG_SETTLE_MS,
            GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS);
        s_config_transaction.uart_settle_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    }
    if ((context->device_result == 0) &&
        ((config->requested_mask & SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL) != 0U))
    {
        GnssOutputProtocol protocol =
            (config->output_protocol == SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA) ?
                GnssOutputProtocolNmeaOnly :
            (config->output_protocol == SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA) ?
                GnssOutputProtocolUbxNmea : GnssOutputProtocolUbxOnly;
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_PROTOCOL;
        context->failed_mask = SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL;
        context->device_result = GnssNeoM9n_ConfigOutputProtocol(instance,
            context->layers, protocol);
        s_config_transaction.protocol_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    }
    if ((context->device_result == 0) &&
        ((config->requested_mask & SYSTEM_GNSS_CFG_ENABLED_MESSAGES) != 0U))
    {
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_NAV_PVT;
        context->failed_mask = SYSTEM_GNSS_CFG_ENABLED_MESSAGES;
        context->device_result = GnssNeoM9n_ConfigNavPvtOutput(instance,
            context->layers,
            ((config->enabled_message_mask & SYSTEM_GNSS_MESSAGE_NAV_PVT) !=
             0U) ? 1U : 0U);
        s_config_transaction.nav_pvt_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    }
}

static void NeoM9nGnssAdapter_NavigationConfigApply(uint8_t instance,
    const SystemGnssConfig *config,
    NeoM9nConfigApplyContext *context)
{
    GnssNeoM9nData data;

    if ((config == NULL) || (context == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nConfigApplyContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((context->device_result == 0) &&
        ((config->requested_mask & SYSTEM_GNSS_CFG_NAVIGATION_RATE) != 0U))
    {
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_RATE;
        context->failed_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE;
        context->device_result = GnssNeoM9n_ConfigNavRate(instance,
            context->layers, (uint8_t)config->navigation_rate_hz);
        s_config_transaction.rate_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    }
    if ((context->device_result == 0) &&
        ((config->requested_mask & SYSTEM_GNSS_CFG_DYNAMIC_MODEL) != 0U))
    {
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_DYNAMIC_MODEL;
        context->failed_mask = SYSTEM_GNSS_CFG_DYNAMIC_MODEL;
        context->device_result = GnssNeoM9n_ConfigDynamicModel(instance,
            context->layers,
            NeoM9nGnssAdapter_DynamicModelGet(config->dynamic_model));
        s_config_transaction.dynamic_model_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
    }
    if ((context->device_result == 0) &&
        ((config->requested_mask & SYSTEM_GNSS_CFG_CONSTELLATIONS) != 0U))
    {
        (void)GnssNeoM9n_GetData(instance, &data);
        s_config_transaction.baseline_pvt_sequence = data.pvtSequence;
        context->step_id = SYSTEM_GNSS_CONFIG_STAGE_SIGNALS;
        context->failed_mask = SYSTEM_GNSS_CFG_CONSTELLATIONS;
        context->device_result = GnssNeoM9n_ConfigSignals(instance, context->layers,
            NeoM9nGnssAdapter_ConstellationMaskGet(instance,
                config->constellation_mask));
        s_config_transaction.signals_result =
            NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
        if (context->device_result == 0)
        {
            s_config_transaction.signal_complete_timestamp_us =
                PlatformTime_Us();
            context->step_id = SYSTEM_GNSS_CONFIG_STAGE_PVT_RECOVERY;
            context->device_result = GnssNeoM9n_WaitForNewNavPvt(instance,
                s_config_transaction.baseline_pvt_sequence,
                s_config_transaction.signal_complete_timestamp_us,
                GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS);
            s_config_transaction.pvt_recovery_result =
                NeoM9nGnssAdapter_DeviceResultMap(context->device_result);
            (void)GnssNeoM9n_GetData(instance, &data);
            s_config_transaction.recovered_pvt_sequence = data.pvtSequence;
        }
    }
}

static void NeoM9nGnssAdapter_EffectiveConfigUpdate(uint8_t instance,
    const SystemGnssConfig *config,
    const SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_effective_config.requested_mask |= report->applied_mask;
    s_effective_config.required_mask =
        (s_effective_config.required_mask & ~report->applied_mask) |
        (config->required_mask & report->applied_mask);
    if ((report->applied_mask & SYSTEM_GNSS_CFG_NAVIGATION_RATE) != 0U)
    { s_effective_config.navigation_rate_hz = config->navigation_rate_hz; }
    if ((report->applied_mask & SYSTEM_GNSS_CFG_CONSTELLATIONS) != 0U)
    { s_effective_config.constellation_mask = config->constellation_mask; }
    if ((report->applied_mask & SYSTEM_GNSS_CFG_DYNAMIC_MODEL) != 0U)
    { s_effective_config.dynamic_model = config->dynamic_model; }
    if ((report->applied_mask & SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL) != 0U)
    { s_effective_config.output_protocol = config->output_protocol; }
    if ((report->applied_mask & SYSTEM_GNSS_CFG_ENABLED_MESSAGES) != 0U)
    {
        s_effective_config.enabled_message_mask = config->enabled_message_mask;
    }
}

static SystemDeviceResult NeoM9nGnssAdapter_ApplyConfig(uint8_t instance,
    const SystemGnssConfig *config,
    SystemDeviceConfigReport *report)
{
    NeoM9nConfigApplyContext context;
    SystemDeviceResult validation =
        NeoM9nGnssAdapter_ConfigCheck(config, report);

    if ((validation != SYSTEM_DEVICE_OK) &&
        (validation != SYSTEM_DEVICE_UNSUPPORTED))
    { return validation; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_runtime_owner_active != 0U) { return SYSTEM_DEVICE_BUSY; }
    NeoM9nGnssAdapter_TransactionReset(instance);
    (void)memset(&context, 0, sizeof(context));
    context.layers = GNSS_CFG_LAYER_RAM;
    context.failed_mask = config->requested_mask;
    s_config_transaction.write_layers = context.layers;
    NeoM9nGnssAdapter_TransportConfigApply(instance, config, &context);
    NeoM9nGnssAdapter_NavigationConfigApply(instance, config, &context);
    s_config_transaction.ack_result = (uint8_t)GnssNeoM9n_GetLastAck(instance);
    if (context.device_result != 0)
    {
        s_config_transaction.failed_stage =
            (SystemGnssConfigStage)context.step_id;
        return NeoM9nGnssAdapter_ConfigFailureMap(
            context.device_result, context.step_id,
            context.failed_mask, report);
    }
    report->applied_mask = config->requested_mask &
                           NEO_M9N_SUPPORTED_CONFIG_MASK;
    report->persisted = 0U;
    report->success = 1U;
    NeoM9nGnssAdapter_EffectiveConfigUpdate(instance, config, report);
    return validation;
}

static SystemDeviceResult NeoM9nGnssAdapter_GetConfig(uint8_t instance, SystemGnssConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *config = s_effective_config;
    return (config->requested_mask != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult NeoM9nGnssAdapter_NoiseCharacteristicsGet(
    SystemGnssNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    noise->recommended_horizontal_position_std_floor_m =
        NEO_M9N_RECOMMENDED_HORIZONTAL_POSITION_STD_FLOOR_M;
    noise->recommended_vertical_position_std_floor_m =
        NEO_M9N_RECOMMENDED_VERTICAL_POSITION_STD_FLOOR_M;
    noise->recommended_velocity_std_floor_mps =
        NEO_M9N_RECOMMENDED_VELOCITY_STD_FLOOR_MPS;
    noise->valid_mask =
        SYSTEM_GNSS_NOISE_VALID_HORIZONTAL_POSITION_STD_FLOOR |
        SYSTEM_GNSS_NOISE_VALID_VERTICAL_POSITION_STD_FLOOR |
        SYSTEM_GNSS_NOISE_VALID_VELOCITY_STD_FLOOR;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_HardwareConfigMap(uint8_t instance,
    const GnssNeoM9nConfigSnapshot *snapshot,
    uint32_t elapsed_ms,
    const GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult result,
    SystemGnssHardwareConfig *config)
{
    if ((snapshot == NULL) || (diagnostics == NULL) || (config == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(snapshot, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssHardwareConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(config, 0, sizeof(*config));
    config->elapsed_ms = elapsed_ms;
    config->valid_mask = snapshot->valid_mask;
    config->baudrate = snapshot->baudrate;
    config->constellation_mask = snapshot->constellations_mask;
    config->navigation_rate_hz = snapshot->rate_hz;
    config->dynamic_model = NeoM9nGnssAdapter_DynamicModelMap(
        snapshot->dynamic_model);
    config->output_protocol = NeoM9nGnssAdapter_OutputProtocolMap(
        snapshot->protocol_out);
    config->protocol_in = snapshot->protocol_in;
    config->nav_pvt_rate = snapshot->nav_pvt_rate;
    config->nav_pvt_known = snapshot->nav_pvt_known;
    config->read_result =
        NeoM9nGnssAdapter_ConfigReadResultMap(instance, result);
    config->failed_group = NeoM9nGnssAdapter_ConfigReadGroupMap(
        diagnostics->failed_group);
    config->failed_key = diagnostics->failed_key;
    config->response_length = diagnostics->response_length;
    config->nak_class = diagnostics->nak_class;
    config->nak_id = diagnostics->nak_id;
    config->detailed_result = NeoM9nGnssAdapter_DetailMap(
        diagnostics->detailed_result);
    config->expected_class = diagnostics->expected_class;
    config->expected_id = diagnostics->expected_id;
    config->received_class = diagnostics->received_class;
    config->received_id = diagnostics->received_id;
    config->response_version = diagnostics->response_version;
    return NeoM9nGnssAdapter_ConfigReadDeviceResultMap(result);
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadHardwareConfigDirect(uint8_t instance,
    SystemGnssHardwareConfig *config)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics diagnostics;
    uint32_t elapsed_ms = 0U;
    GnssNeoM9nConfigReadResult result;

    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(&snapshot, 0, sizeof(snapshot));
    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    result = GnssNeoM9n_ReadHardwareConfig(instance, &snapshot, &elapsed_ms,
                                            &diagnostics);
    return NeoM9nGnssAdapter_HardwareConfigMap(instance,
        &snapshot, elapsed_ms, &diagnostics, result, config);
}

static SystemDeviceResult NeoM9nGnssAdapter_GetLastConfigReport(uint8_t instance,
    SystemGnssConfigTransactionReport *report)
{
    if (report == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *report = s_config_transaction;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult NeoM9nGnssAdapter_DiagnosticResultMap(int result)
{
    if (result == 0) { return SYSTEM_DEVICE_OK; }
    if (result == -2) { return SYSTEM_DEVICE_TIMEOUT; }
    if (result == -3) { return SYSTEM_DEVICE_NOT_READY; }
    if (result == -4) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SYSTEM_DEVICE_IO_ERROR;
}

static SystemDeviceResult NeoM9nGnssAdapter_SatelliteDiagnosticsMap(uint8_t instance,
    const GnssNeoM9nSatelliteDiagnostics *source,
    SystemGnssSatelliteDiagnostics *destination)
{
    uint64_t now_us;
    uint64_t age_us;

    if ((source == NULL) || (destination == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(source, GnssNeoM9nSatelliteDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(destination, SystemGnssSatelliteDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(destination, 0, sizeof(*destination));
    destination->sample_timestamp_us = source->timestamp_us;
    destination->receive_timestamp_us = source->timestamp_us;
    destination->sequence = source->sequence;
    destination->supported_fields = SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS |
        SYSTEM_GNSS_SAT_DIAG_FIELD_CNO |
        SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY;
    destination->satellite_count = source->satellite_count;
    destination->used_count = source->used_count;
    destination->average_cno_dbhz = source->average_cno_dbhz;
    destination->maximum_cno_dbhz = source->maximum_cno_dbhz;
    destination->average_quality = source->average_quality;
    destination->read_result = NeoM9nGnssAdapter_ConfigReadResultMap(instance,
        source->read_result);
    destination->detailed_result = NeoM9nGnssAdapter_DetailMap(
        source->detailed_result);
    destination->response_length = source->response_length;
    destination->expected_class = source->expected_class;
    destination->expected_id = source->expected_id;
    destination->received_class = source->received_class;
    destination->received_id = source->received_id;
    destination->expected_ck_a = source->expected_ck_a;
    destination->expected_ck_b = source->expected_ck_b;
    destination->received_ck_a = source->received_ck_a;
    destination->received_ck_b = source->received_ck_b;
    now_us = PlatformTime_Us();
    age_us = (now_us >= source->timestamp_us) ?
        (now_us - source->timestamp_us) : UINT64_MAX;
    destination->fresh = (uint8_t)((source->valid != 0U) &&
        (age_us <= ((uint64_t)GNSS_TIMEOUT_MS * 1000ULL)));
    destination->valid_fields = (destination->fresh != 0U) ?
        destination->supported_fields : 0U;
    return (destination->fresh != 0U) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult NeoM9nGnssAdapter_RfDiagnosticsMap(uint8_t instance,
    const GnssNeoM9nRfDiagnostics *source,
    SystemGnssRfDiagnostics *destination)
{
    uint64_t now_us;
    uint64_t age_us;

    if ((source == NULL) || (destination == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(source, GnssNeoM9nRfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(destination, SystemGnssRfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(destination, 0, sizeof(*destination));
    destination->sample_timestamp_us = source->timestamp_us;
    destination->receive_timestamp_us = source->timestamp_us;
    destination->sequence = source->sequence;
    destination->supported_fields = SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA |
        SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING |
        SYSTEM_GNSS_RF_DIAG_FIELD_NOISE |
        SYSTEM_GNSS_RF_DIAG_FIELD_AGC;
    destination->noise_per_ms = source->noise_per_ms;
    destination->agc_count = source->agc_count;
    destination->rf_block_count = source->rf_block_count;
    destination->antenna_status = source->antenna_status;
    destination->antenna_power = source->antenna_power;
    destination->jamming_state = source->jamming_state;
    destination->cw_suppression = source->cw_suppression;
    destination->jamming_indicator = source->jamming_indicator;
    destination->read_result = NeoM9nGnssAdapter_ConfigReadResultMap(instance,
        source->read_result);
    destination->detailed_result = NeoM9nGnssAdapter_DetailMap(
        source->detailed_result);
    destination->response_length = source->response_length;
    now_us = PlatformTime_Us();
    age_us = (now_us >= source->timestamp_us) ?
        (now_us - source->timestamp_us) : UINT64_MAX;
    destination->fresh = (uint8_t)((source->valid != 0U) &&
        (age_us <= ((uint64_t)GNSS_TIMEOUT_MS * 1000ULL)));
    destination->valid_fields = (destination->fresh != 0U) ?
        destination->supported_fields : 0U;
    return (destination->fresh != 0U) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadSatelliteDiagnosticsDirect(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    GnssNeoM9nSatelliteDiagnostics source;
    int result;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = GnssNeoM9n_ReadSatelliteDiagnostics(instance, &source);
    if (result != 0)
    {
        (void)NeoM9nGnssAdapter_SatelliteDiagnosticsMap(instance, &source,
                                                         diagnostics);
        diagnostics->supported_fields =
            SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS |
            SYSTEM_GNSS_SAT_DIAG_FIELD_CNO |
            SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY;
        return NeoM9nGnssAdapter_DiagnosticResultMap(result);
    }
    return NeoM9nGnssAdapter_SatelliteDiagnosticsMap(instance, &source, diagnostics);
}

static SystemDeviceResult NeoM9nGnssAdapter_GetSatelliteDiagnostics(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    GnssNeoM9nSatelliteDiagnostics source;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (GnssNeoM9n_GetSatelliteDiagnostics(instance, &source) == 0U)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
        diagnostics->supported_fields =
            SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS |
            SYSTEM_GNSS_SAT_DIAG_FIELD_CNO |
            SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY;
        return SYSTEM_DEVICE_NOT_READY;
    }
    return NeoM9nGnssAdapter_SatelliteDiagnosticsMap(instance, &source, diagnostics);
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadRfDiagnosticsDirect(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{
    GnssNeoM9nRfDiagnostics source;
    int result;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = GnssNeoM9n_ReadRfDiagnostics(instance, &source);
    if (result != 0)
    {
        (void)NeoM9nGnssAdapter_RfDiagnosticsMap(instance, &source, diagnostics);
        diagnostics->supported_fields =
            SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA |
            SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING |
            SYSTEM_GNSS_RF_DIAG_FIELD_NOISE |
            SYSTEM_GNSS_RF_DIAG_FIELD_AGC;
        return NeoM9nGnssAdapter_DiagnosticResultMap(result);
    }
    return NeoM9nGnssAdapter_RfDiagnosticsMap(instance, &source, diagnostics);
}

static void NeoM9nGnssAdapter_RuntimeOutputIdSet(
    NeoM9nRuntimeRequest request,
    NeoM9nRuntimeTransactionOutput *output,
    uint32_t transaction_id)
{
    if (output == NULL) { return; }
    if (request == NeoM9nRuntimeRequestHardwareConfig)
    {
        output->hardware_config.transaction_id = transaction_id;
    }
    else if (request == NeoM9nRuntimeRequestNavSat)
    {
        output->satellite.transaction_id = transaction_id;
    }
    else if (request == NeoM9nRuntimeRequestMonRf)
    {
        output->rf.transaction_id = transaction_id;
    }
}

static void NeoM9nGnssAdapter_RuntimeOutputErrorSet(
    NeoM9nRuntimeRequest request,
    NeoM9nRuntimeTransactionOutput *output,
    uint32_t transaction_id,
    SystemGnssTransactionDetail detail)
{
    if (output == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(output, NeoM9nRuntimeTransactionOutput,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(output, 0, sizeof(*output));
    NeoM9nGnssAdapter_RuntimeOutputIdSet(request, output, transaction_id);
    if (request == NeoM9nRuntimeRequestHardwareConfig)
    {
        output->hardware_config.read_result =
            (detail == SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT) ?
                SYSTEM_GNSS_CONFIG_READ_TIMEOUT :
                SYSTEM_GNSS_CONFIG_READ_NOT_READY;
        output->hardware_config.detailed_result = detail;
    }
    else if (request == NeoM9nRuntimeRequestNavSat)
    {
        output->satellite.supported_fields =
            SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS |
            SYSTEM_GNSS_SAT_DIAG_FIELD_CNO |
            SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY;
        output->satellite.read_result =
            (detail == SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT) ?
                SYSTEM_GNSS_CONFIG_READ_TIMEOUT :
                SYSTEM_GNSS_CONFIG_READ_NOT_READY;
        output->satellite.detailed_result = detail;
    }
    else if (request == NeoM9nRuntimeRequestMonRf)
    {
        output->rf.supported_fields =
            SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA |
            SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING |
            SYSTEM_GNSS_RF_DIAG_FIELD_NOISE |
            SYSTEM_GNSS_RF_DIAG_FIELD_AGC;
        output->rf.read_result =
            (detail == SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT) ?
                SYSTEM_GNSS_CONFIG_READ_TIMEOUT :
                SYSTEM_GNSS_CONFIG_READ_NOT_READY;
        output->rf.detailed_result = detail;
    }
}

static SystemDeviceResult NeoM9nGnssAdapter_RuntimeRequestSubmit(uint8_t instance,
    NeoM9nRuntimeRequest request,
    NeoM9nRuntimeTransactionOutput *output,
    uint32_t start_ms,
    uint32_t timeout_ms,
    uint32_t *transaction_id)
{
    uint32_t primask;

    if ((output == NULL) || (transaction_id == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(output, NeoM9nRuntimeTransactionOutput,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(transaction_id, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_transaction.state != NeoM9nRuntimeTransactionIdle)
    {
        *transaction_id = s_runtime_transaction.transaction_id;
        NeoM9nGnssAdapter_IrqUnlock(primask);
        NeoM9nGnssAdapter_RuntimeOutputErrorSet(
            request, output, *transaction_id,
            SYSTEM_GNSS_TRANSACTION_DETAIL_BUSY);
        return SYSTEM_DEVICE_BUSY;
    }
    s_runtime_transaction.next_transaction_id++;
    if (s_runtime_transaction.next_transaction_id == 0U)
    {
        s_runtime_transaction.next_transaction_id = 1U;
    }
    *transaction_id = s_runtime_transaction.next_transaction_id;
    s_runtime_transaction.transaction_id = *transaction_id;
    s_runtime_transaction.request = request;
    s_runtime_transaction.start_ms = start_ms;
    s_runtime_transaction.timeout_ms = timeout_ms;
    s_runtime_transaction.expected_key = 0U;
    s_runtime_transaction.expected_class =
        (request == NeoM9nRuntimeRequestMonRf) ? 0x0AU :
        (request == NeoM9nRuntimeRequestNavSat) ? 0x01U : 0x06U;
    s_runtime_transaction.expected_id =
        (request == NeoM9nRuntimeRequestMonRf) ? 0x38U :
        (request == NeoM9nRuntimeRequestNavSat) ? 0x35U : 0x8BU;
    s_runtime_transaction.abandoned = 0U;
    (void)memset(&s_runtime_transaction.output, 0,
                 sizeof(s_runtime_transaction.output));
    (void)memset(&s_runtime_transaction.device_config, 0,
                 sizeof(s_runtime_transaction.device_config));
    (void)memset(&s_runtime_transaction.device_config_diagnostics, 0,
                 sizeof(s_runtime_transaction.device_config_diagnostics));
    (void)memset(&s_runtime_transaction.device_satellite, 0,
                 sizeof(s_runtime_transaction.device_satellite));
    (void)memset(&s_runtime_transaction.device_rf, 0,
                 sizeof(s_runtime_transaction.device_rf));
    s_runtime_transaction.state = NeoM9nRuntimeTransactionSubmitted;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static uint8_t NeoM9nGnssAdapter_RuntimeCompletionTake(uint8_t instance,
    uint32_t transaction_id,
    NeoM9nRuntimeTransactionOutput *output,
    SystemDeviceResult *result)
{
    uint32_t primask;

    if ((output == NULL) || (result == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(output, NeoM9nRuntimeTransactionOutput,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(result, SystemDeviceResult,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = NeoM9nGnssAdapter_IrqLock();
    if (((s_runtime_transaction.state == NeoM9nRuntimeTransactionComplete) ||
         (s_runtime_transaction.state == NeoM9nRuntimeTransactionFailed)) &&
        (s_runtime_transaction.transaction_id == transaction_id))
    {
        *result = s_runtime_transaction.result;
        *output = s_runtime_transaction.output;
        s_runtime_transaction.state = NeoM9nRuntimeTransactionIdle;
        NeoM9nGnssAdapter_IrqUnlock(primask);
        return 1U;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 0U;
}

static void NeoM9nGnssAdapter_RuntimeRequestAbandon(uint8_t instance, uint32_t transaction_id)
{
    uint32_t primask = NeoM9nGnssAdapter_IrqLock();

    SILVERSTAR_ASSERT_OBJECT(&s_runtime_transaction,
        NeoM9nRuntimeTransaction, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_runtime_transaction.transaction_id == transaction_id) &&
        (s_runtime_transaction.state == NeoM9nRuntimeTransactionSubmitted))
    {
        s_runtime_transaction.state = NeoM9nRuntimeTransactionIdle;
    }
    else if (s_runtime_transaction.transaction_id == transaction_id)
    {
        s_runtime_transaction.abandoned = 1U;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
}

static SystemDeviceResult NeoM9nGnssAdapter_RuntimeRequestWait(uint8_t instance,
    NeoM9nRuntimeRequest request,
    NeoM9nRuntimeTransactionOutput *output)
{
    SystemDeviceResult result;
    uint32_t transaction_id;
    uint32_t start_ms;
    uint32_t timeout_ms;
    uint32_t wait_timeout_ms;
    uint32_t poll;

    if (output == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(output, NeoM9nRuntimeTransactionOutput,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_ms = PlatformTime_Ms();
    timeout_ms = (request == NeoM9nRuntimeRequestHardwareConfig) ?
        NEO_M9N_RUNTIME_TRANSACTION_TIMEOUT_MS : GNSS_CONFIG_READ_TIMEOUT_MS;
    wait_timeout_ms = timeout_ms + GNSS_CONFIG_READ_KEY_TIMEOUT_MS;
    result = NeoM9nGnssAdapter_RuntimeRequestSubmit(instance,
        request, output, start_ms, timeout_ms, &transaction_id);
    if (result != SYSTEM_DEVICE_OK) { return result; }

    for (poll = 0U; poll < NEO_M9N_RUNTIME_WAIT_MAX_POLLS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >= wait_timeout_ms)
        {
            break;
        }
        if (NeoM9nGnssAdapter_RuntimeCompletionTake(instance,
                transaction_id, output, &result) != 0U)
        {
            return result;
        }
        PlatformTime_DelayMs(1U);
    }
    if (NeoM9nGnssAdapter_RuntimeCompletionTake(instance,
            transaction_id, output, &result) != 0U)
    {
        return result;
    }
    NeoM9nGnssAdapter_RuntimeRequestAbandon(instance, transaction_id);
    NeoM9nGnssAdapter_RuntimeOutputErrorSet(
        request, output, transaction_id,
        SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT);
    return SYSTEM_DEVICE_TIMEOUT;
}

static void NeoM9nGnssAdapter_RuntimeTransactionCancel(uint8_t instance,
    NeoM9nRuntimeRequest request,
    SystemGnssTransactionDetail detail)
{
    GnssNeoM9nConfigReadResult result =
        (detail == SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT) ?
            GnssNeoM9nConfigReadTimeout :
            GnssNeoM9nConfigReadIoError;
    GnssNeoM9nTransactionDetail device_detail =
        (detail == SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT) ?
            GnssNeoM9nTransactionDetailTimeout :
            GnssNeoM9nTransactionDetailRxDiscontinuity;

    SILVERSTAR_ASSERT_OBJECT(&s_runtime_transaction,
        NeoM9nRuntimeTransaction, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (request == NeoM9nRuntimeRequestHardwareConfig)
    {
        GnssNeoM9n_ConfigReadAsyncCancel(instance, result, device_detail);
    }
    else if (request == NeoM9nRuntimeRequestNavSat)
    {
        GnssNeoM9n_SatelliteDiagnosticsAsyncCancel(instance, result, device_detail);
    }
    else if (request == NeoM9nRuntimeRequestMonRf)
    {
        GnssNeoM9n_RfDiagnosticsAsyncCancel(instance, result, device_detail);
    }
}

static SystemDeviceResult NeoM9nGnssAdapter_RuntimeStartResultMap(
    GnssNeoM9nAsyncStartResult result)
{
    if ((result == GnssNeoM9nAsyncStartOk) ||
        (result == GnssNeoM9nAsyncStartTxError))
    {
        return SYSTEM_DEVICE_OK;
    }
    if (result == GnssNeoM9nAsyncStartBusy) { return SYSTEM_DEVICE_BUSY; }
    if (result == GnssNeoM9nAsyncStartNotReady)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    return SYSTEM_DEVICE_INVALID_ARGUMENT;
}

static uint8_t NeoM9nGnssAdapter_RuntimeSnapshotGet(uint8_t instance,
    NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    uint32_t primask;

    if (snapshot == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = NeoM9nGnssAdapter_IrqLock();
    snapshot->state = s_runtime_transaction.state;
    snapshot->request = s_runtime_transaction.request;
    snapshot->transaction_id = s_runtime_transaction.transaction_id;
    snapshot->start_ms = s_runtime_transaction.start_ms;
    snapshot->timeout_ms = s_runtime_transaction.timeout_ms;
    snapshot->abandoned = s_runtime_transaction.abandoned;
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return (uint8_t)((snapshot->state != NeoM9nRuntimeTransactionIdle) &&
        (snapshot->state != NeoM9nRuntimeTransactionComplete) &&
        (snapshot->state != NeoM9nRuntimeTransactionFailed));
}

static uint8_t NeoM9nGnssAdapter_RuntimeAbandonedProcess(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    uint32_t primask;

    if ((snapshot == NULL) || (snapshot->abandoned == 0U)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    NeoM9nGnssAdapter_RuntimeTransactionCancel(instance,
        snapshot->request, SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT);
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_transaction.transaction_id == snapshot->transaction_id)
    {
        s_runtime_transaction.state = NeoM9nRuntimeTransactionIdle;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 1U;
}

static uint8_t NeoM9nGnssAdapter_RuntimeTimeoutProcess(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    NeoM9nRuntimeTransactionOutput output;
    uint32_t primask;

    if (snapshot == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((PlatformTime_Ms() - snapshot->start_ms) < snapshot->timeout_ms)
    { return 0U; }
    NeoM9nGnssAdapter_RuntimeTransactionCancel(instance,
        snapshot->request, SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT);
    (void)memset(&output, 0, sizeof(output));
    NeoM9nGnssAdapter_RuntimeOutputErrorSet(
        snapshot->request, &output, snapshot->transaction_id,
        SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT);
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_transaction.transaction_id == snapshot->transaction_id)
    {
        s_runtime_transaction.output = output;
        s_runtime_transaction.result = SYSTEM_DEVICE_TIMEOUT;
        s_runtime_transaction.state = NeoM9nRuntimeTransactionFailed;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 1U;
}

static uint8_t NeoM9nGnssAdapter_RuntimeSubmittedProcess(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    uint32_t primask;

    if ((snapshot == NULL) ||
        (snapshot->state != NeoM9nRuntimeTransactionSubmitted))
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = NeoM9nGnssAdapter_IrqLock();
    if ((s_runtime_transaction.transaction_id == snapshot->transaction_id) &&
        (s_runtime_transaction.state == NeoM9nRuntimeTransactionSubmitted))
    {
        s_runtime_transaction.state = NeoM9nRuntimeTransactionSendRequest;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 1U;
}

static GnssNeoM9nAsyncStartResult NeoM9nGnssAdapter_RuntimeRequestStart(uint8_t instance,
    NeoM9nRuntimeRequest request)
{
    if (request == NeoM9nRuntimeRequestHardwareConfig)
    { return GnssNeoM9n_ConfigReadAsyncStart(instance); }
    if (request == NeoM9nRuntimeRequestNavSat)
    { return GnssNeoM9n_SatelliteDiagnosticsAsyncStart(instance); }
    if (request == NeoM9nRuntimeRequestMonRf)
    { return GnssNeoM9n_RfDiagnosticsAsyncStart(instance); }
    return GnssNeoM9nAsyncStartInvalidArgument;
}

static uint8_t NeoM9nGnssAdapter_RuntimeSendProcess(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    SystemDeviceResult result;
    uint32_t primask;

    if ((snapshot == NULL) ||
        (snapshot->state != NeoM9nRuntimeTransactionSendRequest))
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = NeoM9nGnssAdapter_RuntimeStartResultMap(
        NeoM9nGnssAdapter_RuntimeRequestStart(instance, snapshot->request));
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_transaction.transaction_id == snapshot->transaction_id)
    {
        if (result == SYSTEM_DEVICE_OK)
        {
            s_runtime_transaction.state = NeoM9nRuntimeTransactionWaitResponse;
        }
        else
        {
            NeoM9nGnssAdapter_RuntimeOutputErrorSet(
                snapshot->request, &s_runtime_transaction.output,
                snapshot->transaction_id,
                (result == SYSTEM_DEVICE_BUSY) ?
                    SYSTEM_GNSS_TRANSACTION_DETAIL_BUSY :
                    SYSTEM_GNSS_TRANSACTION_DETAIL_NOT_READY);
            s_runtime_transaction.result = result;
            s_runtime_transaction.state = NeoM9nRuntimeTransactionFailed;
        }
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 1U;
}

static GnssNeoM9nAsyncPollResult NeoM9nGnssAdapter_RuntimeResponsePoll(uint8_t instance,
    NeoM9nRuntimeRequest request,
    NeoM9nRuntimeTransactionOutput *output,
    SystemDeviceResult *result)
{
    GnssNeoM9nAsyncPollResult poll_result;

    if ((output == NULL) || (result == NULL))
    { return GnssNeoM9nAsyncPollPending; }
    SILVERSTAR_ASSERT_OBJECT(output, NeoM9nRuntimeTransactionOutput,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(result, SystemDeviceResult,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (request == NeoM9nRuntimeRequestHardwareConfig)
    {
        poll_result = GnssNeoM9n_ConfigReadAsyncPoll(instance,
            &s_runtime_transaction.device_config,
            &s_runtime_transaction.device_config_elapsed_ms,
            &s_runtime_transaction.device_config_diagnostics,
            &s_runtime_transaction.device_config_result);
        if (poll_result == GnssNeoM9nAsyncPollComplete)
        {
            *result = NeoM9nGnssAdapter_HardwareConfigMap(instance,
                &s_runtime_transaction.device_config,
                s_runtime_transaction.device_config_elapsed_ms,
                &s_runtime_transaction.device_config_diagnostics,
                s_runtime_transaction.device_config_result,
                &output->hardware_config);
        }
    }
    else if (request == NeoM9nRuntimeRequestNavSat)
    {
        poll_result = GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(instance,
            &s_runtime_transaction.device_satellite);
        if (poll_result == GnssNeoM9nAsyncPollComplete)
        {
            (void)NeoM9nGnssAdapter_SatelliteDiagnosticsMap(instance,
                &s_runtime_transaction.device_satellite, &output->satellite);
            *result = NeoM9nGnssAdapter_ConfigReadDeviceResultMap(
                s_runtime_transaction.device_satellite.read_result);
        }
    }
    else
    {
        poll_result = GnssNeoM9n_RfDiagnosticsAsyncPoll(instance,
            &s_runtime_transaction.device_rf);
        if (poll_result == GnssNeoM9nAsyncPollComplete)
        {
            (void)NeoM9nGnssAdapter_RfDiagnosticsMap(instance,
                &s_runtime_transaction.device_rf, &output->rf);
            *result = NeoM9nGnssAdapter_ConfigReadDeviceResultMap(
                s_runtime_transaction.device_rf.read_result);
        }
    }
    return poll_result;
}

static uint8_t NeoM9nGnssAdapter_RuntimeWaitResponseProcess(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    NeoM9nRuntimeTransactionOutput output;
    SystemDeviceResult result = SYSTEM_DEVICE_INVALID_ARGUMENT;
    GnssNeoM9nAsyncPollResult poll_result;
    uint32_t primask;

    if ((snapshot == NULL) ||
        (snapshot->state != NeoM9nRuntimeTransactionWaitResponse))
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(&output, 0, sizeof(output));
    poll_result = NeoM9nGnssAdapter_RuntimeResponsePoll(instance,
        snapshot->request, &output, &result);
    if (poll_result == GnssNeoM9nAsyncPollPending) { return 1U; }
    NeoM9nGnssAdapter_RuntimeOutputIdSet(
        snapshot->request, &output, snapshot->transaction_id);
    primask = NeoM9nGnssAdapter_IrqLock();
    if (s_runtime_transaction.transaction_id == snapshot->transaction_id)
    {
        s_runtime_transaction.output = output;
        s_runtime_transaction.result = result;
        s_runtime_transaction.state =
            NeoM9nRuntimeTransactionProcessResponse;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
    return 1U;
}

static void NeoM9nGnssAdapter_RuntimeResponseFinalize(uint8_t instance,
    const NeoM9nRuntimeTransactionSnapshot *snapshot)
{
    uint32_t primask;

    if ((snapshot == NULL) ||
        (snapshot->state != NeoM9nRuntimeTransactionProcessResponse))
    { return; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, NeoM9nRuntimeTransactionSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = NeoM9nGnssAdapter_IrqLock();
    if ((s_runtime_transaction.state ==
         NeoM9nRuntimeTransactionProcessResponse) &&
        (s_runtime_transaction.transaction_id == snapshot->transaction_id))
    {
        s_runtime_transaction.state =
            (s_runtime_transaction.result == SYSTEM_DEVICE_OK) ?
                NeoM9nRuntimeTransactionComplete :
                NeoM9nRuntimeTransactionFailed;
    }
    NeoM9nGnssAdapter_IrqUnlock(primask);
}

static void NeoM9nGnssAdapter_RuntimeTransactionProcess(uint8_t instance)
{
    NeoM9nRuntimeTransactionSnapshot snapshot;

    SILVERSTAR_ASSERT_OBJECT(&s_runtime_transaction,
        NeoM9nRuntimeTransaction, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (NeoM9nGnssAdapter_RuntimeSnapshotGet(instance, &snapshot) == 0U) { return; }
    if (NeoM9nGnssAdapter_RuntimeAbandonedProcess(instance, &snapshot) != 0U)
    { return; }
    if (NeoM9nGnssAdapter_RuntimeTimeoutProcess(instance, &snapshot) != 0U)
    { return; }
    if (NeoM9nGnssAdapter_RuntimeSubmittedProcess(instance, &snapshot) != 0U)
    { return; }
    if (NeoM9nGnssAdapter_RuntimeSendProcess(instance, &snapshot) != 0U)
    { return; }
    if (NeoM9nGnssAdapter_RuntimeWaitResponseProcess(instance, &snapshot) != 0U)
    { return; }
    NeoM9nGnssAdapter_RuntimeResponseFinalize(instance, &snapshot);
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadHardwareConfig(uint8_t instance,
    SystemGnssHardwareConfig *config)
{
    NeoM9nRuntimeTransactionOutput output;
    SystemDeviceResult result;

    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_runtime_owner_active == 0U)
    {
        return NeoM9nGnssAdapter_ReadHardwareConfigDirect(instance, config);
    }
    result = NeoM9nGnssAdapter_RuntimeRequestWait(instance,
        NeoM9nRuntimeRequestHardwareConfig, &output);
    *config = output.hardware_config;
    return result;
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadSatelliteDiagnostics(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    NeoM9nRuntimeTransactionOutput output;
    SystemDeviceResult result;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_runtime_owner_active == 0U)
    {
        return NeoM9nGnssAdapter_ReadSatelliteDiagnosticsDirect(instance, diagnostics);
    }
    result = NeoM9nGnssAdapter_RuntimeRequestWait(instance,
        NeoM9nRuntimeRequestNavSat, &output);
    *diagnostics = output.satellite;
    return result;
}

static SystemDeviceResult NeoM9nGnssAdapter_ReadRfDiagnostics(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{
    NeoM9nRuntimeTransactionOutput output;
    SystemDeviceResult result;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_runtime_owner_active == 0U)
    {
        return NeoM9nGnssAdapter_ReadRfDiagnosticsDirect(instance, diagnostics);
    }
    result = NeoM9nGnssAdapter_RuntimeRequestWait(instance,
        NeoM9nRuntimeRequestMonRf, &output);
    *diagnostics = output.rf;
    return result;
}

static SystemDeviceResult NeoM9nGnssAdapter_GetRfDiagnostics(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{
    GnssNeoM9nRfDiagnostics source;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (GnssNeoM9n_GetRfDiagnostics(instance, &source) == 0U)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
        diagnostics->supported_fields =
            SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA |
            SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING |
            SYSTEM_GNSS_RF_DIAG_FIELD_NOISE |
            SYSTEM_GNSS_RF_DIAG_FIELD_AGC;
        return SYSTEM_DEVICE_NOT_READY;
    }
    return NeoM9nGnssAdapter_RfDiagnosticsMap(instance, &source, diagnostics);
}

static void NeoM9nGnssAdapter_VerifyDiagnosticsCapture(uint8_t instance,
    const GnssNeoM9nConfigSnapshot *snapshot,
    const GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult result)
{
    if ((snapshot == NULL) || (diagnostics == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(diagnostics, GnssNeoM9nConfigReadDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_config_transaction.verify_read_result =
        NeoM9nGnssAdapter_ConfigReadResultMap(instance, result);
    s_config_transaction.verify_failed_group =
        NeoM9nGnssAdapter_ConfigReadGroupMap(
            diagnostics->failed_group);
    s_config_transaction.verify_failed_key = diagnostics->failed_key;
    s_config_transaction.verify_valid_mask = snapshot->valid_mask;
    s_config_transaction.verify_response_length =
        diagnostics->response_length;
    s_config_transaction.verify_nak_class = diagnostics->nak_class;
    s_config_transaction.verify_nak_id = diagnostics->nak_id;
    s_config_transaction.verify_detailed_result =
        NeoM9nGnssAdapter_DetailMap(diagnostics->detailed_result);
    s_config_transaction.verify_expected_class =
        diagnostics->expected_class;
    s_config_transaction.verify_expected_id = diagnostics->expected_id;
    s_config_transaction.verify_received_class =
        diagnostics->received_class;
    s_config_transaction.verify_received_id = diagnostics->received_id;
    s_config_transaction.verify_response_version =
        diagnostics->response_version;
}

static uint32_t NeoM9nGnssAdapter_VerifyMismatchGet(uint8_t instance,
    const SystemGnssConfig *config,
    const GnssNeoM9nConfigSnapshot *snapshot)
{
    uint32_t mismatch_mask = 0U;
    uint8_t expected_protocol;

    if ((config == NULL) || (snapshot == NULL)) { return UINT32_MAX; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(snapshot, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (((snapshot->valid_mask & GNSS_CONFIG_VALID_BAUD) == 0U) ||
        (snapshot->baudrate != GNSS_DEFAULT_BAUDRATE))
    { mismatch_mask |= GNSS_CONFIG_VALID_BAUD; }
    if ((config->requested_mask & SYSTEM_GNSS_CFG_NAVIGATION_RATE) != 0U)
    {
        if (((snapshot->valid_mask & GNSS_CONFIG_VALID_RATE) == 0U) ||
            (snapshot->rate_hz != config->navigation_rate_hz))
        { mismatch_mask |= GNSS_CONFIG_VALID_RATE; }
    }
    if ((config->requested_mask & SYSTEM_GNSS_CFG_DYNAMIC_MODEL) != 0U)
    {
        if (((snapshot->valid_mask & GNSS_CONFIG_VALID_DYNAMIC) == 0U) ||
            (snapshot->dynamic_model !=
             NeoM9nGnssAdapter_DynamicModelGet(config->dynamic_model)))
        { mismatch_mask |= GNSS_CONFIG_VALID_DYNAMIC; }
    }
    if ((config->requested_mask & SYSTEM_GNSS_CFG_CONSTELLATIONS) != 0U)
    {
        if (((snapshot->valid_mask & GNSS_CONFIG_VALID_CONSTELLATIONS) == 0U) ||
            (snapshot->constellations_mask !=
             NeoM9nGnssAdapter_ConstellationMaskGet(instance,
                 config->constellation_mask)))
        { mismatch_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS; }
    }
    if ((config->requested_mask & SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL) != 0U)
    {
        expected_protocol =
            (config->output_protocol == SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA) ?
                0x02U :
            (config->output_protocol == SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA) ?
                0x03U : 0x01U;
        if (((snapshot->valid_mask & GNSS_CONFIG_VALID_PROTOCOL_OUT) == 0U) ||
            (snapshot->protocol_out != expected_protocol))
        { mismatch_mask |= GNSS_CONFIG_VALID_PROTOCOL_OUT; }
    }
    if ((config->requested_mask & SYSTEM_GNSS_CFG_ENABLED_MESSAGES) != 0U)
    {
        uint8_t expected_rate =
            ((config->enabled_message_mask & SYSTEM_GNSS_MESSAGE_NAV_PVT) != 0U) ?
                1U : 0U;
        if (((snapshot->valid_mask & GNSS_CONFIG_VALID_NAV_PVT) == 0U) ||
            (snapshot->nav_pvt_known == 0U) ||
            (snapshot->nav_pvt_rate != expected_rate))
        { mismatch_mask |= GNSS_CONFIG_VALID_NAV_PVT; }
    }
    return mismatch_mask;
}

static SystemDeviceResult NeoM9nGnssAdapter_VerifyReadFailureSet(uint8_t instance,
    const SystemGnssConfig *config,
    SystemDeviceConfigReport *report,
    GnssNeoM9nConfigReadResult result)
{
    SystemDeviceResult mapped_result;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    report->matched_mask = 0U;
    report->verify_failed_mask = config->requested_mask;
    report->failed_mask = report->verify_failed_mask;
    report->detail_code = (7UL << 16) | (uint32_t)result;
    report->success = 0U;
    mapped_result = NeoM9nGnssAdapter_ConfigReadDeviceResultMap(result);
    s_config_transaction.verify_result = mapped_result;
    s_config_transaction.failed_stage = SYSTEM_GNSS_CONFIG_STAGE_VERIFY;
    return mapped_result;
}

static SystemDeviceResult NeoM9nGnssAdapter_VerifyMismatchSet(uint8_t instance,
    const SystemGnssConfig *config,
    SystemDeviceConfigReport *report,
    uint32_t mismatch_mask)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    report->matched_mask = 0U;
    report->verify_failed_mask = config->requested_mask;
    report->failed_mask = report->verify_failed_mask;
    report->detail_code = mismatch_mask;
    report->success = 0U;
    s_config_transaction.verify_result = SYSTEM_DEVICE_VERIFY_FAILED;
    s_config_transaction.failed_stage = SYSTEM_GNSS_CONFIG_STAGE_VERIFY;
    return SYSTEM_DEVICE_VERIFY_FAILED;
}

static SystemDeviceResult NeoM9nGnssAdapter_VerifyConfig(uint8_t instance,
    const SystemGnssConfig *config,
    SystemDeviceConfigReport *report)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics read_diagnostics;
    uint32_t elapsed_ms = 0U;
    uint32_t mismatch_mask;
    GnssNeoM9nConfigReadResult result;
    SystemDeviceResult validation =
        NeoM9nGnssAdapter_ConfigCheck(config, report);

    if ((validation != SYSTEM_DEVICE_OK) &&
        (validation != SYSTEM_DEVICE_UNSUPPORTED))
    {
        s_config_transaction.verify_result = validation;
        s_config_transaction.failed_stage = SYSTEM_GNSS_CONFIG_STAGE_VERIFY;
        return validation;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(report, SystemDeviceConfigReport,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_runtime_owner_active != 0U)
    {
        s_config_transaction.verify_result = SYSTEM_DEVICE_BUSY;
        s_config_transaction.failed_stage = SYSTEM_GNSS_CONFIG_STAGE_VERIFY;
        return SYSTEM_DEVICE_BUSY;
    }
    (void)memset(&snapshot, 0, sizeof(snapshot));
    (void)memset(&read_diagnostics, 0, sizeof(read_diagnostics));
    result = GnssNeoM9n_ReadHardwareConfig(instance, &snapshot, &elapsed_ms,
                                            &read_diagnostics);
    NeoM9nGnssAdapter_VerifyDiagnosticsCapture(instance,
        &snapshot, &read_diagnostics, result);
    report->retry_count = 0U;
    if (result != GnssNeoM9nConfigReadResponseOk)
    { return NeoM9nGnssAdapter_VerifyReadFailureSet(instance, config, report, result); }
    mismatch_mask = NeoM9nGnssAdapter_VerifyMismatchGet(instance, config, &snapshot);
    if (mismatch_mask != 0U)
    { return NeoM9nGnssAdapter_VerifyMismatchSet(instance,
        config, report, mismatch_mask); }
    report->detail_code = elapsed_ms;
    report->success = 1U;
    s_config_transaction.verify_result = validation;
    return validation;
}

const char *NeoM9nGnssInstance_NameGet(uint8_t instance)
{
    (void)instance;
    return "NEO-M9N GNSS";
}
SystemDeviceResult NeoM9nGnssInstance_Init(uint8_t instance) { return NeoM9nGnssAdapter_Init(instance); }
SystemDeviceResult NeoM9nGnssInstance_Start(uint8_t instance) { return NeoM9nGnssAdapter_Start(instance); }
SystemDeviceResult NeoM9nGnssInstance_Stop(uint8_t instance) { return NeoM9nGnssAdapter_Stop(instance); }
SystemDeviceResult NeoM9nGnssInstance_RuntimeOwnerActivate(uint8_t instance)
{ return NeoM9nGnssAdapter_RuntimeOwnerActivate(instance); }
SystemDeviceResult NeoM9nGnssInstance_Process(uint8_t instance)
{
    NeoM9nGnssAdapter_Process(instance);
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult NeoM9nGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance;
    return NeoM9nGnssAdapter_GetInfo(info);
}
SystemDeviceResult NeoM9nGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *mask)
{
    (void)instance;
    return NeoM9nGnssAdapter_GetCapabilities(mask);
}
SystemDeviceResult NeoM9nGnssInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{ return NeoM9nGnssAdapter_GetHealth(instance, health); }
SystemDeviceResult NeoM9nGnssInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{ return NeoM9nGnssAdapter_GetIoDiagnostics(instance, diagnostics); }
SystemDeviceResult NeoM9nGnssInstance_IoDetailGet(uint8_t instance, SystemGnssIoDetail *detail)
{ return NeoM9nGnssAdapter_GetIoDetail(instance, detail); }
SystemDeviceResult NeoM9nGnssInstance_LatestSampleGet(uint8_t instance, SystemGnssSample *sample)
{ return NeoM9nGnssAdapter_GetSample(instance, sample); }
SystemDeviceResult NeoM9nGnssInstance_TimeGet(uint8_t instance, SystemGnssTime *time)
{ return NeoM9nGnssAdapter_GetTime(instance, time); }
SystemDeviceResult NeoM9nGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result)
{
    (void)instance;
    return NeoM9nGnssAdapter_SelfTest(result);
}
SystemDeviceResult NeoM9nGnssInstance_ConfigApply(uint8_t instance,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{ return NeoM9nGnssAdapter_ApplyConfig(instance, config, report); }
SystemDeviceResult NeoM9nGnssInstance_ConfigVerify(uint8_t instance,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{ return NeoM9nGnssAdapter_VerifyConfig(instance, config, report); }
SystemDeviceResult NeoM9nGnssInstance_EffectiveConfigGet(uint8_t instance, SystemGnssConfig *config)
{ return NeoM9nGnssAdapter_GetConfig(instance, config); }
SystemDeviceResult NeoM9nGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise)
{
    (void)instance;
    return NeoM9nGnssAdapter_NoiseCharacteristicsGet(noise);
}
SystemDeviceResult NeoM9nGnssInstance_HardwareConfigRead(uint8_t instance,
    SystemGnssHardwareConfig *config)
{ return NeoM9nGnssAdapter_ReadHardwareConfig(instance, config); }
SystemDeviceResult NeoM9nGnssInstance_LastConfigReportGet(uint8_t instance,
    SystemGnssConfigTransactionReport *report)
{ return NeoM9nGnssAdapter_GetLastConfigReport(instance, report); }
SystemDeviceResult NeoM9nGnssInstance_SatelliteDiagnosticsRead(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{ return NeoM9nGnssAdapter_ReadSatelliteDiagnostics(instance, diagnostics); }
SystemDeviceResult NeoM9nGnssInstance_LatestSatelliteDiagnosticsGet(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{ return NeoM9nGnssAdapter_GetSatelliteDiagnostics(instance, diagnostics); }
SystemDeviceResult NeoM9nGnssInstance_RfDiagnosticsRead(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{ return NeoM9nGnssAdapter_ReadRfDiagnostics(instance, diagnostics); }
SystemDeviceResult NeoM9nGnssInstance_LatestRfDiagnosticsGet(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{ return NeoM9nGnssAdapter_GetRfDiagnostics(instance, diagnostics); }
