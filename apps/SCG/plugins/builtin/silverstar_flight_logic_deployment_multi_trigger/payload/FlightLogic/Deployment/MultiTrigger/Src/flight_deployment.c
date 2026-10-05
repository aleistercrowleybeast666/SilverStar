#include "flight_deployment.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define FLIGHT_DEPLOYMENT_DEG_TO_RAD 0.01745329251994329577f
#define FLIGHT_DEPLOYMENT_RAD_TO_DEG 57.295779513082320876f
#define FLIGHT_DEPLOYMENT_QUATERNION_NORM_MIN_SQUARED 0.25f

static uint8_t FlightDeployment_VectorIsFinite(const float value[3])
{
    return (uint8_t)((value != NULL) && isfinite(value[0]) &&
                     isfinite(value[1]) && isfinite(value[2]));
}

static float FlightDeployment_VectorDot(const float lhs[3],
                                        const float rhs[3])
{
    return (lhs[0] * rhs[0]) + (lhs[1] * rhs[1]) +
           (lhs[2] * rhs[2]);
}

static uint8_t FlightDeployment_QuaternionNormalize(const float input[4],
                                                    float output[4])
{
    float norm_squared;
    float inverse_norm;
    uint8_t index;

    if ((input == NULL) || (output == NULL) || !isfinite(input[0]) ||
        !isfinite(input[1]) || !isfinite(input[2]) || !isfinite(input[3]))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(input, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(output, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    norm_squared = input[0] * input[0] + input[1] * input[1] +
                   input[2] * input[2] + input[3] * input[3];
    if (!isfinite(norm_squared) ||
        (norm_squared < FLIGHT_DEPLOYMENT_QUATERNION_NORM_MIN_SQUARED))
    {
        return 0U;
    }
    inverse_norm = 1.0f / sqrtf(norm_squared);
    for (index = 0U; index < 4U; index++)
    {
        output[index] = input[index] * inverse_norm;
    }
    return 1U;
}

static void FlightDeployment_BodyAxisVectorGet(SystemBodyAxis axis,
                                               float vector[3])
{
    (void)memset(vector, 0, sizeof(float) * 3U);
    switch (axis)
    {
        case SYSTEM_BODY_AXIS_X_POSITIVE: vector[0] = 1.0f; break;
        case SYSTEM_BODY_AXIS_X_NEGATIVE: vector[0] = -1.0f; break;
        case SYSTEM_BODY_AXIS_Y_POSITIVE: vector[1] = 1.0f; break;
        case SYSTEM_BODY_AXIS_Y_NEGATIVE: vector[1] = -1.0f; break;
        case SYSTEM_BODY_AXIS_Z_POSITIVE: vector[2] = 1.0f; break;
        case SYSTEM_BODY_AXIS_Z_NEGATIVE: vector[2] = -1.0f; break;
        default: break;
    }
}

static FlightDeploymentConditionResult FlightDeployment_TiltEvaluate(
    const FlightDeploymentContext *context,
    const FlightDeploymentInput *input,
    float *reference_dot)
{
    float current_axis_n[3];

    if ((context == NULL) || (input == NULL) || (reference_dot == NULL) ||
        (input->attitude_valid == 0U) ||
        (FlightDeployment_RocketAxisGet(context, input->q_nb,
                                        current_axis_n) !=
         FLIGHT_DEPLOYMENT_AXIS_OK))
    {
        return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightDeploymentContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, FlightDeploymentInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (context->config.tilt_reference ==
        SYSTEM_TILT_REFERENCE_INITIAL_AXIS)
    {
        if (input->initial_rocket_axis_valid == 0U)
        {
            return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
        }
        *reference_dot = FlightDeployment_VectorDot(
            input->initial_rocket_axis_n, current_axis_n);
    }
    else
    {
        *reference_dot = current_axis_n[2];
    }
    if (*reference_dot > 1.0f) { *reference_dot = 1.0f; }
    if (*reference_dot < -1.0f) { *reference_dot = -1.0f; }
    return (*reference_dot < context->tilt_cos_threshold) ?
        FLIGHT_DEPLOYMENT_CONDITION_MET :
        FLIGHT_DEPLOYMENT_CONDITION_NOT_MET;
}

static FlightDeploymentConditionResult FlightDeployment_ApogeeEvaluate(
    const FlightDeploymentContext *context,
    const FlightDeploymentInput *input,
    float *vertical_velocity_mps)
{
    if ((context == NULL) || (input == NULL) ||
        (vertical_velocity_mps == NULL) || (input->velocity_valid == 0U) ||
        (FlightDeployment_VectorIsFinite(input->velocity_enu_mps) == 0U))
    {
        return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    }
    *vertical_velocity_mps = input->velocity_enu_mps[2];
    return (*vertical_velocity_mps <
            context->config.apogee_vertical_velocity_threshold_mps) ?
        FLIGHT_DEPLOYMENT_CONDITION_MET :
        FLIGHT_DEPLOYMENT_CONDITION_NOT_MET;
}

FlightDeploymentInitResult FlightDeployment_ContextInit(
    FlightDeploymentContext *context,
    const FlightDeploymentConfig *config)
{
    if ((context == NULL) || (config == NULL))
    {
        return FLIGHT_DEPLOYMENT_INIT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightDeploymentContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(config, FlightDeploymentConfig,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)memset(context, 0, sizeof(*context));
    if (((config->trigger_mask & ~SYSTEM_DEPLOY_TRIGGER_MASK_ALL) != 0U) ||
        (config->rocket_longitudinal_axis > SYSTEM_BODY_AXIS_Z_NEGATIVE) ||
        ((config->tilt_reference != SYSTEM_TILT_REFERENCE_INITIAL_AXIS) &&
         (config->tilt_reference != SYSTEM_TILT_REFERENCE_NAV_UP)) ||
        !isfinite(config->tilt_threshold_deg) ||
        !isfinite(config->apogee_vertical_velocity_threshold_mps) ||
        (config->tilt_threshold_deg <= 0.0f) ||
        (config->tilt_threshold_deg > 180.0f) ||
        (config->apogee_vertical_velocity_threshold_mps >= 0.0f))
    {
        return FLIGHT_DEPLOYMENT_INIT_INVALID_CONFIG;
    }
    context->config = *config;
    context->tilt_cos_threshold = cosf(config->tilt_threshold_deg *
                                       FLIGHT_DEPLOYMENT_DEG_TO_RAD);
    context->initialized = 1U;
    return FLIGHT_DEPLOYMENT_INIT_OK;
}

FlightDeploymentAxisResult FlightDeployment_RocketAxisGet(
    const FlightDeploymentContext *context,
    const float q_nb_input[4],
    float axis_n[3])
{
    float axis_b[3];
    float q_nb[4];
    float w;
    float x;
    float y;
    float z;

    if ((context == NULL) || (axis_n == NULL) ||
        (context->initialized == 0U))
    {
        return FLIGHT_DEPLOYMENT_AXIS_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightDeploymentContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(axis_n, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (FlightDeployment_QuaternionNormalize(q_nb_input, q_nb) == 0U)
    {
        return FLIGHT_DEPLOYMENT_AXIS_INVALID_QUATERNION;
    }
    FlightDeployment_BodyAxisVectorGet(
        context->config.rocket_longitudinal_axis, axis_b);
    w = q_nb[0];
    x = q_nb[1];
    y = q_nb[2];
    z = q_nb[3];
    axis_n[0] = ((1.0f - 2.0f * (y * y + z * z)) * axis_b[0]) +
                (2.0f * (x * y - w * z) * axis_b[1]) +
                (2.0f * (x * z + w * y) * axis_b[2]);
    axis_n[1] = (2.0f * (x * y + w * z) * axis_b[0]) +
                ((1.0f - 2.0f * (x * x + z * z)) * axis_b[1]) +
                (2.0f * (y * z - w * x) * axis_b[2]);
    axis_n[2] = (2.0f * (x * z - w * y) * axis_b[0]) +
                (2.0f * (y * z + w * x) * axis_b[1]) +
                ((1.0f - 2.0f * (x * x + y * y)) * axis_b[2]);
    return (FlightDeployment_VectorIsFinite(axis_n) != 0U) ?
        FLIGHT_DEPLOYMENT_AXIS_OK :
        FLIGHT_DEPLOYMENT_AXIS_INVALID_QUATERNION;
}

static void FlightDeployment_EvaluationMatchesApply(
    FlightDeploymentConditionResult apogee_result,
    FlightDeploymentConditionResult tilt_result,
    float apogee_value,
    float tilt_value,
    FlightDeploymentEvaluation *evaluation)
{
    SILVERSTAR_ASSERT_OBJECT(evaluation, FlightDeploymentEvaluation,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT((apogee_result <= FLIGHT_DEPLOYMENT_CONDITION_MET),
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((tilt_result <= FLIGHT_DEPLOYMENT_CONDITION_MET),
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (apogee_result == FLIGHT_DEPLOYMENT_CONDITION_MET)
    {
        evaluation->matched_mask |= SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ;
        evaluation->vertical_velocity_mps = apogee_value;
    }
    if (tilt_result == FLIGHT_DEPLOYMENT_CONDITION_MET)
    {
        evaluation->matched_mask |= SYSTEM_DEPLOY_TRIGGER_TILT;
        evaluation->tilt_angle_deg = acosf(tilt_value) *
                                     FLIGHT_DEPLOYMENT_RAD_TO_DEG;
    }
}

FlightDeploymentConditionResult FlightDeployment_ConditionEvaluate(
    const FlightDeploymentContext *context,
    const FlightDeploymentInput *input,
    FlightDeploymentEvaluation *evaluation)
{
    FlightDeploymentConditionResult apogee_result =
        FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    FlightDeploymentConditionResult tilt_result =
        FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    float apogee_value = 0.0f;
    float tilt_value = 0.0f;
    uint8_t valid_mode = 0U;

    if ((context == NULL) || (input == NULL) || (evaluation == NULL) ||
        (context->initialized == 0U))
    {
        return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, FlightDeploymentContext,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(evaluation, FlightDeploymentEvaluation,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)memset(evaluation, 0, sizeof(*evaluation));
    if ((context->config.trigger_mask &
         SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ) != 0U)
    {
        apogee_result = FlightDeployment_ApogeeEvaluate(
            context, input, &apogee_value);
        valid_mode = (uint8_t)(apogee_result !=
                               FLIGHT_DEPLOYMENT_CONDITION_INVALID);
    }
    if ((context->config.trigger_mask & SYSTEM_DEPLOY_TRIGGER_TILT) != 0U)
    {
        tilt_result = FlightDeployment_TiltEvaluate(
            context, input, &tilt_value);
        valid_mode |= (uint8_t)(tilt_result !=
                                FLIGHT_DEPLOYMENT_CONDITION_INVALID);
    }
    FlightDeployment_EvaluationMatchesApply(
        apogee_result, tilt_result, apogee_value, tilt_value, evaluation);
    if (((context->config.trigger_mask & SYSTEM_DEPLOY_TRIGGER_DELAY) != 0U) &&
        (input->mission_time_ms >= context->config.delay_ms))
    {
        evaluation->matched_mask |= SYSTEM_DEPLOY_TRIGGER_DELAY;
    }
    valid_mode |= (uint8_t)((context->config.trigger_mask &
                             SYSTEM_DEPLOY_TRIGGER_DELAY) != 0U);
    if (evaluation->matched_mask != SYSTEM_DEPLOY_TRIGGER_NONE)
    {
        return FLIGHT_DEPLOYMENT_CONDITION_MET;
    }
    if ((valid_mode == 0U) &&
        (context->config.trigger_mask != SYSTEM_DEPLOY_TRIGGER_NONE))
    {
        return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    }
    return FLIGHT_DEPLOYMENT_CONDITION_NOT_MET;
}
