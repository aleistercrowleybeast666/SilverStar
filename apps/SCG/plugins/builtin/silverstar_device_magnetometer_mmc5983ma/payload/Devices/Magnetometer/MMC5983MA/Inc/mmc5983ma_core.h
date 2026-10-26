#ifndef __MMC5983MA_CORE_H
#define __MMC5983MA_CORE_H

#include <stdint.h>

#define MMC5983MA_SAMPLE_VALID_RAW (1UL << 0)
#define MMC5983MA_SAMPLE_VALID_PHYSICAL_UNIT (1UL << 1)
#define MMC5983MA_SAMPLE_VALID_CALIBRATED (1UL << 2)
#define MMC5983MA_SAMPLE_VALID_TEMPERATURE (1UL << 3)

/* Native sample; System conversion lives in Adapter. */
typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t raw[3];
    float magnetic_field_b_uT[3];
    float temperature_c;
    uint32_t valid_mask;
    uint8_t calibration_valid;
    uint16_t physical_device_id;
    uint16_t descriptor_id;
    uint8_t instance_id;
    /* Native physical sensor-axis uT^2 covariance, used only before correction.
     * Trust=1 requires sample time resolved to the active IMU's SystemTime
     * monotonic microsecond domain. Receive/decode proxy time leaves trust=0. */
    float covariance_sensor_uT2[9];
    uint8_t covariance_valid;
    uint8_t measurement_timestamp_trusted;
    /* Native evidence only. Source1 is JY decode proxy, NOT hardware receive or
     * sample time. Augmented EstimatorTask owns any statistical estimate. */
    uint32_t observation_quality_source;
    uint64_t decode_timestamp_us,processing_timestamp_us,accel_decode_timestamp_us,gyro_decode_timestamp_us;
    uint32_t transport_epoch,decode_queue_bytes,decode_span_us,transport_evidence_valid,imu_evidence_valid;
    float accel_sensor_mps2[3],gyro_sensor_radps[3];
} Mmc5983maSample;

typedef enum
{
    Mmc5983maBusOk = 0,
    Mmc5983maBusError
} Mmc5983maBusResult;

typedef struct
{
    void *bus;
} Mmc5983maPort;

Mmc5983maBusResult Mmc5983maBus_Read(void *bus, uint8_t register_address, uint8_t *bytes, uint8_t length);
Mmc5983maBusResult Mmc5983maBus_Write(void *bus, uint8_t register_address, uint8_t value);

typedef enum
{
    Mmc5983maStateProbe = 0,
    Mmc5983maStateReadConfig,
    Mmc5983maStateApplyConfig,
    Mmc5983maStateVerifyConfig,
    Mmc5983maStateSet,
    Mmc5983maStateTriggerMag,
    Mmc5983maStatePollMag,
    Mmc5983maStateReadMag,
    Mmc5983maStateTriggerTemp,
    Mmc5983maStatePollTemp,
    Mmc5983maStateReadTemp,
    Mmc5983maStateWaitPeriod,
    Mmc5983maStateFailed
} Mmc5983maState;

typedef enum
{
    Mmc5983maStepPending = 0,
    Mmc5983maStepSampleReady,
    Mmc5983maStepNotPresent,
    Mmc5983maStepBusError,
    Mmc5983maStepVerifyFailed,
    Mmc5983maStepMeasurementTimeout
} Mmc5983maStepResult;

typedef struct
{
    Mmc5983maPort port;
    Mmc5983maSample sample;
    Mmc5983maState state;
    uint64_t operation_started_us;
    uint64_t last_sample_us;
    uint32_t error_count;
    uint32_t sequence;
    uint8_t config_index;
} Mmc5983maContext;

void Mmc5983ma_Init(Mmc5983maContext *context, const Mmc5983maPort *port);
Mmc5983maStepResult Mmc5983ma_Step(Mmc5983maContext *context,
    uint64_t now_us);

#endif /* __MMC5983MA_CORE_H */
