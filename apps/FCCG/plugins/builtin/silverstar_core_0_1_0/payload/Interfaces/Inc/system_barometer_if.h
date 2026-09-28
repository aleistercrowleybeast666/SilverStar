#ifndef __SYSTEM_BAROMETER_IF_H
#define __SYSTEM_BAROMETER_IF_H

#include "system_device_types.h"

#define SYSTEM_BARO_FIELD_PRESSURE    (1UL << 0)
#define SYSTEM_BARO_FIELD_ALTITUDE    (1UL << 1)
#define SYSTEM_BARO_FIELD_VARIANCE    (1UL << 2)
#define SYSTEM_BARO_FIELD_TEMPERATURE (1UL << 3)

#define SYSTEM_BARO_VALID_PRESSURE SYSTEM_BARO_FIELD_PRESSURE
#define SYSTEM_BARO_VALID_ALTITUDE SYSTEM_BARO_FIELD_ALTITUDE
#define SYSTEM_BARO_VALID_VARIANCE SYSTEM_BARO_FIELD_VARIANCE

#define SYSTEM_BARO_CFG_OUTPUT_RATE (1UL << 0)

#define SYSTEM_BAROMETER_NOISE_VALID_ALTITUDE_STD (1UL << 0)
#define SYSTEM_BAROMETER_NOISE_VALID_PRESSURE_STD (1UL << 1)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    /* sample_timestamp_us is already on MCU monotonic axis when trusted. */
    uint8_t measurement_timestamp_trusted;
    uint32_t sequence;
    int32_t pressure_raw_pa;
    int32_t altitude_raw_cm;
    float pressure_pa;
    float altitude_m;
    float altitude_variance_m2;
    float temperature_c;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t valid_mask;
} SystemBarometerSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
} SystemBarometerConfig;

typedef struct
{
    float recommended_altitude_std_m;
    float pressure_noise_std_pa;
    uint32_t valid_mask;
} SystemBarometerNoiseCharacteristics;

const char *SystemBarometer_NameGet(void);
SystemDeviceResult SystemBarometer_Init(void);
SystemDeviceResult SystemBarometer_Start(void);
SystemDeviceResult SystemBarometer_Stop(void);
void SystemBarometer_Process(void);
SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemBarometer_LatestSampleGet(
    SystemBarometerSample *sample);
SystemDeviceResult SystemBarometer_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemBarometer_ConfigApply(
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemBarometer_ConfigVerify(
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemBarometer_EffectiveConfigGet(
    SystemBarometerConfig *config);
SystemDeviceResult SystemBarometer_NoiseCharacteristicsGet(
    SystemBarometerNoiseCharacteristics *noise);

#endif /* __SYSTEM_BAROMETER_IF_H */
