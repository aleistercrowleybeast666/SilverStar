#include "alignment_strategy_binding.h"

#include <stddef.h>
#include <string.h>

#include "attitude_alignment.h"
#include "silverstar_assert.h"

static uint8_t AlignmentStrategy_TimestampsClose(
    uint64_t first_us,
    uint64_t second_us,
    uint32_t maximum_gap_us)
{
    uint64_t difference;

    if ((first_us == 0ULL) || (second_us == 0ULL))
    {
        return 0U;
    }
    difference = (first_us >= second_us) ?
        (first_us - second_us) : (second_us - first_us);
    return (uint8_t)(difference <= maximum_gap_us);
}

static void AlignmentStrategy_TriadConfigBuild(
    const AlignmentStrategyConfig *source,
    AttitudeTriadConfig *destination)
{
    SILVERSTAR_ASSERT(source != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(destination != NULL,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    destination->minimum_samples = source->minimum_samples;
    destination->maximum_samples = source->maximum_samples;
    destination->minimum_duration_us = source->minimum_duration_us;
    destination->maximum_gap_us = source->maximum_gap_us;
    destination->gravity_mps2 = source->gravity_mps2;
    destination->acceleration_tolerance_mps2 =
        source->acceleration_tolerance_mps2;
    destination->maximum_gyro_radps = source->maximum_gyro_radps;
    destination->magnetic_magnitude_min_uT =
        source->magnetic_magnitude_min_uT;
    destination->magnetic_magnitude_max_uT =
        source->magnetic_magnitude_max_uT;
    destination->magnetic_magnitude_max_deviation_ratio =
        source->magnetic_magnitude_max_deviation_ratio;
    destination->magnetic_direction_min_dot =
        source->magnetic_direction_min_dot;
    destination->magnetic_horizontal_min_ratio =
        source->magnetic_horizontal_min_ratio;
}

static void AlignmentStrategy_ProgressCopy(
    const AttitudeTriadAccumulator *triad,
    AlignmentStrategyOutput *output)
{
    SILVERSTAR_ASSERT(triad != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(output != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    output->first_timestamp_us = triad->first_timestamp_us;
    output->last_timestamp_us = triad->last_timestamp_us;
    output->sample_count = triad->sample_count;
    output->reject_count = triad->reject_count;
}

void AlignmentStrategy_Init(AlignmentStrategyContext *context)
{
    if (context != NULL)
    {
        (void)memset(context, 0, sizeof(*context));
        AttitudeTriad_Init(&context->triad);
    }
}

uint8_t AlignmentStrategy_MagnetometerRequired(void)
{
    return 1U;
}

uint8_t AlignmentStrategy_HardwareQuaternionRequired(void)
{
    return 0U;
}

AlignmentStrategyProcessResult AlignmentStrategy_SampleProcess(
    AlignmentStrategyContext *context,
    const AlignmentStrategyConfig *config,
    const AlignmentStrategySample *sample,
    AlignmentStrategyOutput *output)
{
    AttitudeTriadConfig triad_config;
    uint8_t accepted;

    if ((context == NULL) || (config == NULL) || (sample == NULL) ||
        (output == NULL))
    {
        return ALIGNMENT_STRATEGY_PROCESS_INVALID;
    }
    SILVERSTAR_ASSERT(config->minimum_samples != 0U,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(config->maximum_samples >= config->minimum_samples,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    (void)memset(output, 0, sizeof(*output));
    if ((sample->magnetometer_available == 0U) ||
        ((context->magnetometer_seen != 0U) &&
         (sample->magnetometer_sequence ==
          context->last_magnetometer_sequence)) ||
        (AlignmentStrategy_TimestampsClose(
            sample->timestamp_us, sample->magnetometer_timestamp_us,
            config->maximum_gap_us) == 0U))
    {
        return ALIGNMENT_STRATEGY_PROCESS_WAITING;
    }
    context->last_magnetometer_sequence = sample->magnetometer_sequence;
    context->magnetometer_seen = 1U;
    AlignmentStrategy_TriadConfigBuild(config, &triad_config);
    accepted = AttitudeTriad_AddStaticSample(
        &context->triad, &triad_config, sample->timestamp_us,
        sample->acceleration_b_mps2, sample->gyro_b_radps,
        sample->magnetic_field_b_uT, sample->magnetometer_calibrated);
    AlignmentStrategy_ProgressCopy(&context->triad, output);
    if (accepted == 0U)
    {
        return ALIGNMENT_STRATEGY_PROCESS_REJECTED;
    }
    if ((context->triad.valid != 0U) &&
        (AttitudeTriad_GetAverage(
            &context->triad, output->acceleration_mean_b_mps2,
            output->gyro_mean_b_radps,
            output->magnetic_field_mean_b_uT) != 0U) &&
        (AttitudeTriad_BuildBodyToEnu(
            &context->triad, config->magnetic_declination_deg,
            output->q_nb) != 0U) &&
        (AttitudeAlignment_TiltConsistent(
            output->q_nb, output->acceleration_mean_b_mps2,
            config->maximum_tilt_error_rad) != 0U))
    {
        output->magnetic_field_valid = 1U;
        return ALIGNMENT_STRATEGY_PROCESS_READY;
    }
    return ALIGNMENT_STRATEGY_PROCESS_ACCEPTED;
}
