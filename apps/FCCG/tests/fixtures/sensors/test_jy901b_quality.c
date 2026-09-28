#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "jy901b_sample_quality.h"
#include "jy901b_device.h"
#include "silverstar_assert.h"

void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module_id, const char *file_name, uint32_t line)
{
    (void)module_id;
    (void)file_name;
    (void)line;
    assert(object != NULL && ((uintptr_t)object % alignment) == 0U);
}

/* Preserve both pre-change sample sizes: no per-queue RAM expansion. */
_Static_assert(sizeof(SystemImuSample) == 80U, "System IMU sample RAM changed");
_Static_assert(sizeof(Jy901bImuSample) == 48U, "JY901B native FIFO RAM changed");

int main(void)
{
    SystemImuSample sample;
    SystemImuConfig config;
    memset(&sample, 0, sizeof(sample));
    memset(&config, 0, sizeof(config));
    sample.sample_timestamp_us = 1000000U;
    sample.receive_timestamp_us = 1000000U;
    sample.accel_raw[2] = -32768;
    config.output_rate_hz = 200U;
    assert(Jy901bSample_QualityEvaluate(&sample, &config, 995000U, 0U) == SYSTEM_DEVICE_OK);
    assert(sample.accel_raw[2] == -32768);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_CLIPPED) != 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED) != 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_TIME_UNCERTAIN) != 0U);
    config.requested_mask = SYSTEM_IMU_CFG_ACCEL_RANGE | SYSTEM_IMU_CFG_GYRO_RANGE;
    config.accel_range_g = 16.0F;
    config.gyro_range_dps = 2000.0F;
    sample.accel_raw[2] = 32000;
    assert(Jy901bSample_QualityEvaluate(&sample, &config, 1000000U, 5001U) == SYSTEM_DEVICE_OK);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_NEAR_RANGE) != 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_CLIPPED) == 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY) != 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_PAIR_SKEW) != 0U);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED) == 0U);
    sample.accel_raw[2] = 2048;
    assert(Jy901bSample_QualityEvaluate(&sample, &config, 900000U, 0U) == SYSTEM_DEVICE_OK);
    assert((sample.quality_flags & SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY) != 0U);
    assert(Jy901bSample_QualityEvaluate(&sample, &config, 995000U, 0U) == SYSTEM_DEVICE_OK);
    assert(sample.quality_flags == SYSTEM_IMU_QUALITY_TIME_UNCERTAIN);
    puts("JY901B signed clipping/near-range/epoch/range-readback/80B-48B ABI PASS");
    return 0;
}
