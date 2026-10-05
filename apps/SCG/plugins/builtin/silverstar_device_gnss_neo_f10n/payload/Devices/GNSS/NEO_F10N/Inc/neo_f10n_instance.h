#ifndef __NEO_F10N_INSTANCE_H
#define __NEO_F10N_INSTANCE_H

#include <stdint.h>

#include "system_gnss_if.h"

const char *NeoF10nGnssInstance_NameGet(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_Init(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_Start(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_Stop(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_Process(uint8_t instance);
SystemDeviceResult NeoF10nGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult NeoF10nGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult NeoF10nGnssInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult NeoF10nGnssInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult NeoF10nGnssInstance_IoDetailGet(
    uint8_t instance, SystemGnssIoDetail *detail);
SystemDeviceResult NeoF10nGnssInstance_LatestSampleGet(
    uint8_t instance, SystemGnssSample *sample);
SystemDeviceResult NeoF10nGnssInstance_TimeGet(
    uint8_t instance, SystemGnssTime *time);
SystemDeviceResult NeoF10nGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult NeoF10nGnssInstance_ConfigApply(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoF10nGnssInstance_ConfigVerify(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoF10nGnssInstance_EffectiveConfigGet(
    uint8_t instance, SystemGnssConfig *config);
SystemDeviceResult NeoF10nGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult NeoF10nGnssInstance_HardwareConfigRead(
    uint8_t instance, SystemGnssHardwareConfig *config);
SystemDeviceResult NeoF10nGnssInstance_LastConfigReportGet(
    uint8_t instance, SystemGnssConfigTransactionReport *report);
SystemDeviceResult NeoF10nGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoF10nGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoF10nGnssInstance_RfDiagnosticsRead(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult NeoF10nGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);

/* Explicit maintenance only; layer is UBX_RECEIVER_LAYER_BBR or FLASH.
 * Unsupported model/layer combinations are rejected before any write. */
SystemDeviceResult NeoF10nGnssInstance_ConfigPersist(uint8_t instance,
    uint8_t persistent_layer, SystemDeviceConfigReport *report);

#endif /* __NEO_F10N_INSTANCE_H */
