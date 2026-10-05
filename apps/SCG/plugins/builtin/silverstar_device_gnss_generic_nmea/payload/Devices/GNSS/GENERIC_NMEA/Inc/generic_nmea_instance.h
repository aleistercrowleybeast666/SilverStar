#ifndef __GENERIC_NMEA_INSTANCE_H
#define __GENERIC_NMEA_INSTANCE_H

#include <stdint.h>

#include "system_gnss_if.h"

const char *GenericNmeaGnssInstance_NameGet(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_Init(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_Start(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_Stop(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_Process(uint8_t instance);
SystemDeviceResult GenericNmeaGnssInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult GenericNmeaGnssInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult GenericNmeaGnssInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult GenericNmeaGnssInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult GenericNmeaGnssInstance_IoDetailGet(
    uint8_t instance, SystemGnssIoDetail *detail);
SystemDeviceResult GenericNmeaGnssInstance_LatestSampleGet(
    uint8_t instance, SystemGnssSample *sample);
SystemDeviceResult GenericNmeaGnssInstance_TimeGet(
    uint8_t instance, SystemGnssTime *time);
SystemDeviceResult GenericNmeaGnssInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult GenericNmeaGnssInstance_ConfigApply(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult GenericNmeaGnssInstance_ConfigVerify(
    uint8_t instance, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult GenericNmeaGnssInstance_EffectiveConfigGet(
    uint8_t instance, SystemGnssConfig *config);
SystemDeviceResult GenericNmeaGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult GenericNmeaGnssInstance_HardwareConfigRead(
    uint8_t instance, SystemGnssHardwareConfig *config);
SystemDeviceResult GenericNmeaGnssInstance_LastConfigReportGet(
    uint8_t instance, SystemGnssConfigTransactionReport *report);
SystemDeviceResult GenericNmeaGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult GenericNmeaGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult GenericNmeaGnssInstance_RfDiagnosticsRead(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult GenericNmeaGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance, SystemGnssRfDiagnostics *diagnostics);

#endif /* __GENERIC_NMEA_INSTANCE_H */
