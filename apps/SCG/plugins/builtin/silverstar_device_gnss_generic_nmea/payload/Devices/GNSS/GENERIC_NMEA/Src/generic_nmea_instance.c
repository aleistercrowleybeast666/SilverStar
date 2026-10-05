#include "generic_nmea_instance.h"

#include <stddef.h>
#include <string.h>

#include "generic_nmea_parser.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "project_resources.h"
#include "system_gnss_quality.h"

#define GENERIC_NMEA_STALE_US 1500000ULL

typedef struct
{
    GenericNmeaParser parser;
    SystemGnssSample published;
    PlatformUartId uart;
    SystemDeviceHealth health;
    uint8_t has_published;
    uint8_t started;
} GenericNmeaInstanceContext;

static GenericNmeaInstanceContext s_contexts[PROJECT_GENERIC_NMEA_INSTANCE_COUNT];
_Static_assert(PROJECT_GENERIC_NMEA_INSTANCE_COUNT <= 4U,
    "Generic NMEA GNSS instance bound exceeded");

static uint8_t GenericNmeaGnssInstance_Valid(uint8_t instance)
{
    return (uint8_t)(instance < PROJECT_GENERIC_NMEA_INSTANCE_COUNT);
}

const char *GenericNmeaGnssInstance_NameGet(uint8_t instance)
{
    return GenericNmeaGnssInstance_Valid(instance) != 0U ?
        "Generic NMEA GNSS" : "Invalid GNSS";
}

SystemDeviceResult GenericNmeaGnssInstance_Init(uint8_t instance)
{
    ProjectGenericNmeaResources resources;
    PlatformResult result;
    GenericNmeaInstanceContext *context;
    if (GenericNmeaGnssInstance_Valid(instance) == 0U)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectGenericNmeaResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    context = &s_contexts[instance];
    (void)memset(context, 0, sizeof(*context));
    context->uart = resources.uart;
    GenericNmeaParser_Init(&context->parser);
    result = PlatformUart_Init(context->uart);
    if ((result != PLATFORM_OK) && (result != PLATFORM_ALREADY_INITIALIZED))
    { return SYSTEM_DEVICE_IO_ERROR; }
    context->health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_Start(uint8_t instance)
{
    if (GenericNmeaGnssInstance_Valid(instance) == 0U)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_contexts[instance].health.initialized == 0U)
    { return SYSTEM_DEVICE_NOT_READY; }
    s_contexts[instance].started = 1U;
    s_contexts[instance].health.started = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_Stop(uint8_t instance)
{
    if (GenericNmeaGnssInstance_Valid(instance) == 0U)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].started = 0U;
    s_contexts[instance].health.started = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (GenericNmeaGnssInstance_Valid(instance) == 0U)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return s_contexts[instance].started != 0U ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult GenericNmeaGnssInstance_Process(uint8_t instance)
{
    GenericNmeaInstanceContext *context;
    uint8_t bytes[GENERIC_NMEA_MAX_BYTES_PER_PROCESS];
    uint16_t count = 0U;
    GenericNmeaFeedResult result;
    if (GenericNmeaGnssInstance_Valid(instance) == 0U)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    context = &s_contexts[instance];
    if (context->started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    PlatformUart_Process(context->uart);
    if (PlatformUart_Read(context->uart, bytes, sizeof(bytes), &count) != PLATFORM_OK)
    { context->health.error_count++; return SYSTEM_DEVICE_IO_ERROR; }
    result = GenericNmeaParser_Feed(&context->parser, bytes, count, PlatformTime_Us());
    if (result != GenericNmeaFeedOk) { context->health.error_count++; }
    if (context->parser.sequence != context->published.sequence)
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        context->published = context->parser.published;
        context->has_published = 1U;
        PlatformCritical_Exit(lock);
    }
    context->health.sample_count = context->parser.sequence;
    context->health.last_receive_timestamp_us = context->published.receive_timestamp_us;
    context->health.last_sample_timestamp_us = context->published.sample_timestamp_us;
    context->health.checksum_error_count = context->parser.checksum_errors;
    context->health.online = (uint8_t)(context->has_published != 0U &&
        PlatformTime_Us() >= context->published.receive_timestamp_us &&
        PlatformTime_Us() - context->published.receive_timestamp_us <=
        GENERIC_NMEA_STALE_US);
    context->health.healthy = context->health.online;
    return context->health.online != 0U ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult GenericNmeaGnssInstance_InfoGet(uint8_t instance,
    SystemDeviceInfo *info)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (info == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "Generic NMEA GNSS";
    info->model_name = "NMEA 0183 receiver";
    info->driver_version = "0.1.0-HARDWARE_UNVERIFIED";
    (void)GenericNmeaGnssInstance_CapabilitiesGet(instance, &info->capability_mask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_CapabilitiesGet(uint8_t instance,
    uint32_t *capability_mask)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) ||
        (capability_mask == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_GNSS_CAP_READ_ONLY;
    if ((s_contexts[instance].published.valid_fields &
         SYSTEM_GNSS_FIELD_POSITION) != 0U)
    { *capability_mask |= SYSTEM_GNSS_CAP_POSITION; }
    if ((s_contexts[instance].published.valid_fields &
         SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL) != 0U)
    { *capability_mask |= SYSTEM_GNSS_CAP_VELOCITY_2D; }
    if ((s_contexts[instance].published.valid_fields &
         SYSTEM_GNSS_FIELD_HEIGHT) != 0U)
    { *capability_mask |= SYSTEM_GNSS_CAP_MSL_HEIGHT; }
    if ((s_contexts[instance].published.valid_fields &
         (SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
          SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY)) != 0U)
    { *capability_mask |= SYSTEM_GNSS_CAP_ACCURACY_FIELDS; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_HealthGet(uint8_t instance,
    SystemDeviceHealth *health)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_contexts[instance].health;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    PlatformUartDiagnostics uart;
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (diagnostics == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    if (PlatformUart_DiagnosticsGet(s_contexts[instance].uart, &uart) != PLATFORM_OK)
    { return SYSTEM_DEVICE_IO_ERROR; }
    diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_UART;
    diagnostics->owner = SYSTEM_DEVICE_IO_OWNER_GNSS;
    diagnostics->rx_bytes = uart.rx_bytes;
    diagnostics->rx_discarded_bytes = uart.rx_discarded_bytes;
    diagnostics->integrity_error_count = s_contexts[instance].parser.checksum_errors;
    diagnostics->valid_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT |
        SYSTEM_DEVICE_IO_VALID_RX_BYTES | SYSTEM_DEVICE_IO_VALID_RX_DISCARDED |
        SYSTEM_DEVICE_IO_VALID_INTEGRITY_ERRORS;
    diagnostics->supported_mask = diagnostics->valid_mask;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_IoDetailGet(uint8_t instance,
    SystemGnssIoDetail *detail)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (detail == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(detail, 0, sizeof(*detail));
    detail->nmea_sentence_count = s_contexts[instance].parser.accepted_sentences;
    detail->nmea_checksum_ok_count = detail->nmea_sentence_count;
    detail->nmea_checksum_error_count = s_contexts[instance].parser.checksum_errors;
    detail->parser_resync_count = s_contexts[instance].parser.resync_count +
        s_contexts[instance].parser.overlength_sentences;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_LatestSampleGet(uint8_t instance,
    SystemGnssSample *sample)
{
    PlatformCriticalState lock;
    uint64_t now_us;
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_contexts[instance].has_published == 0U)
    { return SYSTEM_DEVICE_NOT_READY; }
    lock = PlatformCritical_Enter();
    *sample = s_contexts[instance].published;
    PlatformCritical_Exit(lock);
    now_us = PlatformTime_Us();
    sample->online = (uint8_t)(now_us >= sample->receive_timestamp_us &&
        now_us - sample->receive_timestamp_us <= GENERIC_NMEA_STALE_US);
    sample->measurement_timestamp_trusted = 0U;
    return SystemGnssQuality_Evaluate(sample, now_us);
}

SystemDeviceResult GenericNmeaGnssInstance_TimeGet(uint8_t instance,
    SystemGnssTime *time)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (time == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(time, 0, sizeof(*time));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_SelfTestRun(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (result == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_ConfigApply(uint8_t instance,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) ||
        (config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->unsupported_optional_mask = config->requested_mask & ~config->required_mask;
    report->unsupported_required_mask = config->required_mask;
    return config->requested_mask == 0U ?
        SYSTEM_DEVICE_CONFIG_NO_ACTION : SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_ConfigVerify(uint8_t instance,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    return GenericNmeaGnssInstance_ConfigApply(instance, config, report);
}

SystemDeviceResult GenericNmeaGnssInstance_EffectiveConfigGet(uint8_t instance,
    SystemGnssConfig *config)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult GenericNmeaGnssInstance_NoiseCharacteristicsGet(uint8_t instance,
    SystemGnssNoiseCharacteristics *noise)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (noise == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_HardwareConfigRead(uint8_t instance,
    SystemGnssHardwareConfig *config)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (config == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_LastConfigReportGet(uint8_t instance,
    SystemGnssConfigTransactionReport *report)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_SatelliteDiagnosticsRead(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) ||
        (diagnostics == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_LatestSatelliteDiagnosticsGet(uint8_t instance,
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    return GenericNmeaGnssInstance_SatelliteDiagnosticsRead(instance, diagnostics);
}

SystemDeviceResult GenericNmeaGnssInstance_RfDiagnosticsRead(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{
    if ((GenericNmeaGnssInstance_Valid(instance) == 0U) ||
        (diagnostics == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult GenericNmeaGnssInstance_LatestRfDiagnosticsGet(uint8_t instance,
    SystemGnssRfDiagnostics *diagnostics)
{
    return GenericNmeaGnssInstance_RfDiagnosticsRead(instance, diagnostics);
}
