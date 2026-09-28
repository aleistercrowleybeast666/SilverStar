#include "max_m10s_instance.h"
#include "ubx_system_adapter.h"
#include "project_resources.h"
#include <stddef.h>
#include <string.h>

static UbxSystemAdapter s_contexts[PROJECT_MAX_M10S_INSTANCE_COUNT];
_Static_assert(PROJECT_MAX_M10S_INSTANCE_COUNT <= 4U, "GNSS instance bound exceeded");

const char *MaxM10sGnssInstance_NameGet(uint8_t instance)
{
    return instance < PROJECT_MAX_M10S_INSTANCE_COUNT ? "MAX-M10S" : "Invalid GNSS";
}

SystemDeviceResult MaxM10sGnssInstance_Init(uint8_t instance)
{
    ProjectMaxM10sResources resources;
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectMaxM10sResources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return UbxSystemAdapter_Init(&s_contexts[instance], resources.uart, UBX_RECEIVER_MAX_M10S);
}

SystemDeviceResult MaxM10sGnssInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].started = 1U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].started = 0U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    s_contexts[instance].health.started = s_contexts[instance].started;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult MaxM10sGnssInstance_InfoGet( uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "MAX-M10S"; info->model_name = info->device_name;
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_CapabilitiesGet( uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_GNSS_CAP_POSITION | SYSTEM_GNSS_CAP_VELOCITY_3D | SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT | SYSTEM_GNSS_CAP_MSL_HEIGHT | SYSTEM_GNSS_CAP_ACCURACY_FIELDS;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_HealthGet( uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult MaxM10sGnssInstance_IoDiagnosticsGet( uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_IoDetailGet( uint8_t instance, SystemGnssIoDetail *detail)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->ubx_frame_count = s_contexts[instance].receiver.latest.sequence;
    detail->ubx_checksum_error_count = s_contexts[instance].receiver.checksum_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult MaxM10sGnssInstance_LatestSampleGet( uint8_t instance, SystemGnssSample *sample)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_SampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult MaxM10sGnssInstance_TimeGet( uint8_t instance, SystemGnssTime *time)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_TimeGet(&s_contexts[instance], time);
}

SystemDeviceResult MaxM10sGnssInstance_SelfTestRun( uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_ConfigApply( uint8_t instance, const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult MaxM10sGnssInstance_ConfigVerify( uint8_t instance, const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult MaxM10sGnssInstance_EffectiveConfigGet( uint8_t instance, SystemGnssConfig *config)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult MaxM10sGnssInstance_NoiseCharacteristicsGet( uint8_t instance, SystemGnssNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_HardwareConfigRead( uint8_t instance, SystemGnssHardwareConfig *config)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_HardwareConfigRead(&s_contexts[instance], config);
}

SystemDeviceResult MaxM10sGnssInstance_LastConfigReportGet( uint8_t instance, SystemGnssConfigTransactionReport *report)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_LastConfigReportGet(&s_contexts[instance], report);
}

SystemDeviceResult MaxM10sGnssInstance_SatelliteDiagnosticsRead( uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_LatestSatelliteDiagnosticsGet( uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_RfDiagnosticsRead( uint8_t instance, SystemGnssRfDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_LatestRfDiagnosticsGet( uint8_t instance, SystemGnssRfDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult MaxM10sGnssInstance_ConfigPersist(uint8_t instance,
    uint8_t persistent_layer, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MAX_M10S_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return UbxSystemAdapter_ConfigPersist(&s_contexts[instance], persistent_layer, report);
}
