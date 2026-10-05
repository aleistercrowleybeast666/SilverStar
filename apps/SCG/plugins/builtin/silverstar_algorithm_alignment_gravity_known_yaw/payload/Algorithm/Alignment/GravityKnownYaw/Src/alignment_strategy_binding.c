#include "alignment_strategy_binding.h"

#include <stddef.h>
#include <string.h>

#include "alignment_gravity_known_yaw.h"
#include "silverstar_assert.h"

static void AlignmentStrategy_WindowConfigBuild(
    const AlignmentStrategyConfig *source,
    AttitudeAlignmentWindowConfig *destination)
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
    destination->maximum_quaternion_deviation_rad =
        source->maximum_quaternion_deviation_rad;
}

static void AlignmentStrategy_ProgressCopy(
    const AttitudeAlignmentWindow *window,
    AlignmentStrategyOutput *output)
{
    SILVERSTAR_ASSERT(window != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(output != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    output->first_timestamp_us = window->first_timestamp_us;
    output->last_timestamp_us = window->last_timestamp_us;
    output->sample_count = window->sample_count;
    output->reject_count = window->reject_count;
}

void AlignmentStrategy_Init(AlignmentStrategyContext *context)
{
    AttitudeAlignmentWindow_Init(&context->window);
}

uint8_t AlignmentStrategy_MagnetometerRequired(void)
{
    return 0U;
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
    AttitudeAlignmentWindowConfig window_config;
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
    AlignmentStrategy_WindowConfigBuild(config, &window_config);
    accepted = AttitudeAlignmentWindow_AddInertial(
        &context->window, &window_config, sample->timestamp_us,
        sample->acceleration_b_mps2, sample->gyro_b_radps);
    AlignmentStrategy_ProgressCopy(&context->window, output);
    if (accepted == 0U)
    {
        return ALIGNMENT_STRATEGY_PROCESS_REJECTED;
    }
    if ((context->window.valid != 0U) &&
        (AttitudeAlignmentWindow_GetInertialAverage(
            &context->window, output->acceleration_mean_b_mps2,
            output->gyro_mean_b_radps) != 0U) &&
        (AttitudeAlignment_GravityKnownYawBuild(
            output->acceleration_mean_b_mps2, config->known_yaw_deg,
            output->q_nb) != 0U) &&
        (AttitudeAlignment_TiltConsistent(
            output->q_nb, output->acceleration_mean_b_mps2,
            config->maximum_tilt_error_rad) != 0U))
    {
        return ALIGNMENT_STRATEGY_PROCESS_READY;
    }
    return ALIGNMENT_STRATEGY_PROCESS_ACCEPTED;
}
