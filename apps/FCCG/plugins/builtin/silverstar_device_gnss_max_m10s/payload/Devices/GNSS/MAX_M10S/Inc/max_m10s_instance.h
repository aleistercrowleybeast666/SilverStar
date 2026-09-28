#ifndef __MAX_M10S_INSTANCE_H
#define __MAX_M10S_INSTANCE_H

#include <stdint.h>

#include "system_gnss_if.h"

const char *MaxM10sGnssInstance_NameGet(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_Init(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_Start(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_Stop(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_Process(uint8_t instance);
SystemDeviceResult MaxM10sGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult MaxM10sGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult MaxM10sGnssInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult MaxM10sGnssInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult MaxM10sGnssInstance_IoDetailGet(
    uint8_t instance, SystemGnssIoDetail *detail);
SystemDeviceResult MaxM10sGnssInstance_LatestSampleGet(
    uint8_t instance, SystemGnssSample *sample);
SystemDeviceResult MaxM10sGnssInstance_TimeGet(
    uint8_t instance, SystemGnssTime *time);
SystemDeviceResult MaxM10sGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult MaxM10sGnssInstance_ConfigApply(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult MaxM10sGnssInstance_ConfigVerify(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult MaxM10sGnssInstance_EffectiveConfigGet(
    uint8_t instance, SystemGnssConfig *config);
SystemDeviceResult MaxM10sGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult MaxM10sGnssInstance_HardwareConfigRead(
    uint8_t instance, SystemGnssHardwareConfig *config);
SystemDeviceResult MaxM10sGnssInstance_LastConfigReportGet(
    uint8_t instance, SystemGnssConfigTransactionReport *report);
SystemDeviceResult MaxM10sGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult MaxM10sGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult MaxM10sGnssInstance_RfDiagnosticsRead(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult MaxM10sGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);

/* Explicit maintenance only; layer is UBX_RECEIVER_LAYER_BBR or FLASH.
 * Unsupported model/layer combinations are rejected before any write. */
SystemDeviceResult MaxM10sGnssInstance_ConfigPersist(uint8_t instance,
    uint8_t persistent_layer, SystemDeviceConfigReport *report);

#endif /* __MAX_M10S_INSTANCE_H */
