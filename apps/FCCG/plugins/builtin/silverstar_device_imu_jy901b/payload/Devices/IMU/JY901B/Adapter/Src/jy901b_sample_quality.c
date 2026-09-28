#include "jy901b_sample_quality.h"

#include <stddef.h>
#include "silverstar_assert.h"

#define JY901B_RAW_NEAR_RANGE 31129L
#define JY901B_PERIOD_FALLBACK_US 100000ULL

static uint32_t Jy901bSample_AxisQuality(int32_t raw)
{
    if ((raw <= -32768L) || (raw >= 32767L))
    {
        return SYSTEM_IMU_QUALITY_NEAR_RANGE | SYSTEM_IMU_QUALITY_CLIPPED;
    }
    return ((raw <= -JY901B_RAW_NEAR_RANGE) || (raw >= JY901B_RAW_NEAR_RANGE)) ?
        SYSTEM_IMU_QUALITY_NEAR_RANGE : 0U;
}

SystemDeviceResult Jy901bSample_QualityEvaluate(SystemImuSample *sample,
    const SystemImuConfig *verified_config, uint64_t previous_epoch_us,
    uint64_t pair_skew_us)
{
    uint8_t axis;
    uint64_t period_us = JY901B_PERIOD_FALLBACK_US;
    uint32_t range_mask = SYSTEM_IMU_CFG_ACCEL_RANGE | SYSTEM_IMU_CFG_GYRO_RANGE;
    if ((sample == NULL) || (verified_config == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemImuSample, SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(verified_config, SystemImuConfig, SILVERSTAR_ASSERT_MODULE_DEVICE);
    sample->quality_flags = SYSTEM_IMU_QUALITY_TIME_UNCERTAIN;
    if ((verified_config->requested_mask & range_mask) != range_mask)
    {
        sample->quality_flags |= SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED;
    }
    if (verified_config->output_rate_hz != 0U)
    {
        period_us = 1000000ULL / verified_config->output_rate_hz;
    }
    if ((sample->sample_timestamp_us == 0U) ||
        (sample->receive_timestamp_us < sample->sample_timestamp_us) ||
        ((previous_epoch_us != 0U) &&
         ((sample->sample_timestamp_us <= previous_epoch_us) ||
          (sample->sample_timestamp_us - previous_epoch_us > 5U * period_us))))
    {
        sample->quality_flags |= SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY;
    }
    if (previous_epoch_us == 0U) { sample->quality_flags |= SYSTEM_IMU_QUALITY_HISTORY_RESET; }
    if (pair_skew_us > period_us)
    {
        sample->quality_flags |= SYSTEM_IMU_QUALITY_PAIR_SKEW;
    }
    for (axis = 0U; axis < 3U; axis++)
    {
        sample->quality_flags |= Jy901bSample_AxisQuality(sample->accel_raw[axis]);
        sample->quality_flags |= Jy901bSample_AxisQuality(sample->gyro_raw[axis]);
    }
    return SYSTEM_DEVICE_OK;
}
