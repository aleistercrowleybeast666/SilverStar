#include "neo_m8n_instance.h"
#include "ubx_system_adapter.h"
#include "project_resources.h"
#include <stddef.h>
#include <string.h>

static UbxSystemAdapter s_contexts[PROJECT_NEO_M8N_INSTANCE_COUNT];
_Static_assert(PROJECT_NEO_M8N_INSTANCE_COUNT <= 4U, "GNSS instance bound exceeded");

const char *NeoM8nGnssInstance_NameGet(uint8_t instance)
{
    return instance < PROJECT_NEO_M8N_INSTANCE_COUNT ? "NEO-M8N" : "Invalid GNSS";
}

SystemDeviceResult NeoM8nGnssInstance_Init(uint8_t instance)
{
    ProjectNeoM8nResources resources;
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectNeoM8nResources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return UbxSystemAdapter_Init(&s_contexts[instance], resources.uart, UBX_RECEIVER_NEO_M8N);
}

SystemDeviceResult NeoM8nGnssInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].started = 1U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].started = 0U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult NeoM8nGnssInstance_InfoGet( uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "NEO-M8N"; info->model_name = info->device_name;
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_CapabilitiesGet( uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_GNSS_CAP_POSITION | SYSTEM_GNSS_CAP_VELOCITY_3D | SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT | SYSTEM_GNSS_CAP_MSL_HEIGHT | SYSTEM_GNSS_CAP_ACCURACY_FIELDS;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_HealthGet( uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult NeoM8nGnssInstance_IoDiagnosticsGet( uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_IoDetailGet( uint8_t instance, SystemGnssIoDetail *detail)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->ubx_frame_count = s_contexts[instance].receiver.latest.sequence;
    detail->ubx_checksum_error_count = s_contexts[instance].receiver.checksum_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult NeoM8nGnssInstance_LatestSampleGet( uint8_t instance, SystemGnssSample *sample)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_SampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult NeoM8nGnssInstance_TimeGet( uint8_t instance, SystemGnssTime *time)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_TimeGet(&s_contexts[instance], time);
}

SystemDeviceResult NeoM8nGnssInstance_SelfTestRun( uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_ConfigApply( uint8_t instance, const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult NeoM8nGnssInstance_ConfigVerify( uint8_t instance, const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult NeoM8nGnssInstance_EffectiveConfigGet( uint8_t instance, SystemGnssConfig *config)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult NeoM8nGnssInstance_NoiseCharacteristicsGet( uint8_t instance, SystemGnssNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_HardwareConfigRead( uint8_t instance, SystemGnssHardwareConfig *config)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_HardwareConfigRead(&s_contexts[instance], config);
}

SystemDeviceResult NeoM8nGnssInstance_LastConfigReportGet( uint8_t instance, SystemGnssConfigTransactionReport *report)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_LastConfigReportGet(&s_contexts[instance], report);
}

SystemDeviceResult NeoM8nGnssInstance_SatelliteDiagnosticsRead( uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_LatestSatelliteDiagnosticsGet( uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_RfDiagnosticsRead( uint8_t instance, SystemGnssRfDiagnostics *diagnostics)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_LatestRfDiagnosticsGet( uint8_t instance, SystemGnssRfDiagnostics *diagnostics)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult NeoM8nGnssInstance_ConfigPersist(uint8_t instance,
    uint8_t persistent_layer, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_NEO_M8N_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigPersist(&s_contexts[instance], persistent_layer, report);
}
