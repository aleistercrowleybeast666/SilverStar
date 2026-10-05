#ifndef __NEO_M8N_INSTANCE_H
#define __NEO_M8N_INSTANCE_H

#include <stdint.h>

#include "system_gnss_if.h"

const char *NeoM8nGnssInstance_NameGet(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_Init(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_Start(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_Stop(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_Process(uint8_t instance);
SystemDeviceResult NeoM8nGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult NeoM8nGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult NeoM8nGnssInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult NeoM8nGnssInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult NeoM8nGnssInstance_IoDetailGet(
    uint8_t instance, SystemGnssIoDetail *detail);
SystemDeviceResult NeoM8nGnssInstance_LatestSampleGet(
    uint8_t instance, SystemGnssSample *sample);
SystemDeviceResult NeoM8nGnssInstance_TimeGet(
    uint8_t instance, SystemGnssTime *time);
SystemDeviceResult NeoM8nGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult NeoM8nGnssInstance_ConfigApply(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoM8nGnssInstance_ConfigVerify(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoM8nGnssInstance_EffectiveConfigGet(
    uint8_t instance, SystemGnssConfig *config);
SystemDeviceResult NeoM8nGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult NeoM8nGnssInstance_HardwareConfigRead(
    uint8_t instance, SystemGnssHardwareConfig *config);
SystemDeviceResult NeoM8nGnssInstance_LastConfigReportGet(
    uint8_t instance, SystemGnssConfigTransactionReport *report);
SystemDeviceResult NeoM8nGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoM8nGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoM8nGnssInstance_RfDiagnosticsRead(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult NeoM8nGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);

/* Explicit maintenance only; layer is UBX_RECEIVER_LAYER_BBR or FLASH.
 * Unsupported model/layer combinations are rejected before any write. */
SystemDeviceResult NeoM8nGnssInstance_ConfigPersist(uint8_t instance,
    uint8_t persistent_layer, SystemDeviceConfigReport *report);

#endif /* __NEO_M8N_INSTANCE_H */
