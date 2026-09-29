#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "alignment_strategy_binding.h"

static AlignmentStrategyConfig Test_ConfigGet(uint8_t magnetic)
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
    config.maximum_tilt_error_rad = 0.1F;
    config.constraint_count = magnetic != 0U ? 3U : 2U;
    config.constraints[0].kind = ALIGNMENT_CONSTRAINT_GRAVITY;
    config.constraints[0].weight = 1.0F;
    config.constraints[1].kind = ALIGNMENT_CONSTRAINT_REFERENCE_DIRECTION;
    config.constraints[1].weight = 1.0F;
    config.constraints[1].body_axis = 1;
    config.constraints[1].nav_azimuth_deg = 90.0F;
    if (magnetic != 0U)
    {
        config.constraints[2].kind = ALIGNMENT_CONSTRAINT_MAGNETIC_FIELD;
        config.constraints[2].weight = 1.0F;
    }
    return config;
}

static AlignmentStrategySample Test_SampleGet(uint64_t timestamp_us,
    uint32_t magnetometer_sequence)
{
    AlignmentStrategySample sample;
    (void)memset(&sample, 0, sizeof(sample));
    sample.timestamp_us = timestamp_us;
    sample.acceleration_b_mps2[2] = 9.78F;
    sample.magnetometer_timestamp_us = timestamp_us;
    sample.magnetometer_sequence = magnetometer_sequence;
    sample.magnetic_field_b_uT[1] = 30.0F;
    sample.magnetometer_available = 1U;
    sample.magnetometer_calibrated = 1U;
    return sample;
}

static void Test_ReferenceOnly(void)
{
    AlignmentStrategyContext context;
    AlignmentStrategyConfig config = Test_ConfigGet(0U);
    AlignmentStrategySample sample = Test_SampleGet(10000ULL, 0U);
    AlignmentStrategyOutput output;
    AlignmentStrategy_Init(&context);
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    sample.timestamp_us = 15000ULL;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_READY);
    assert(output.constraint_count == 2U);
    assert(output.valid_pair_count == 1U);
    assert(fabsf(output.q_nb[0] - 1.0F) < 0.001F);
    assert(output.rms_mismatch_rad < 0.001F);
}

static void Test_MagneticRequiresFreshCalibration(void)
{
    AlignmentStrategyContext context;
    AlignmentStrategyConfig config = Test_ConfigGet(1U);
    AlignmentStrategySample sample = Test_SampleGet(10000ULL, 1U);
    AlignmentStrategyOutput output;
    AlignmentStrategy_Init(&context);
    sample.magnetometer_calibrated = 0U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_WAITING);
    sample.magnetometer_calibrated = 1U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    sample.timestamp_us = 15000ULL;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_WAITING);
    assert(output.sample_count == 1U);
    sample.magnetometer_timestamp_us = 15000ULL;
    sample.magnetometer_sequence = 2U;
    assert(AlignmentStrategy_SampleProcess(&context, &config, &sample,
        &output) == ALIGNMENT_STRATEGY_PROCESS_READY);
    assert(output.constraint_count == 3U);
    assert(output.valid_pair_count == 3U);
    assert(output.magnetic_field_valid != 0U);
    assert(output.rms_mismatch_rad < 0.001F);
}

int main(void)
{
    Test_ReferenceOnly();
    Test_MagneticRequiresFreshCalibration();
    (void)puts("vector strategy fresh magnetic and bounded pairs PASS");
    return 0;
}
