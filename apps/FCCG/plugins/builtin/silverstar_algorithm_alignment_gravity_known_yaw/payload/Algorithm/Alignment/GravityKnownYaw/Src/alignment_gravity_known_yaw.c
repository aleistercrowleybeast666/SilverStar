#include "alignment_gravity_known_yaw.h"

#include <math.h>
#include <stddef.h>

#include "attitude_alignment.h"
#include "attitude_frame.h"
#include "silverstar_assert.h"

#define ALIGNMENT_GRAVITY_VECTOR_NORM_MIN 1.0e-6f

static float AlignmentGravity_VectorDot(const float lhs[3],
                                        const float rhs[3])
{
    return (lhs[0] * rhs[0]) + (lhs[1] * rhs[1]) + (lhs[2] * rhs[2]);
}

static float AlignmentGravity_VectorNorm(const float vector[3])
{
    return sqrtf(AlignmentGravity_VectorDot(vector, vector));
}

static uint8_t AlignmentGravity_VectorFinite(const float vector[3])
{
    return (uint8_t)(isfinite(vector[0]) && isfinite(vector[1]) &&
                     isfinite(vector[2]));
}

static void AlignmentGravity_TiltQuaternionBuild(
    const float up_b[3],
    float q_tilt[4])
{
    static const float up_n[3] = {0.0f, 0.0f, 1.0f};
    float dot = AlignmentGravity_VectorDot(up_b, up_n);

    SILVERSTAR_ASSERT(up_b != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(q_tilt != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (dot > -0.999999f)
    {
        q_tilt[0] = 1.0f + dot;
        q_tilt[1] = up_b[1];
        q_tilt[2] = -up_b[0];
        q_tilt[3] = 0.0f;
    }
    else
    {
        q_tilt[0] = 0.0f;
        q_tilt[1] = 1.0f;
        q_tilt[2] = 0.0f;
        q_tilt[3] = 0.0f;
    }
}

uint8_t AttitudeAlignment_GravityKnownYawBuild(
    const float acceleration_mean_b_mps2[3],
    float yaw_deg,
    float output_q_nb[4])
{
    float up_b[3];
    float norm;
    float q_tilt[4];
    uint8_t index;

    if ((acceleration_mean_b_mps2 == NULL) || (output_q_nb == NULL) ||
        (!isfinite(yaw_deg)) ||
        (AlignmentGravity_VectorFinite(acceleration_mean_b_mps2) == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT(acceleration_mean_b_mps2 != NULL,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(output_q_nb != NULL,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    norm = AlignmentGravity_VectorNorm(acceleration_mean_b_mps2);
    if ((!isfinite(norm)) || (norm < ALIGNMENT_GRAVITY_VECTOR_NORM_MIN))
    {
        return 0U;
    }
    for (index = 0U; index < 3U; index++)
    {
        up_b[index] = acceleration_mean_b_mps2[index] / norm;
    }
    AlignmentGravity_TiltQuaternionBuild(up_b, q_tilt);
    if (Attitude_QuaternionNormalize(q_tilt) == 0U)
    {
        return 0U;
    }
    return AttitudeAlignment_ApplyKnownYaw(
        q_tilt, 1, yaw_deg, output_q_nb);
}
