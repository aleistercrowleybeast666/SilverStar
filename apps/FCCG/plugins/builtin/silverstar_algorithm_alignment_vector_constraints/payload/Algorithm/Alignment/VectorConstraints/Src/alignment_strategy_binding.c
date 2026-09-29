#include "alignment_strategy_binding.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "attitude_alignment.h"
#include "silverstar_assert.h"
#include "vector_constraints.h"

#define ALIGNMENT_DEGREES_TO_RADIANS 0.01745329251994329577F
#define ALIGNMENT_VECTOR_NORM_MIN 1.0e-6F

static float AlignmentStrategy_Dot(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static uint8_t AlignmentStrategy_Normalize(float vector[3])
{
    float norm = sqrtf(AlignmentStrategy_Dot(vector, vector));
    uint8_t axis;
    if ((!isfinite(norm)) || (norm < ALIGNMENT_VECTOR_NORM_MIN))
    { return 0U; }
    for (axis = 0U; axis < 3U; axis++)
    { vector[axis] /= norm; }
    return 1U;
}

static uint8_t AlignmentStrategy_MagneticConfigured(
    const AlignmentStrategyConfig *config)
{
    uint8_t index;
    SILVERSTAR_ASSERT_OBJECT(config, AlignmentStrategyConfig,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < ALIGNMENT_STRATEGY_MAX_CONSTRAINTS; index++)
    {
        if (index >= config->constraint_count) { break; }
        if (config->constraints[index].kind ==
            ALIGNMENT_CONSTRAINT_MAGNETIC_FIELD)
        { return 1U; }
    }
    return 0U;
}

static void AlignmentStrategy_WindowReset(AlignmentStrategyContext *context)
{
    uint32_t rejects = context->reject_count;
    (void)memset(context, 0, sizeof(*context));
    context->reject_count = rejects;
}

static AlignmentStrategyProcessResult AlignmentStrategy_SampleReject(
    AlignmentStrategyContext *context, AlignmentStrategyOutput *output)
{
    context->reject_count++;
    AlignmentStrategy_WindowReset(context);
    output->reject_count = context->reject_count;
    return ALIGNMENT_STRATEGY_PROCESS_REJECTED;
}

static uint8_t AlignmentStrategy_SampleValid(
    const AlignmentStrategyContext *context,
    const AlignmentStrategyConfig *config,
    const AlignmentStrategySample *sample, uint8_t magnetic_required)
{
    float acceleration_norm;
    float gyro_norm;
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(context, AlignmentStrategyContext,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AlignmentStrategySample,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (axis = 0U; axis < 3U; axis++)
    {
        if ((!isfinite(sample->acceleration_b_mps2[axis])) ||
            (!isfinite(sample->gyro_b_radps[axis])))
        { return 0U; }
        if ((magnetic_required != 0U) &&
            (!isfinite(sample->magnetic_field_b_uT[axis])))
        { return 0U; }
    }
    acceleration_norm = sqrtf(AlignmentStrategy_Dot(
        sample->acceleration_b_mps2, sample->acceleration_b_mps2));
    gyro_norm = sqrtf(AlignmentStrategy_Dot(
        sample->gyro_b_radps, sample->gyro_b_radps));
    if ((sample->timestamp_us == 0ULL) ||
        (fabsf(acceleration_norm - config->gravity_mps2) >
         config->acceleration_tolerance_mps2) ||
        (gyro_norm > config->maximum_gyro_radps))
    { return 0U; }
    if ((context->sample_count != 0U) &&
        ((sample->timestamp_us <= context->last_timestamp_us) ||
         (sample->timestamp_us - context->last_timestamp_us >
          config->maximum_gap_us)))
    { return 0U; }
    if (magnetic_required == 0U) { return 1U; }
    return (uint8_t)((sample->magnetometer_available != 0U) &&
        (sample->magnetometer_calibrated != 0U) &&
        (sample->magnetometer_timestamp_us != 0ULL) &&
        (sample->timestamp_us >= sample->magnetometer_timestamp_us) &&
        (sample->timestamp_us - sample->magnetometer_timestamp_us <=
         config->maximum_gap_us) &&
        ((context->magnetometer_seen == 0U) ||
         (sample->magnetometer_sequence !=
          context->last_magnetometer_sequence)));
}

static void AlignmentStrategy_SampleAccumulate(
    AlignmentStrategyContext *context,
    const AlignmentStrategySample *sample, uint8_t magnetic_required)
{
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(context, AlignmentStrategyContext,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AlignmentStrategySample,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->sample_count == 0U)
    { context->first_timestamp_us = sample->timestamp_us; }
    for (axis = 0U; axis < 3U; axis++)
    {
        context->acceleration_sum_b_mps2[axis] +=
            sample->acceleration_b_mps2[axis];
        context->gyro_sum_b_radps[axis] += sample->gyro_b_radps[axis];
        if (magnetic_required != 0U)
        {
            context->magnetic_sum_b_uT[axis] +=
                sample->magnetic_field_b_uT[axis];
        }
    }
    context->sample_count++;
    context->last_timestamp_us = sample->timestamp_us;
    if (magnetic_required != 0U)
    {
        context->last_magnetometer_sequence =
            sample->magnetometer_sequence;
        context->magnetometer_seen = 1U;
    }
}

static void AlignmentStrategy_ProgressCopy(
    const AlignmentStrategyContext *context, AlignmentStrategyOutput *output)
{
    output->first_timestamp_us = context->first_timestamp_us;
    output->last_timestamp_us = context->last_timestamp_us;
    output->sample_count = context->sample_count;
    output->reject_count = context->reject_count;
}

static uint8_t AlignmentStrategy_HorizontalGet(
    const float vector[3], const float up_b[3], float horizontal[3])
{
    float projection = AlignmentStrategy_Dot(vector, up_b);
    uint8_t axis;
    for (axis = 0U; axis < 3U; axis++)
    { horizontal[axis] = vector[axis] - projection * up_b[axis]; }
    return AlignmentStrategy_Normalize(horizontal);
}

static uint8_t AlignmentStrategy_ConstraintBuild(
    const AlignmentConstraintSpec *spec,
    const float up_b[3], const float magnetic_b[3],
    VectorConstraint *constraint)
{
    float angle_rad;
    int8_t axis;
    SILVERSTAR_ASSERT_OBJECT(spec, AlignmentConstraintSpec,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(constraint, VectorConstraint,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(constraint, 0, sizeof(*constraint));
    constraint->weight = spec->weight;
    if (spec->kind == ALIGNMENT_CONSTRAINT_GRAVITY)
    {
        (void)memcpy(constraint->body, up_b, sizeof(constraint->body));
        constraint->navigation[2] = 1.0F;
        return 1U;
    }
    if (spec->kind == ALIGNMENT_CONSTRAINT_MAGNETIC_FIELD)
    {
        if (AlignmentStrategy_HorizontalGet(magnetic_b, up_b,
            constraint->body) == 0U)
        { return 0U; }
        angle_rad = spec->declination_deg * ALIGNMENT_DEGREES_TO_RADIANS;
    }
    else if (spec->kind == ALIGNMENT_CONSTRAINT_REFERENCE_DIRECTION)
    {
        axis = spec->body_axis;
        if ((axis == 0) || (axis < -3) || (axis > 3))
        { return 0U; }
        constraint->body[(axis < 0) ? -axis - 1 : axis - 1] =
            (axis < 0) ? -1.0F : 1.0F;
        if (AlignmentStrategy_HorizontalGet(constraint->body, up_b,
            constraint->body) == 0U)
        { return 0U; }
        angle_rad = spec->nav_azimuth_deg * ALIGNMENT_DEGREES_TO_RADIANS;
    }
    else { return 0U; }
    constraint->navigation[0] = sinf(angle_rad);
    constraint->navigation[1] = cosf(angle_rad);
    return 1U;
}

static uint8_t AlignmentStrategy_SolutionBuild(
    const AlignmentStrategyConfig *config,
    AlignmentStrategyOutput *output)
{
    VectorConstraint constraints[ALIGNMENT_STRATEGY_MAX_CONSTRAINTS];
    VectorConstraintsSolution solution;
    float up_b[3];
    uint8_t axis;
    uint8_t index;
    SILVERSTAR_ASSERT_OBJECT(config, AlignmentStrategyConfig,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(output, AlignmentStrategyOutput,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (axis = 0U; axis < 3U; axis++)
    {
        up_b[axis] = output->acceleration_mean_b_mps2[axis];
    }
    if (AlignmentStrategy_Normalize(up_b) == 0U) { return 0U; }
    for (index = 0U; index < ALIGNMENT_STRATEGY_MAX_CONSTRAINTS; index++)
    {
        if (index >= config->constraint_count) { break; }
        if (AlignmentStrategy_ConstraintBuild(&config->constraints[index],
            up_b, output->magnetic_field_mean_b_uT,
            &constraints[index]) == 0U)
        { return 0U; }
    }
    if (VectorConstraints_Solve(constraints, config->constraint_count,
        &solution) != VectorConstraintsSolveOk)
    { return 0U; }
    if (AttitudeAlignment_TiltConsistent(solution.q_nb,
        output->acceleration_mean_b_mps2,
        config->maximum_tilt_error_rad) == 0U)
    { return 0U; }
    (void)memcpy(output->q_nb, solution.q_nb, sizeof(output->q_nb));
    output->constraint_count = config->constraint_count;
    output->valid_pair_count = solution.valid_pair_count;
    output->minimum_pair_sine = solution.minimum_pair_sine;
    output->rms_mismatch_rad = solution.rms_mismatch_rad;
    output->max_mismatch_rad = solution.max_mismatch_rad;
    output->magnetic_field_valid =
        AlignmentStrategy_MagneticConfigured(config);
    return 1U;
}

static void AlignmentStrategy_MeansGet(
    const AlignmentStrategyContext *context,
    uint8_t magnetic_required,
    AlignmentStrategyOutput *output)
{
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(context, AlignmentStrategyContext,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(output, AlignmentStrategyOutput,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(context->sample_count != 0U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (axis = 0U; axis < 3U; axis++)
    {
        output->acceleration_mean_b_mps2[axis] =
            context->acceleration_sum_b_mps2[axis] /
            (float)context->sample_count;
        output->gyro_mean_b_radps[axis] =
            context->gyro_sum_b_radps[axis] /
            (float)context->sample_count;
        if (magnetic_required != 0U)
        {
            output->magnetic_field_mean_b_uT[axis] =
                context->magnetic_sum_b_uT[axis] /
                (float)context->sample_count;
        }
    }
}

void AlignmentStrategy_Init(AlignmentStrategyContext *context)
{
    if (context != NULL) { (void)memset(context, 0, sizeof(*context)); }
}

uint8_t AlignmentStrategy_MagnetometerRequired(void)
{
    /* The common interface is queried; the configured constraints decide use. */
    return 1U;
}

uint8_t AlignmentStrategy_HardwareQuaternionRequired(void)
{ return 0U; }

AlignmentStrategyProcessResult AlignmentStrategy_SampleProcess(
    AlignmentStrategyContext *context,
    const AlignmentStrategyConfig *config,
    const AlignmentStrategySample *sample,
    AlignmentStrategyOutput *output)
{
    uint8_t magnetic_required;
    if ((context == NULL) || (config == NULL) || (sample == NULL) ||
        (output == NULL) || (config->constraint_count < 2U) ||
        (config->constraint_count > ALIGNMENT_STRATEGY_MAX_CONSTRAINTS) ||
        (config->minimum_samples == 0U) ||
        (config->maximum_samples < config->minimum_samples))
    { return ALIGNMENT_STRATEGY_PROCESS_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, AlignmentStrategyContext,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(config, AlignmentStrategyConfig,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AlignmentStrategySample,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(output, AlignmentStrategyOutput,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(output, 0, sizeof(*output));
    magnetic_required = AlignmentStrategy_MagneticConfigured(config);
    if ((magnetic_required != 0U) &&
        ((sample->magnetometer_available == 0U) ||
         (sample->magnetometer_calibrated == 0U) ||
         ((context->magnetometer_seen != 0U) &&
          (sample->magnetometer_sequence ==
           context->last_magnetometer_sequence))))
    {
        AlignmentStrategy_ProgressCopy(context, output);
        return ALIGNMENT_STRATEGY_PROCESS_WAITING;
    }
    if (AlignmentStrategy_SampleValid(context, config, sample,
        magnetic_required) == 0U)
    { return AlignmentStrategy_SampleReject(context, output); }
    AlignmentStrategy_SampleAccumulate(context, sample, magnetic_required);
    AlignmentStrategy_ProgressCopy(context, output);
    if ((context->sample_count < config->minimum_samples) ||
        (context->last_timestamp_us - context->first_timestamp_us <
         config->minimum_duration_us))
    {
        if (context->sample_count >= config->maximum_samples)
        { return AlignmentStrategy_SampleReject(context, output); }
        return ALIGNMENT_STRATEGY_PROCESS_ACCEPTED;
    }
    AlignmentStrategy_MeansGet(context, magnetic_required, output);
    if (AlignmentStrategy_SolutionBuild(config, output) != 0U)
    { return ALIGNMENT_STRATEGY_PROCESS_READY; }
    if (context->sample_count >= config->maximum_samples)
    { return AlignmentStrategy_SampleReject(context, output); }
    return ALIGNMENT_STRATEGY_PROCESS_ACCEPTED;
}
