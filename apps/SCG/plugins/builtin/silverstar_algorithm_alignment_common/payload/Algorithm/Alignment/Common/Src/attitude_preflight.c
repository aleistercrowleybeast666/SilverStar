#include "attitude_preflight.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define ATTITUDE_PREFLIGHT_QUATERNION_NORM_MIN 0.5f
#define ATTITUDE_PREFLIGHT_QUATERNION_NORM_MAX 1.5f

static uint8_t AttitudePreflight_QuaternionValid(const float q_nb[4])
{
    float norm_squared = 0.0f;
    uint8_t index;

    if (q_nb == NULL)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 4U; index++)
    {
        if (!isfinite(q_nb[index]))
        {
            return 0U;
        }
        norm_squared += q_nb[index] * q_nb[index];
    }
    return (uint8_t)((norm_squared >=
        (ATTITUDE_PREFLIGHT_QUATERNION_NORM_MIN *
         ATTITUDE_PREFLIGHT_QUATERNION_NORM_MIN)) &&
        (norm_squared <=
        (ATTITUDE_PREFLIGHT_QUATERNION_NORM_MAX *
         ATTITUDE_PREFLIGHT_QUATERNION_NORM_MAX)));
}

void AttitudePreflight_Init(AttitudePreflightContext *context)
{
    if (context == NULL)
    {
        return;
    }
    (void)memset(context, 0, sizeof(*context));
    context->latest.quaternion_wxyz[0] = 1.0f;
    context->mission.quaternion_wxyz[0] = 1.0f;
}

AttitudePreflightResult AttitudePreflight_LatestUpdate(
    AttitudePreflightContext *context,
    const AttitudePreflightSample *sample)
{
    AttitudePreflightSample normalized;
    float inverse_norm;
    float norm_squared = 0.0f;
    uint8_t index;

    if ((context == NULL) || (sample == NULL))
    {
        return ATTITUDE_PREFLIGHT_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudePreflightContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudePreflightSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->mission_frozen != 0U)
    {
        return ATTITUDE_PREFLIGHT_RESULT_FROZEN;
    }
    if ((sample->valid == 0U) ||
        (sample->sample_timestamp_us == 0U) ||
        (sample->receive_timestamp_us == 0U) ||
        (AttitudePreflight_QuaternionValid(sample->quaternion_wxyz) == 0U))
    {
        return ATTITUDE_PREFLIGHT_RESULT_INVALID;
    }
    for (index = 0U; index < 4U; index++)
    {
        norm_squared += sample->quaternion_wxyz[index] *
                        sample->quaternion_wxyz[index];
    }
    normalized = *sample;
    inverse_norm = 1.0f / sqrtf(norm_squared);
    for (index = 0U; index < 4U; index++)
    {
        normalized.quaternion_wxyz[index] =
            sample->quaternion_wxyz[index] * inverse_norm;
    }
    normalized.valid = 1U;
    context->latest = normalized;
    return ATTITUDE_PREFLIGHT_RESULT_OK;
}

AttitudePreflightResult AttitudePreflight_LatestCheck(
    const AttitudePreflightContext *context,
    uint64_t now_us,
    uint64_t maximum_age_us)
{
    if (context == NULL)
    {
        return ATTITUDE_PREFLIGHT_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudePreflightContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((context->latest.valid == 0U) ||
        (context->latest.sample_timestamp_us == 0U) ||
        (context->latest.receive_timestamp_us == 0U) ||
        (AttitudePreflight_QuaternionValid(
             context->latest.quaternion_wxyz) == 0U))
    {
        return ATTITUDE_PREFLIGHT_RESULT_INVALID;
    }
    if ((context->latest.sample_timestamp_us > now_us) ||
        ((now_us - context->latest.sample_timestamp_us) > maximum_age_us))
    {
        return ATTITUDE_PREFLIGHT_RESULT_STALE;
    }
    return ATTITUDE_PREFLIGHT_RESULT_OK;
}

AttitudePreflightResult AttitudePreflight_MissionFreeze(
    AttitudePreflightContext *context,
    uint64_t now_us,
    uint64_t maximum_age_us)
{
    AttitudePreflightResult result;

    if (context == NULL)
    {
        return ATTITUDE_PREFLIGHT_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudePreflightContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->mission_frozen != 0U)
    {
        return ATTITUDE_PREFLIGHT_RESULT_OK;
    }
    result = AttitudePreflight_LatestCheck(context, now_us,
                                            maximum_age_us);
    if (result != ATTITUDE_PREFLIGHT_RESULT_OK)
    {
        return result;
    }
    context->mission = context->latest;
    context->mission_frozen = 1U;
    return ATTITUDE_PREFLIGHT_RESULT_OK;
}

void AttitudePreflight_MissionUnfreeze(AttitudePreflightContext *context)
{
    if (context != NULL)
    {
        context->mission_frozen = 0U;
    }
}

uint8_t AttitudePreflight_LatestGet(
    const AttitudePreflightContext *context,
    AttitudePreflightSample *sample)
{
    if ((context == NULL) || (sample == NULL) ||
        (context->latest.valid == 0U))
    {
        return 0U;
    }
    *sample = context->latest;
    return 1U;
}

uint8_t AttitudePreflight_MissionGet(
    const AttitudePreflightContext *context,
    AttitudePreflightSample *sample)
{
    if ((context == NULL) || (sample == NULL) ||
        (context->mission_frozen == 0U))
    {
        return 0U;
    }
    *sample = context->mission;
    return 1U;
}
