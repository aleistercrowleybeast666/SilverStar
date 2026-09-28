#ifndef __PROJECT_DEVICE_INSTANCES_H
#define __PROJECT_DEVICE_INSTANCES_H

#include <stdint.h>

#include "system_barometer_if.h"
#include "system_descriptor_if.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_power_if.h"
#include "system_telemetry_transport_if.h"

#define PROJECT_PHYSICAL_DEVICE_ID_NONE       0U
#define PROJECT_PHYSICAL_DEVICE_ID_JY901B     1U
#define PROJECT_PHYSICAL_DEVICE_ID_NEO_M9N    2U
#define PROJECT_PHYSICAL_DEVICE_ID_E28_SX1281 3U
#define PROJECT_PHYSICAL_DEVICE_ID_CONSOLE    4U
#define PROJECT_PHYSICAL_DEVICE_ID_POWER_ADC  5U
#define PROJECT_PHYSICAL_DEVICE_ID_STORAGE    6U
#define PROJECT_PHYSICAL_DEVICE_ID_OUTPUT     7U

#define PROJECT_DESCRIPTOR_ID_IMU_0       1U
#define PROJECT_DESCRIPTOR_ID_GNSS_0      2U
#define PROJECT_DESCRIPTOR_ID_BARO_0      3U
#define PROJECT_DESCRIPTOR_ID_ATTITUDE_0  4U
#define PROJECT_DESCRIPTOR_ID_TELEMETRY_0 5U
#define PROJECT_DESCRIPTOR_ID_CONSOLE_0   6U
#define PROJECT_DESCRIPTOR_ID_POWER_0     7U
#define PROJECT_DESCRIPTOR_ID_STORAGE_0   8U
#define PROJECT_DESCRIPTOR_ID_LOG_SINK_0  9U
#define PROJECT_DESCRIPTOR_ID_OUTPUT_0    10U
#define PROJECT_DESCRIPTOR_ID_ACTION_0    11U
#define PROJECT_DESCRIPTOR_ID_TIME_0      12U
#define PROJECT_DESCRIPTOR_ID_MAG_0       13U

/* FCCG-owned static bounds for per-capability runtime state.  The current
 * reference project binds one endpoint per class; the bound deliberately
 * permits a future generated project to bind additional distinct plugins. */
#define PROJECT_IMU_INSTANCE_COUNT_MAX          4U
#define PROJECT_GNSS_INSTANCE_COUNT_MAX         4U
#define PROJECT_BAROMETER_INSTANCE_COUNT_MAX    4U
#define PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX 4U
#define PROJECT_ATTITUDE_INSTANCE_COUNT_MAX     4U
#define PROJECT_TELEMETRY_INSTANCE_COUNT_MAX    4U
#define PROJECT_POWER_INSTANCE_COUNT_MAX        4U

uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass device_class);
SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor);
SystemDeviceResult ProjectDeviceInstance_InfoGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceInfo *info);
SystemDeviceResult ProjectDeviceInstance_CapabilitiesGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    uint32_t *capability_mask);
SystemDeviceResult ProjectDeviceInstance_HealthGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceHealth *health);
SystemDeviceResult ProjectDeviceInstance_IoDiagnosticsGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceIoDiagnostics *diagnostics,
    SystemDeviceDescriptor *owner_descriptor);

uint8_t ProjectImuInstance_CountGet(void);
SystemDeviceResult ProjectImuInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_RuntimeOwnerActivate(
    uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_Process(uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectImuInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectImuInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectImuInstance_LatestSampleGet(
    uint8_t instance_id, SystemImuSample *sample);
SystemDeviceResult ProjectImuInstance_NextSampleGet(
    uint8_t instance_id, SystemImuSample *sample);
SystemDeviceResult ProjectImuInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectImuInstance_ConfigApply(
    uint8_t instance_id, const SystemImuConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectImuInstance_ConfigVerify(
    uint8_t instance_id, const SystemImuConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectImuInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemImuConfig *config);
SystemDeviceResult ProjectImuInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemImuNoiseCharacteristics *noise);
SystemDeviceResult ProjectImuInstance_IoDetailGet(
    uint8_t instance_id, SystemImuIoDetail *detail);
SystemDeviceResult ProjectImuInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics);

uint8_t ProjectGnssInstance_CountGet(void);
SystemDeviceResult ProjectGnssInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_RuntimeOwnerActivate(
    uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_Process(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectGnssInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectGnssInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample);
SystemDeviceResult ProjectGnssInstance_TimeGet(
    uint8_t instance_id, SystemGnssTime *time);
SystemDeviceResult ProjectGnssInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectGnssInstance_ConfigApply(
    uint8_t instance_id, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectGnssInstance_ConfigVerify(
    uint8_t instance_id, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectGnssInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemGnssConfig *config);
SystemDeviceResult ProjectGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult ProjectGnssInstance_HardwareConfigRead(
    uint8_t instance_id, SystemGnssHardwareConfig *config);
SystemDeviceResult ProjectGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance_id, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult ProjectGnssInstance_RfDiagnosticsRead(
    uint8_t instance_id, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult ProjectGnssInstance_LastConfigReportGet(
    uint8_t instance_id, SystemGnssConfigTransactionReport *report);
SystemDeviceResult ProjectGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance_id, SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult ProjectGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance_id, SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult ProjectGnssInstance_IoDetailGet(
    uint8_t instance_id, SystemGnssIoDetail *detail);
SystemDeviceResult ProjectGnssInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics);

uint8_t ProjectBarometerInstance_CountGet(void);
SystemDeviceResult ProjectBarometerInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectBarometerInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectBarometerInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectBarometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectBarometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectBarometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemBarometerSample *sample);
SystemDeviceResult ProjectBarometerInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectBarometerInstance_ConfigApply(
    uint8_t instance_id, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectBarometerInstance_ConfigVerify(
    uint8_t instance_id, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectBarometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemBarometerConfig *config);
SystemDeviceResult ProjectBarometerInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemBarometerNoiseCharacteristics *noise);

uint8_t ProjectMagnetometerInstance_CountGet(void);
SystemDeviceResult ProjectMagnetometerInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectMagnetometerInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectMagnetometerInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectMagnetometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectMagnetometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample);
SystemDeviceResult ProjectMagnetometerInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectMagnetometerInstance_ConfigApply(
    uint8_t instance_id, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectMagnetometerInstance_ConfigVerify(
    uint8_t instance_id, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectMagnetometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemMagnetometerConfig *config);

uint8_t ProjectAttitudeInstance_CountGet(void);
SystemDeviceResult ProjectAttitudeInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectAttitudeInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectAttitudeInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectAttitudeInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectAttitudeInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectAttitudeInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectAttitudeInstance_LatestSampleGet(
    uint8_t instance_id, SystemHardwareQuaternionSample *sample);
SystemDeviceResult ProjectAttitudeInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectAttitudeInstance_ConfigApply(
    uint8_t instance_id, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectAttitudeInstance_ConfigVerify(
    uint8_t instance_id, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult ProjectAttitudeInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemHardwareQuaternionConfig *config);

uint8_t ProjectTelemetryInstance_CountGet(void);
SystemDeviceResult ProjectTelemetryInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_Stop(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_Send(
    uint8_t instance_id, const uint8_t *data, uint16_t length);
SystemDeviceResult ProjectTelemetryInstance_Receive(
    uint8_t instance_id, uint8_t *data, uint16_t capacity,
    uint16_t *length);
SystemDeviceResult ProjectTelemetryInstance_Process(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectTelemetryInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectTelemetryInstance_HealthGet(
    uint8_t instance_id, SystemTelemetryHealth *health);
SystemDeviceResult ProjectTelemetryInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult ProjectTelemetryInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result);
SystemDeviceResult ProjectTelemetryInstance_MtuGet(
    uint8_t instance_id, uint16_t *mtu);

uint8_t ProjectPowerInstance_CountGet(void);
SystemDeviceResult ProjectPowerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info);
SystemDeviceResult ProjectPowerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask);
SystemDeviceResult ProjectPowerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health);
SystemDeviceResult ProjectPowerInstance_LatestSampleGet(
    uint8_t instance_id, SystemPowerSample *sample);
SystemDeviceResult ProjectPowerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemPowerConfig *config);

#endif /* __PROJECT_DEVICE_INSTANCES_H */
