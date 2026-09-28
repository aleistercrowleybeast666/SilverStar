#ifndef __NEO_M9N_INSTANCE_H
#define __NEO_M9N_INSTANCE_H

#include <stdint.h>

#include "system_gnss_if.h"

const char *NeoM9nGnssInstance_NameGet(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_Init(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_Start(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_Stop(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_Process(uint8_t instance);
SystemDeviceResult NeoM9nGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult NeoM9nGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult NeoM9nGnssInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult NeoM9nGnssInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult NeoM9nGnssInstance_IoDetailGet(
    uint8_t instance, SystemGnssIoDetail *detail);
SystemDeviceResult NeoM9nGnssInstance_LatestSampleGet(
    uint8_t instance, SystemGnssSample *sample);
SystemDeviceResult NeoM9nGnssInstance_TimeGet(
    uint8_t instance, SystemGnssTime *time);
SystemDeviceResult NeoM9nGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult NeoM9nGnssInstance_ConfigApply(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoM9nGnssInstance_ConfigVerify(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult NeoM9nGnssInstance_EffectiveConfigGet(
    uint8_t instance, SystemGnssConfig *config);
SystemDeviceResult NeoM9nGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult NeoM9nGnssInstance_HardwareConfigRead(
    uint8_t instance, SystemGnssHardwareConfig *config);
SystemDeviceResult NeoM9nGnssInstance_LastConfigReportGet(
    uint8_t instance, SystemGnssConfigTransactionReport *report);
SystemDeviceResult NeoM9nGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoM9nGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult NeoM9nGnssInstance_RfDiagnosticsRead(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult NeoM9nGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);

#endif /* __NEO_M9N_INSTANCE_H */
