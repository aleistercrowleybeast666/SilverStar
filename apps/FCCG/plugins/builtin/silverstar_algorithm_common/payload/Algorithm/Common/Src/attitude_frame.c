#include "attitude_frame.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define ATTITUDE_QUATERNION_NORM_MIN       1.0e-6f
#define ATTITUDE_MATRIX_DIVISOR_MIN        1.0e-6f
#define ATTITUDE_ALIGNMENT_CHECK_TOLERANCE 1.0e-5f
#define ATTITUDE_ROTATION_SMALL_ANGLE_SQ   1.0e-6f
#define ATTITUDE_YAW_HORIZONTAL_NORM_MIN   1.0e-6f

static uint8_t AttitudeFrame_MatrixDivisorValid(float divisor)
{
    return (uint8_t)(isfinite(divisor) &&
                     (divisor >= ATTITUDE_MATRIX_DIVISOR_MIN));
}

static uint8_t AttitudeFrame_QuaternionEquivalent(const float a[4],
                                                  const float b[4])
{
    float absolute_dot;

    if ((a == NULL) || (b == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(a, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    absolute_dot = fabsf(Attitude_QuaternionDot(a, b));
    return (isfinite(absolute_dot) &&
            (fabsf(1.0f - absolute_dot) <=
             ATTITUDE_ALIGNMENT_CHECK_TOLERANCE)) ? 1U : 0U;
}

static uint8_t AttitudeFrame_OutputPublish(AttitudeFrameContext *context,
                                           float q_nb[4])
{
    uint8_t i;

    if ((context == NULL) || (q_nb == NULL) ||
        (Attitude_QuaternionNormalize(q_nb) == 0U))
    {
        if (context != NULL)
        {
            context->output_valid = 0U;
        }
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeFrameContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if ((context->output_valid != 0U) &&
        (Attitude_QuaternionDot(context->q_previous, q_nb) < 0.0f))
    {
        for (i = 0U; i < 4U; i++)
        {
            q_nb[i] = -q_nb[i];
        }
    }

    memcpy(context->q_nb, q_nb, sizeof(context->q_nb));
    memcpy(context->q_previous, q_nb, sizeof(context->q_previous));
    context->output_valid = 1U;
    return 1U;
}

void Attitude_QuaternionMultiply(const float lhs[4],
                                 const float rhs[4],
                                 float out[4])
{
    float result[4];

    if ((lhs == NULL) || (rhs == NULL) || (out == NULL))
    {
        return;
    }

    result[0] = (lhs[0] * rhs[0]) - (lhs[1] * rhs[1]) -
                (lhs[2] * rhs[2]) - (lhs[3] * rhs[3]);
    result[1] = (lhs[0] * rhs[1]) + (lhs[1] * rhs[0]) +
                (lhs[2] * rhs[3]) - (lhs[3] * rhs[2]);
    result[2] = (lhs[0] * rhs[2]) - (lhs[1] * rhs[3]) +
                (lhs[2] * rhs[0]) + (lhs[3] * rhs[1]);
    result[3] = (lhs[0] * rhs[3]) + (lhs[1] * rhs[2]) -
                (lhs[2] * rhs[1]) + (lhs[3] * rhs[0]);
    memcpy(out, result, sizeof(result));
}

uint8_t Attitude_QuaternionNormalize(float q[4])
{
    float norm;
    uint8_t i;

    if (q == NULL)
    {
        return 0U;
    }

    norm = sqrtf((q[0] * q[0]) + (q[1] * q[1]) +
                 (q[2] * q[2]) + (q[3] * q[3]));
    if ((!isfinite(norm)) || (norm < ATTITUDE_QUATERNION_NORM_MIN))
    {
        return 0U;
    }

    for (i = 0U; i < 4U; i++)
    {
        q[i] /= norm;
    }
    return 1U;
}

void Attitude_QuaternionConjugate(const float q[4], float out[4])
{
    float result[4];

    if ((q == NULL) || (out == NULL))
    {
        return;
    }

    result[0] = q[0];
    result[1] = -q[1];
    result[2] = -q[2];
    result[3] = -q[3];
    memcpy(out, result, sizeof(result));
}

float Attitude_QuaternionDot(const float a[4], const float b[4])
{
    if ((a == NULL) || (b == NULL))
    {
        return 0.0f;
    }

    return (a[0] * b[0]) + (a[1] * b[1]) +
           (a[2] * b[2]) + (a[3] * b[3]);
}

uint8_t Attitude_RotationVectorToQuaternion(const float delta_theta[3],
                                            float delta_q[4])
{
    float angle;
    float angle_sq;
    float scale;

    if ((delta_theta == NULL) || (delta_q == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(delta_theta, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(delta_q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    angle_sq = (delta_theta[0] * delta_theta[0]) +
               (delta_theta[1] * delta_theta[1]) +
               (delta_theta[2] * delta_theta[2]);
    if (!isfinite(angle_sq))
    {
        return 0U;
    }

    if (angle_sq <= ATTITUDE_ROTATION_SMALL_ANGLE_SQ)
    {
        delta_q[0] = 1.0f - (angle_sq / 8.0f);
        scale = 0.5f - (angle_sq / 48.0f);
    }
    else
    {
        angle = sqrtf(angle_sq);
        delta_q[0] = cosf(0.5f * angle);
        scale = sinf(0.5f * angle) / angle;
    }

    delta_q[1] = scale * delta_theta[0];
    delta_q[2] = scale * delta_theta[1];
    delta_q[3] = scale * delta_theta[2];
    return Attitude_QuaternionNormalize(delta_q);
}

uint8_t Attitude_PropagateQuaternionBodyIncrement(
    const float q_nb_start[4],
    const float delta_theta_b[3],
    float q_nb_end[4])
{
    float delta_q_body[4];
    float q_start_normalized[4];
    float propagated[4];
    uint8_t i;

    if ((q_nb_start == NULL) || (delta_theta_b == NULL) ||
        (q_nb_end == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb_start, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nb_end, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    memcpy(q_start_normalized, q_nb_start, sizeof(q_start_normalized));
    if ((Attitude_QuaternionNormalize(q_start_normalized) == 0U) ||
        (Attitude_RotationVectorToQuaternion(delta_theta_b,
                                             delta_q_body) == 0U))
    {
        return 0U;
    }

    Attitude_QuaternionMultiply(q_start_normalized,
                                delta_q_body,
                                propagated);
    if (Attitude_QuaternionNormalize(propagated) == 0U)
    {
        return 0U;
    }

    if (Attitude_QuaternionDot(q_start_normalized, propagated) < 0.0f)
    {
        for (i = 0U; i < 4U; i++)
        {
            propagated[i] = -propagated[i];
        }
    }

    memcpy(q_nb_end, propagated, sizeof(propagated));
    return 1U;
}

void Attitude_RotateVector(const float q_nb[4],
                           const float vector_b[3],
                           float vector_n[3])
{
    float vector_quaternion[4];
    float q_conjugate[4];
    float intermediate[4];
    float rotated[4];

    if ((q_nb == NULL) || (vector_b == NULL) || (vector_n == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(vector_n, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    vector_quaternion[0] = 0.0f;
    vector_quaternion[1] = vector_b[0];
    vector_quaternion[2] = vector_b[1];
    vector_quaternion[3] = vector_b[2];
    Attitude_QuaternionConjugate(q_nb, q_conjugate);
    Attitude_QuaternionMultiply(q_nb, vector_quaternion, intermediate);
    Attitude_QuaternionMultiply(intermediate, q_conjugate, rotated);

    vector_n[0] = rotated[1];
    vector_n[1] = rotated[2];
    vector_n[2] = rotated[3];
}

static uint8_t AttitudeFrame_MatrixTraceQuaternionBuild(
    const float matrix[3][3],
    float q[4],
    float trace)
{
    float divisor;

    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    divisor = 2.0f * sqrtf(trace + 1.0f);
    if (AttitudeFrame_MatrixDivisorValid(divisor) == 0U)
    {
        return 0U;
    }
    q[0] = 0.25f * divisor;
    q[1] = (matrix[2][1] - matrix[1][2]) / divisor;
    q[2] = (matrix[0][2] - matrix[2][0]) / divisor;
    q[3] = (matrix[1][0] - matrix[0][1]) / divisor;
    return 1U;
}

static uint8_t AttitudeFrame_MatrixXQuaternionBuild(
    const float matrix[3][3],
    float q[4])
{
    float divisor;

    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    divisor = 2.0f * sqrtf(1.0f + matrix[0][0] -
                           matrix[1][1] - matrix[2][2]);
    if (AttitudeFrame_MatrixDivisorValid(divisor) == 0U)
    {
        return 0U;
    }
    q[0] = (matrix[2][1] - matrix[1][2]) / divisor;
    q[1] = 0.25f * divisor;
    q[2] = (matrix[0][1] + matrix[1][0]) / divisor;
    q[3] = (matrix[0][2] + matrix[2][0]) / divisor;
    return 1U;
}

static uint8_t AttitudeFrame_MatrixYQuaternionBuild(
    const float matrix[3][3],
    float q[4])
{
    float divisor;

    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    divisor = 2.0f * sqrtf(1.0f + matrix[1][1] -
                           matrix[0][0] - matrix[2][2]);
    if (AttitudeFrame_MatrixDivisorValid(divisor) == 0U)
    {
        return 0U;
    }
    q[0] = (matrix[0][2] - matrix[2][0]) / divisor;
    q[1] = (matrix[0][1] + matrix[1][0]) / divisor;
    q[2] = 0.25f * divisor;
    q[3] = (matrix[1][2] + matrix[2][1]) / divisor;
    return 1U;
}

static uint8_t AttitudeFrame_MatrixZQuaternionBuild(
    const float matrix[3][3],
    float q[4])
{
    float divisor;

    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    divisor = 2.0f * sqrtf(1.0f + matrix[2][2] -
                           matrix[0][0] - matrix[1][1]);
    if (AttitudeFrame_MatrixDivisorValid(divisor) == 0U)
    {
        return 0U;
    }
    q[0] = (matrix[1][0] - matrix[0][1]) / divisor;
    q[1] = (matrix[0][2] + matrix[2][0]) / divisor;
    q[2] = (matrix[1][2] + matrix[2][1]) / divisor;
    q[3] = 0.25f * divisor;
    return 1U;
}

uint8_t Attitude_RotationMatrixToQuaternionWxyz(
    const float matrix[3][3],
    float q[4])
{
    float trace;
    uint8_t build_result;
    uint8_t row;
    uint8_t column;

    if ((matrix == NULL) || (q == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    for (row = 0U; row < 3U; row++)
    {
        for (column = 0U; column < 3U; column++)
        {
            if (!isfinite(matrix[row][column]))
            {
                return 0U;
            }
        }
    }

    trace = matrix[0][0] + matrix[1][1] + matrix[2][2];
    if (trace > 0.0f)
    {
        build_result = AttitudeFrame_MatrixTraceQuaternionBuild(
            matrix, q, trace);
    }
    else if ((matrix[0][0] > matrix[1][1]) &&
             (matrix[0][0] > matrix[2][2]))
    {
        build_result = AttitudeFrame_MatrixXQuaternionBuild(matrix, q);
    }
    else if (matrix[1][1] > matrix[2][2])
    {
        build_result = AttitudeFrame_MatrixYQuaternionBuild(matrix, q);
    }
    else
    {
        build_result = AttitudeFrame_MatrixZQuaternionBuild(matrix, q);
    }
    if (build_result == 0U)
    {
        return 0U;
    }
    return Attitude_QuaternionNormalize(q);
}

AttitudeYawResult Attitude_YawEnuFromQuaternion(
    const float q_nb[4],
    float *yaw_rad)
{
    static const float body_x[3] = {1.0f, 0.0f, 0.0f};
    float q_normalized[4];
    float body_x_n[3];
    float horizontal_norm;

    if ((q_nb == NULL) || (yaw_rad == NULL))
    {
        return ATTITUDE_YAW_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(yaw_rad, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(q_normalized, q_nb, sizeof(q_normalized));
    if (Attitude_QuaternionNormalize(q_normalized) == 0U)
    {
        return ATTITUDE_YAW_RESULT_INVALID_QUATERNION;
    }
    Attitude_RotateVector(q_normalized, body_x, body_x_n);
    horizontal_norm = sqrtf((body_x_n[0] * body_x_n[0]) +
                            (body_x_n[1] * body_x_n[1]));
    if ((!isfinite(horizontal_norm)) ||
        (horizontal_norm < ATTITUDE_YAW_HORIZONTAL_NORM_MIN))
    {
        return ATTITUDE_YAW_RESULT_SINGULAR;
    }
    *yaw_rad = atan2f(body_x_n[1], body_x_n[0]);
    return isfinite(*yaw_rad) ? ATTITUDE_YAW_RESULT_OK :
                                ATTITUDE_YAW_RESULT_SINGULAR;
}

uint8_t AttitudeFrame_RawSensorToReference(
    const float q_raw_sr[4],
    float q_rs[4])
{
    float normalized_q_sr[4];

    if ((q_raw_sr == NULL) || (q_rs == NULL))
    {
        return 0U;
    }

    memcpy(normalized_q_sr, q_raw_sr, sizeof(normalized_q_sr));
    if (Attitude_QuaternionNormalize(normalized_q_sr) == 0U)
    {
        return 0U;
    }

    Attitude_QuaternionConjugate(normalized_q_sr, q_rs);
    return Attitude_QuaternionNormalize(q_rs);
}

uint8_t AttitudeFrame_ComputeBodyToReference(
    const float q_raw_sr[4],
    float q_rb[4])
{
    float q_rs[4];

    if ((q_raw_sr == NULL) || (q_rb == NULL) ||
        (AttitudeFrame_RawSensorToReference(q_raw_sr, q_rs) == 0U))
    {
        return 0U;
    }

    memcpy(q_rb, q_rs, sizeof(q_rs));
    return Attitude_QuaternionNormalize(q_rb);
}

uint8_t AttitudeFrame_SixAxisReferenceToNavigationCompute(
    const float q_nb_absolute[4],
    const float q_rb_alignment[4],
    float q_nr[4])
{
    float q_nb_normalized[4];
    float q_rb_normalized[4];
    float q_br_alignment[4];

    if ((q_nb_absolute == NULL) || (q_rb_alignment == NULL) ||
        (q_nr == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb_absolute, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nr, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    memcpy(q_nb_normalized, q_nb_absolute, sizeof(q_nb_normalized));
    memcpy(q_rb_normalized, q_rb_alignment, sizeof(q_rb_normalized));
    if ((Attitude_QuaternionNormalize(q_nb_normalized) == 0U) ||
        (Attitude_QuaternionNormalize(q_rb_normalized) == 0U))
    {
        return 0U;
    }

    Attitude_QuaternionConjugate(q_rb_normalized, q_br_alignment);
    Attitude_QuaternionMultiply(q_nb_normalized, q_br_alignment, q_nr);
    return Attitude_QuaternionNormalize(q_nr);
}

void AttitudeFrame_Init(AttitudeFrameContext *context)
{
    if (context == NULL)
    {
        return;
    }

    memset(context, 0, sizeof(*context));
}

uint8_t AttitudeFrame_SixAxisAlignmentApply(
    AttitudeFrameContext *context,
    const float q_nr[4],
    const float q_rb_alignment[4],
    const float q_nb_absolute[4])
{
    float q_nr_normalized[4];
    float q_rb_normalized[4];
    float q_nb_check[4];

    if ((context == NULL) || (q_nr == NULL) ||
        (q_rb_alignment == NULL) || (q_nb_absolute == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeFrameContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nr, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    memcpy(q_nr_normalized, q_nr, sizeof(q_nr_normalized));
    memcpy(q_rb_normalized, q_rb_alignment, sizeof(q_rb_normalized));
    if ((Attitude_QuaternionNormalize(q_nr_normalized) == 0U) ||
        (Attitude_QuaternionNormalize(q_rb_normalized) == 0U))
    {
        context->alignment_failure_count++;
        context->alignment_valid = 0U;
        context->output_valid = 0U;
        return 0U;
    }

    Attitude_QuaternionMultiply(q_nr_normalized, q_rb_normalized, q_nb_check);
    if ((Attitude_QuaternionNormalize(q_nb_check) == 0U) ||
        (AttitudeFrame_QuaternionEquivalent(q_nb_check, q_nb_absolute) == 0U))
    {
        context->alignment_failure_count++;
        context->alignment_valid = 0U;
        context->output_valid = 0U;
        return 0U;
    }

    memcpy(context->q_nr, q_nr_normalized, sizeof(context->q_nr));
    memcpy(context->q_nb, q_nb_check, sizeof(context->q_nb));
    memcpy(context->q_previous, q_nb_check, sizeof(context->q_previous));
    context->alignment_valid = 1U;
    context->output_valid = 1U;
    return 1U;
}

uint8_t AttitudeFrame_SixAxisTransform(AttitudeFrameContext *context,
                                       const float q_raw_sr[4],
                                       float q_nb[4])
{
    float q_rb[4];

    if ((context == NULL) || (q_raw_sr == NULL) || (q_nb == NULL) ||
        (context->alignment_valid == 0U) ||
        (AttitudeFrame_ComputeBodyToReference(q_raw_sr, q_rb) == 0U))
    {
        if (context != NULL)
        {
            context->output_valid = 0U;
        }
        return 0U;
    }

    Attitude_QuaternionMultiply(context->q_nr, q_rb, q_nb);
    return AttitudeFrame_OutputPublish(context, q_nb);
}

uint8_t AttitudeFrame_NineAxisTransform(AttitudeFrameContext *context,
                                        const float q_raw[4],
                                        float q_nb[4])
{
    if ((context == NULL) || (q_raw == NULL) || (q_nb == NULL))
    {
        if (context != NULL)
        {
            context->alignment_valid = 0U;
            context->output_valid = 0U;
        }
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeFrameContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    /* Device-normalized logical axes are the flight-controller body axes. */
    memcpy(q_nb, q_raw, sizeof(context->q_nb));
    if (Attitude_QuaternionNormalize(q_nb) == 0U)
    {
        context->alignment_valid = 0U;
        context->output_valid = 0U;
        return 0U;
    }

    context->alignment_valid = 1U;
    return AttitudeFrame_OutputPublish(context, q_nb);
}
