#ifndef __SYSTEM_IMU_IF_H
#define __SYSTEM_IMU_IF_H

#include "system_device_types.h"

#define SYSTEM_IMU_VALID_ACCEL       (1UL << 0)
#define SYSTEM_IMU_VALID_GYRO        (1UL << 1)
#define SYSTEM_IMU_VALID_TEMPERATURE (1UL << 2)

#define SYSTEM_IMU_CAP_ACCEL               (1UL << 0)
#define SYSTEM_IMU_CAP_GYRO                (1UL << 1)
#define SYSTEM_IMU_CAP_TEMPERATURE         (1UL << 2)
#define SYSTEM_IMU_CAP_SELF_TEST           (1UL << 3)
#define SYSTEM_IMU_CAP_CONFIG_OUTPUT_RATE  (1UL << 4)
#define SYSTEM_IMU_CAP_CONFIG_BANDWIDTH    (1UL << 5)
#define SYSTEM_IMU_CAP_CONFIG_RANGE        (1UL << 6)
#define SYSTEM_IMU_CAP_DATA_READY          (1UL << 7)

#define SYSTEM_IMU_CFG_OUTPUT_RATE     (1UL << 0)
#define SYSTEM_IMU_CFG_ACCEL_BANDWIDTH (1UL << 1)
#define SYSTEM_IMU_CFG_GYRO_BANDWIDTH  (1UL << 2)
#define SYSTEM_IMU_CFG_ACCEL_RANGE     (1UL << 3)
#define SYSTEM_IMU_CFG_GYRO_RANGE      (1UL << 4)

#define SYSTEM_IMU_NOISE_VALID_PROCESS_ACCEL_STD (1UL << 0)

#define SYSTEM_IMU_QUALITY_NEAR_RANGE         (1UL << 0)
#define SYSTEM_IMU_QUALITY_CLIPPED            (1UL << 1)
#define SYSTEM_IMU_QUALITY_TIME_UNCERTAIN     (1UL << 2)
#define SYSTEM_IMU_QUALITY_HISTORY_RESET      (1UL << 3)
#define SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY  (1UL << 4)
#define SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED   (1UL << 5)
#define SYSTEM_IMU_QUALITY_PAIR_SKEW          (1UL << 6)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t accel_raw[3];
    int32_t gyro_raw[3];
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float temperature_c;
    uint32_t valid_mask;
    /* Raw samples retain their actual sign/value even at the ADC rails.
     * A receive-time proxy is never advertised as a hardware sample epoch. */
    uint32_t quality_flags;
} SystemImuSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
    float accel_bandwidth_hz;
    float gyro_bandwidth_hz;
    float accel_range_g;
    float gyro_range_dps;
} SystemImuConfig;

typedef struct
{
    float accel_noise_density_mps2_sqrt_hz[3];
    float gyro_noise_density_radps_sqrt_hz[3];
    /* Estimator ENU E/N/U recommendation, not live sample uncertainty. */
    float recommended_process_accel_std_mps2[3];
    uint32_t valid_mask;
} SystemImuNoiseCharacteristics;

typedef struct
{
    uint32_t valid_frame_count;
    uint32_t checksum_error_count;
    uint32_t parser_resync_count;
    uint32_t config_generation;
    uint8_t config_generation_valid;
} SystemImuIoDetail;

const char *SystemImu_NameGet(void);
SystemDeviceResult SystemImu_Init(void);
SystemDeviceResult SystemImu_Start(void);
SystemDeviceResult SystemImu_Stop(void);
SystemDeviceResult SystemImu_RuntimeOwnerActivate(void);
void SystemImu_Process(void);
SystemDeviceResult SystemImu_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemImu_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemImu_IoDetailGet(SystemImuIoDetail *detail);
SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample);
SystemDeviceResult SystemImu_NextSampleGet(SystemImuSample *sample);
SystemDeviceResult SystemImu_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemImu_ConfigApply(const SystemImuConfig *config,
                                         SystemDeviceConfigReport *report);
SystemDeviceResult SystemImu_ConfigVerify(const SystemImuConfig *config,
                                          SystemDeviceConfigReport *report);
SystemDeviceResult SystemImu_EffectiveConfigGet(SystemImuConfig *config);
SystemDeviceResult SystemImu_NoiseCharacteristicsGet(
    SystemImuNoiseCharacteristics *noise);

#endif /* __SYSTEM_IMU_IF_H */
