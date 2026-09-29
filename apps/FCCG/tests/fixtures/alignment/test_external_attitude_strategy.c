#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "alignment_strategy_binding.h"
#include "system_hardware_quaternion_if.h"

static AlignmentStrategyConfig Test_ConfigGet(uint8_t authoritative)
{
    AlignmentStrategyConfig config;
    (void)memset(&config, 0, sizeof(config));
    config.minimum_samples = 2U;
    config.maximum_samples = 4U;
    config.minimum_duration_us = 5000U;
    config.maximum_gap_us = 10000U;
    config.gravity_mps2 = 9.78F;
    config.acceleration_tolerance_mps2 = 0.5F;
    config.maximum_gyro_radps = 0.1F;
    config.maximum_quaternion_deviation_rad = 0.1F;
    config.maximum_tilt_error_rad = 0.1F;
    config.known_yaw_body_axis = 1;
    config.external_yaw_authoritative = authoritative;
    return config;
}

static AlignmentStrategySample Test_SampleGet(uint64_t timestamp_us,
    uint32_t sequence, uint8_t mode)
{
    AlignmentStrategySample sample;
    (void)memset(&sample, 0, sizeof(sample));
    sample.timestamp_us = timestamp_us;
    sample.acceleration_b_mps2[2] = 9.78F;
    sample.quaternion_timestamp_us = timestamp_us;
    sample.quaternion_sequence = sequence;
    sample.quaternion_wxyz[0] = 1.0F;
    sample.quaternion_available = 1U;
    sample.quaternion_mode = mode;
    sample.quaternion_mode_verified = 1U;
    return sample;
}

int main(void)
{
    AlignmentStrategyContext context;
    AlignmentStrategyConfig config = Test_ConfigGet(0U);
    AlignmentStrategySample sample = Test_SampleGet(10000ULL, 1U,
        SYSTEM_HW_QUAT_MODE_6AXIS);
    AlignmentStrategyOutput output;
    AlignmentStrategy_Init(&context);
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    sample.timestamp_us = 15000ULL;
    sample.quaternion_timestamp_us = 15000ULL;
    sample.quaternion_sequence = 2U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_READY);
    assert(fabsf(output.q_nb[0] - 1.0F) < 0.001F);

    AlignmentStrategy_Init(&context);
    config.external_yaw_authoritative = 1U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_WAITING);
    sample.quaternion_mode = SYSTEM_HW_QUAT_MODE_9AXIS;
    sample.timestamp_us = 20000ULL;
    sample.quaternion_timestamp_us = 20000ULL;
    sample.quaternion_sequence = 3U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    sample.timestamp_us = 25000ULL;
    sample.quaternion_timestamp_us = 25000ULL;
    sample.quaternion_sequence = 4U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_READY);
    assert(output.hardware_mode == SYSTEM_HW_QUAT_MODE_9AXIS);
    (void)puts("external attitude yaw authority PASS");
    return 0;
}
