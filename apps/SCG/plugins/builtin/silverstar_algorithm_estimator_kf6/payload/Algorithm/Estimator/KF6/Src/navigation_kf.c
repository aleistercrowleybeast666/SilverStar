#include "navigation_kf.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"
#include "system_user_config.h"

#define NAV_KF_STATE_DIMENSION 6U
#define NAV_KF_VECTOR_DIMENSION 3U
#define NAV_KF_P_DIAGONAL_MIN SYSTEM_ESTIMATOR_P_DIAGONAL_MIN
#define NAV_KF_MATRIX_EPSILON SYSTEM_ESTIMATOR_MATRIX_EPSILON
#define NAV_KF_DT_MAX_S SYSTEM_KF_PREDICTION_DT_MAX_S

#define NAV_KF_DEFAULT_PROCESS_E_STD_MPS2 SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_VALUE
#define NAV_KF_DEFAULT_PROCESS_N_STD_MPS2 SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_VALUE
#define NAV_KF_DEFAULT_PROCESS_U_STD_MPS2 SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_VALUE
#define NAV_KF_DEFAULT_BARO_STD_M SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_VALUE
#define NAV_KF_DEFAULT_NIS_1D_SOFT SYSTEM_ESTIMATOR_NIS_1D_SOFT_THRESHOLD
#define NAV_KF_DEFAULT_NIS_1D_HARD SYSTEM_ESTIMATOR_NIS_1D_HARD_THRESHOLD
#define NAV_KF_DEFAULT_NIS_2D_SOFT SYSTEM_ESTIMATOR_NIS_2D_SOFT_THRESHOLD
#define NAV_KF_DEFAULT_NIS_2D_HARD SYSTEM_ESTIMATOR_NIS_2D_HARD_THRESHOLD
#define NAV_KF_DEFAULT_NIS_3D_SOFT SYSTEM_ESTIMATOR_NIS_3D_SOFT_THRESHOLD
#define NAV_KF_DEFAULT_NIS_3D_HARD SYSTEM_ESTIMATOR_NIS_3D_HARD_THRESHOLD
#define NAV_KF_DEFAULT_NIS_MAX_R_SCALE SYSTEM_ESTIMATOR_NIS_MAX_R_SCALE
#define NAV_KF_GNSS_GROUP_INVALID 0xFFU

typedef enum
{
    NAV_KF_MEASUREMENT_POSITION = 0U,
    NAV_KF_MEASUREMENT_VELOCITY,
    NAV_KF_MEASUREMENT_BARO
} NavigationKfMeasurementType;

typedef struct
{
    float state_backup[6];
    float covariance_backup[6][6];
    float innovation[3];
    float innovation_covariance[3][3];
    float innovation_inverse[3][3];
    float gain[6][3];
    float identity_minus_kh[6][6];
    float temporary[6][6];
    float covariance_new[6][6];
    float effective_variance[3];
    float nis;
    NavigationKfUpdateResult result;
} NavigationKfVectorWork;

typedef struct
{
    float process_accel_std[3];
    float baro_std;
    float nis_soft_threshold[3];
    float nis_hard_threshold[3];
    float nis_max_r_scale;
} NavigationKfConfigSnapshot;

static uint8_t NavigationKf_IsFiniteVector(const float *values, uint8_t count)
{
    uint8_t index;

    if (values == NULL)
    {
        return 0U;
    }

    for (index = 0U; index < count; index++)
    {
        if (!isfinite(values[index]))
        {
            return 0U;
        }
    }

    return 1U;
}

static void NavigationKf_CovarianceInitialSet(NavigationKfContext *context)
{
    static const float initial_variance[NAV_KF_STATE_DIMENSION] =
    {
        SYSTEM_ESTIMATOR_P0_POSITION_E_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_POSITION_N_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_POSITION_U_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_E_VARIANCE_M2PS2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_N_VARIANCE_M2PS2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_U_VARIANCE_M2PS2
    };
    uint8_t row;

    memset(context->covariance, 0, sizeof(context->covariance));
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        context->covariance[row][row] = initial_variance[row];
    }
}

static uint8_t NavigationKf_StateAndCovarianceValid(
    const NavigationKfContext *context)
{
    uint8_t row;
    uint8_t column;

    if ((context == NULL) ||
        (NavigationKf_IsFiniteVector(context->state, NAV_KF_STATE_DIMENSION) == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            if (!isfinite(context->covariance[row][column]))
            {
                return 0U;
            }
        }

        if (context->covariance[row][row] < 0.0f)
        {
            return 0U;
        }
    }

    return 1U;
}

static void NavigationKf_CovarianceSymmetrizeAndClamp(
    NavigationKfContext *context)
{
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = (uint8_t)(row + 1U);
             column < NAV_KF_STATE_DIMENSION;
             column++)
        {
            float symmetric_value = 0.5f *
                (context->covariance[row][column] +
                 context->covariance[column][row]);
            context->covariance[row][column] = symmetric_value;
            context->covariance[column][row] = symmetric_value;
        }

        if (context->covariance[row][row] < NAV_KF_P_DIAGONAL_MIN)
        {
            context->covariance[row][row] = NAV_KF_P_DIAGONAL_MIN;
        }
    }
}

static void NavigationKf_NumericRecovery(NavigationKfContext *context,
                                         const float state_backup[6],
                                         uint32_t extra_health_flags)
{
    if (context == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if (NavigationKf_IsFiniteVector(context->state, NAV_KF_STATE_DIMENSION) == 0U)
    {
        if (NavigationKf_IsFiniteVector(state_backup, NAV_KF_STATE_DIMENSION) != 0U)
        {
            memcpy(context->state, state_backup, sizeof(context->state));
        }
        else
        {
            memset(context->state, 0, sizeof(context->state));
        }
    }

    NavigationKf_CovarianceInitialSet(context);
    context->numeric_error_count++;
    context->health_flags |= NAV_KF_HEALTH_NUMERIC_ERROR |
                             NAV_KF_HEALTH_COVARIANCE_RECOVERED |
                             extra_health_flags;
}

static uint8_t NavigationKf_CholeskyDecompose(
    float matrix[3][3],
    float lower[3][3],
    uint8_t dimension)
{
    uint8_t row;
    uint8_t column;
    uint8_t inner;

    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(lower, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < dimension; row++)
    {
        for (column = 0U; column <= row; column++)
        {
            float value = matrix[row][column];

            for (inner = 0U; inner < column; inner++)
            {
                value -= lower[row][inner] * lower[column][inner];
            }

            if (row == column)
            {
                if ((!isfinite(value)) || (value <= NAV_KF_MATRIX_EPSILON))
                {
                    return 0U;
                }
                lower[row][column] = sqrtf(value);
            }
            else
            {
                if (lower[column][column] <= NAV_KF_MATRIX_EPSILON)
                {
                    return 0U;
                }
                lower[row][column] = value / lower[column][column];
            }
        }
    }
    return 1U;
}

static void NavigationKf_CholeskyColumnSolve(
    float lower[3][3],
    float inverse[3][3],
    uint8_t dimension,
    uint8_t column)
{
    float forward[3] = {0.0f};
    float solution[3] = {0.0f};
    uint8_t row;
    uint8_t inner;

    SILVERSTAR_ASSERT_OBJECT(lower, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(inverse, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < dimension; row++)
    {
        float value = (row == column) ? 1.0f : 0.0f;
        for (inner = 0U; inner < row; inner++)
        {
            value -= lower[row][inner] * forward[inner];
        }
        forward[row] = value / lower[row][row];
    }
    for (row = dimension; row > 0U; row--)
    {
        uint8_t solve_row = (uint8_t)(row - 1U);
        float value = forward[solve_row];
        for (inner = (uint8_t)(solve_row + 1U); inner < dimension; inner++)
        {
            value -= lower[inner][solve_row] * solution[inner];
        }
        solution[solve_row] = value / lower[solve_row][solve_row];
    }
    for (row = 0U; row < dimension; row++)
    {
        inverse[row][column] = solution[row];
    }
}

static uint8_t NavigationKf_CholeskyInverse(float matrix[3][3],
                                             float inverse[3][3],
                                             uint8_t dimension)
{
    float lower[3][3] = {{0.0f}};
    uint8_t column;

    if ((dimension == 0U) || (dimension > NAV_KF_VECTOR_DIMENSION))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(matrix, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(inverse, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(inverse, 0, sizeof(float) * 9U);
    if (NavigationKf_CholeskyDecompose(matrix, lower, dimension) == 0U)
    {
        return 0U;
    }
    for (column = 0U; column < dimension; column++)
    {
        NavigationKf_CholeskyColumnSolve(lower, inverse, dimension, column);
    }
    return 1U;
}

static void NavigationKf_UpdateCounters(NavigationKfContext *context,
                                        NavigationKfMeasurementType type,
                                        NavigationKfUpdateResult result)
{
    uint32_t *accept_count;
    uint32_t *soft_count;
    uint32_t *reject_count;

    if (context == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if (type == NAV_KF_MEASUREMENT_POSITION)
    {
        accept_count = &context->position_accept_count;
        soft_count = &context->position_soft_count;
        reject_count = &context->position_reject_count;
    }
    else if (type == NAV_KF_MEASUREMENT_VELOCITY)
    {
        accept_count = &context->velocity_accept_count;
        soft_count = &context->velocity_soft_count;
        reject_count = &context->velocity_reject_count;
    }
    else
    {
        accept_count = &context->baro_accept_count;
        soft_count = &context->baro_soft_count;
        reject_count = &context->baro_reject_count;
    }

    if (result == NAV_KF_UPDATE_ACCEPTED)
    {
        (*accept_count)++;
    }
    else if (result == NAV_KF_UPDATE_SOFT_WEIGHTED)
    {
        (*soft_count)++;
    }
    else
    {
        (*reject_count)++;
    }
}

static uint8_t NavigationKf_UpdateResultFused(
    NavigationKfUpdateResult result)
{
    return (uint8_t)((result == NAV_KF_UPDATE_ACCEPTED) ||
                     (result == NAV_KF_UPDATE_SOFT_WEIGHTED));
}

static void NavigationKf_GnssGroupCountersUpdate(
    NavigationKfContext *context,
    NavigationKfGnssGroup group,
    NavigationKfUpdateResult result)
{
    if ((context == NULL) || (group >= NAV_KF_GNSS_GROUP_COUNT))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (result == NAV_KF_UPDATE_ACCEPTED)
    {
        context->gnss_group_accept_count[group]++;
    }
    else if (result == NAV_KF_UPDATE_SOFT_WEIGHTED)
    {
        context->gnss_group_soft_count[group]++;
    }
    else
    {
        context->gnss_group_reject_count[group]++;
    }
}

static NavigationKfUpdateResult NavigationKf_SeparatedResultAggregate(
    const NavigationKfGnssSeparatedUpdateResult *result)
{
    NavigationKfUpdateResult attempted_result[2];
    uint8_t attempted_count = 0U;
    uint8_t index;
    uint8_t soft_seen = 0U;
    uint8_t nis_reject_seen = 0U;
    uint8_t invalid_seen = 0U;

    if (result == NULL)
    {
        return NAV_KF_UPDATE_REJECTED_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(result, NavigationKfGnssSeparatedUpdateResult,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (result->horizontal_attempted != 0U)
    {
        attempted_result[attempted_count++] = result->horizontal_result;
    }
    if (result->vertical_attempted != 0U)
    {
        attempted_result[attempted_count++] = result->vertical_result;
    }
    for (index = 0U; index < attempted_count; index++)
    {
        if (attempted_result[index] == NAV_KF_UPDATE_ACCEPTED)
        {
            return NAV_KF_UPDATE_ACCEPTED;
        }
        if (attempted_result[index] == NAV_KF_UPDATE_SOFT_WEIGHTED)
        {
            soft_seen = 1U;
        }
        else if (attempted_result[index] == NAV_KF_UPDATE_REJECTED_NIS)
        {
            nis_reject_seen = 1U;
        }
        else if (attempted_result[index] == NAV_KF_UPDATE_REJECTED_INVALID)
        {
            invalid_seen = 1U;
        }
    }
    if (soft_seen != 0U)
    {
        return NAV_KF_UPDATE_SOFT_WEIGHTED;
    }
    if (nis_reject_seen != 0U)
    {
        return NAV_KF_UPDATE_REJECTED_NIS;
    }
    if (invalid_seen != 0U)
    {
        return NAV_KF_UPDATE_REJECTED_INVALID;
    }
    return NAV_KF_UPDATE_NUMERIC_ERROR;
}

static uint8_t NavigationKf_VectorInputValid(
    NavigationKfContext *context,
    const float *observation,
    const float *variance,
    uint8_t dimension,
    const float *last_nis,
    const float *last_innovation,
    const float *last_effective_variance)
{
    uint8_t row;

    if ((context == NULL) || (context->initialized == 0U) ||
        (last_nis == NULL) || (last_innovation == NULL) ||
        (last_effective_variance == NULL) ||
        (dimension == 0U) || (dimension > 3U) ||
        (NavigationKf_IsFiniteVector(observation, dimension) == 0U) ||
        (NavigationKf_IsFiniteVector(variance, dimension) == 0U))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        }
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < dimension; row++)
    {
        if (variance[row] <= NAV_KF_MATRIX_EPSILON)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
            return 0U;
        }
    }
    return 1U;
}

static uint8_t NavigationKf_VectorWorkPrepare(
    NavigationKfContext *context,
    const float *observation,
    const float *variance,
    uint8_t dimension,
    uint8_t state_offset,
    float *last_innovation,
    float *last_effective_variance,
    NavigationKfVectorWork *work)
{
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationKfVectorWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(work->state_backup, context->state, sizeof(work->state_backup));
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        NavigationKf_NumericRecovery(context, work->state_backup, 0U);
        return 0U;
    }
    memcpy(work->covariance_backup, context->covariance,
           sizeof(work->covariance_backup));
    for (row = 0U; row < dimension; row++)
    {
        work->innovation[row] = observation[row] -
                                context->state[state_offset + row];
        work->effective_variance[row] = variance[row];
        last_innovation[row] = work->innovation[row];
        last_effective_variance[row] = work->effective_variance[row];
        for (column = 0U; column < dimension; column++)
        {
            work->innovation_covariance[row][column] =
                context->covariance[state_offset + row][state_offset + column];
        }
        work->innovation_covariance[row][row] += variance[row];
    }
    if (NavigationKf_CholeskyInverse(work->innovation_covariance,
                                     work->innovation_inverse,
                                     dimension) == 0U)
    {
        NavigationKf_NumericRecovery(context, work->state_backup,
                                     NAV_KF_HEALTH_MATRIX_NOT_SPD);
        return 0U;
    }
    return 1U;
}

static uint8_t NavigationKf_VectorNisCalculate(
    NavigationKfContext *context,
    NavigationKfVectorWork *work,
    uint8_t dimension,
    float *last_nis)
{
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationKfVectorWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    work->nis = 0.0f;
    for (row = 0U; row < dimension; row++)
    {
        for (column = 0U; column < dimension; column++)
        {
            work->nis += work->innovation[row] *
                         work->innovation_inverse[row][column] *
                         work->innovation[column];
        }
    }
    if ((!isfinite(work->nis)) || (work->nis < 0.0f))
    {
        NavigationKf_NumericRecovery(context, work->state_backup, 0U);
        return 0U;
    }
    *last_nis = work->nis;
    return 1U;
}

static uint8_t NavigationKf_VectorSoftWeightProcess(
    NavigationKfContext *context,
    const float *variance,
    uint8_t dimension,
    uint8_t state_offset,
    float *last_effective_variance,
    NavigationKfVectorWork *work)
{
    float scale;
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationKfVectorWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (work->nis <= context->nis_soft_threshold[dimension - 1U])
    {
        return 1U;
    }
    scale = work->nis / context->nis_soft_threshold[dimension - 1U];
    if (scale > context->nis_max_r_scale)
    {
        scale = context->nis_max_r_scale;
    }
    work->result = NAV_KF_UPDATE_SOFT_WEIGHTED;
    for (row = 0U; row < dimension; row++)
    {
        work->effective_variance[row] = variance[row] * scale;
        last_effective_variance[row] = work->effective_variance[row];
        for (column = 0U; column < dimension; column++)
        {
            work->innovation_covariance[row][column] =
                context->covariance[state_offset + row][state_offset + column];
        }
        work->innovation_covariance[row][row] +=
            work->effective_variance[row];
    }
    if (NavigationKf_CholeskyInverse(work->innovation_covariance,
                                     work->innovation_inverse,
                                     dimension) == 0U)
    {
        NavigationKf_NumericRecovery(context, work->state_backup,
                                     NAV_KF_HEALTH_MATRIX_NOT_SPD);
        return 0U;
    }
    return 1U;
}

static uint8_t NavigationKf_VectorGainAndStateApply(
    NavigationKfContext *context,
    NavigationKfVectorWork *work,
    uint8_t dimension,
    uint8_t state_offset)
{
    uint8_t row;
    uint8_t column;
    uint8_t inner;
    uint8_t nonzero = 0U;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, NavigationKfVectorWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < dimension; column++)
        {
            work->gain[row][column] = 0.0f;
            for (inner = 0U; inner < dimension; inner++)
            {
                work->gain[row][column] +=
                    context->covariance[row][state_offset + inner] *
                    work->innovation_inverse[inner][column];
            }
            if (!isfinite(work->gain[row][column])) { return 0U; }
            if (work->gain[row][column] != 0.0f) { nonzero = 1U; }
        }
    }
    /* Validate before any state/P mutation; a zero correction alone is valid,
       but an entirely zero gain cannot refresh successful fusion. */
    if (nonzero == 0U) { return 0U; }
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < dimension; column++)
        {
            context->state[row] += work->gain[row][column] *
                                   work->innovation[column];
        }
    }
    return 1U;
}

static void NavigationKf_VectorCovarianceBuild(
    NavigationKfVectorWork *work,
    uint8_t dimension,
    uint8_t state_offset)
{
    uint8_t row;
    uint8_t column;
    uint8_t inner;

    SILVERSTAR_ASSERT_OBJECT(work, NavigationKfVectorWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memset(work->identity_minus_kh, 0, sizeof(work->identity_minus_kh));
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        work->identity_minus_kh[row][row] = 1.0f;
        for (column = 0U; column < dimension; column++)
        {
            work->identity_minus_kh[row][state_offset + column] -=
                work->gain[row][column];
        }
    }
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            work->temporary[row][column] = 0.0f;
            for (inner = 0U; inner < NAV_KF_STATE_DIMENSION; inner++)
            {
                work->temporary[row][column] +=
                    work->identity_minus_kh[row][inner] *
                    work->covariance_backup[inner][column];
            }
        }
    }
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            work->covariance_new[row][column] = 0.0f;
            for (inner = 0U; inner < NAV_KF_STATE_DIMENSION; inner++)
            {
                work->covariance_new[row][column] +=
                    work->temporary[row][inner] *
                    work->identity_minus_kh[column][inner];
            }
            for (inner = 0U; inner < dimension; inner++)
            {
                work->covariance_new[row][column] +=
                    work->gain[row][inner] * work->effective_variance[inner] *
                    work->gain[column][inner];
            }
        }
    }
}

static NavigationKfUpdateResult NavigationKf_UpdateVector(
    NavigationKfContext *context,
    const float *observation,
    const float *variance,
    uint8_t dimension,
    uint8_t state_offset,
    float *last_nis,
    float *last_innovation,
    float *last_effective_variance)
{
    NavigationKfVectorWork work;

    if (NavigationKf_VectorInputValid(
            context, observation, variance, dimension, last_nis,
            last_innovation, last_effective_variance) == 0U)
    { return NAV_KF_UPDATE_REJECTED_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(
        state_offset <= (uint8_t)(NAV_KF_STATE_DIMENSION - dimension),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    work.result = NAV_KF_UPDATE_ACCEPTED;
    if (NavigationKf_VectorWorkPrepare(
            context, observation, variance, dimension, state_offset,
            last_innovation, last_effective_variance, &work) == 0U)
    { return NAV_KF_UPDATE_NUMERIC_ERROR; }
    if (NavigationKf_VectorNisCalculate(
            context, &work, dimension, last_nis) == 0U)
    { return NAV_KF_UPDATE_NUMERIC_ERROR; }
    if (work.nis >= context->nis_hard_threshold[dimension - 1U])
    { return NAV_KF_UPDATE_REJECTED_NIS; }
    if (NavigationKf_VectorSoftWeightProcess(
            context, variance, dimension, state_offset,
            last_effective_variance, &work) == 0U)
    { return NAV_KF_UPDATE_NUMERIC_ERROR; }
    if (NavigationKf_VectorGainAndStateApply(
            context, &work, dimension, state_offset) == 0U)
    {
        context->numeric_error_count++;
        context->health_flags |= NAV_KF_HEALTH_NUMERIC_ERROR;
        return NAV_KF_UPDATE_NUMERIC_ERROR;
    }
    NavigationKf_VectorCovarianceBuild(&work, dimension, state_offset);
    memcpy(context->covariance, work.covariance_new,
           sizeof(work.covariance_new));
    NavigationKf_CovarianceSymmetrizeAndClamp(context);
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        memcpy(context->state, work.state_backup, sizeof(work.state_backup));
        NavigationKf_NumericRecovery(context, work.state_backup, 0U);
        return NAV_KF_UPDATE_NUMERIC_ERROR;
    }
    return work.result;
}

void NavigationKf_Init(NavigationKfContext *context)
{
    if (context == NULL)
    {
        return;
    }

    memset(context, 0, sizeof(*context));
    context->process_accel_std_mps2[0] = NAV_KF_DEFAULT_PROCESS_E_STD_MPS2;
    context->process_accel_std_mps2[1] = NAV_KF_DEFAULT_PROCESS_N_STD_MPS2;
    context->process_accel_std_mps2[2] = NAV_KF_DEFAULT_PROCESS_U_STD_MPS2;
    context->baro_std_m = NAV_KF_DEFAULT_BARO_STD_M;
    context->nis_soft_threshold[0] = NAV_KF_DEFAULT_NIS_1D_SOFT;
    context->nis_soft_threshold[1] = NAV_KF_DEFAULT_NIS_2D_SOFT;
    context->nis_soft_threshold[2] = NAV_KF_DEFAULT_NIS_3D_SOFT;
    context->nis_hard_threshold[0] = NAV_KF_DEFAULT_NIS_1D_HARD;
    context->nis_hard_threshold[1] = NAV_KF_DEFAULT_NIS_2D_HARD;
    context->nis_hard_threshold[2] = NAV_KF_DEFAULT_NIS_3D_HARD;
    context->nis_max_r_scale = NAV_KF_DEFAULT_NIS_MAX_R_SCALE;
    NavigationKf_Reset(context);
}

static void NavigationKf_ConfigSnapshotCapture(
    const NavigationKfContext *context,
    NavigationKfConfigSnapshot *snapshot)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(snapshot, NavigationKfConfigSnapshot,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(snapshot->process_accel_std, context->process_accel_std_mps2,
           sizeof(snapshot->process_accel_std));
    snapshot->baro_std = context->baro_std_m;
    memcpy(snapshot->nis_soft_threshold, context->nis_soft_threshold,
           sizeof(snapshot->nis_soft_threshold));
    memcpy(snapshot->nis_hard_threshold, context->nis_hard_threshold,
           sizeof(snapshot->nis_hard_threshold));
    snapshot->nis_max_r_scale = context->nis_max_r_scale;
}

static void NavigationKf_ProcessConfigRestore(
    NavigationKfContext *context,
    const NavigationKfConfigSnapshot *snapshot)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(snapshot, NavigationKfConfigSnapshot,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((NavigationKf_IsFiniteVector(snapshot->process_accel_std, 3U) != 0U) &&
        (snapshot->process_accel_std[0] > 0.0f) &&
        (snapshot->process_accel_std[1] > 0.0f) &&
        (snapshot->process_accel_std[2] > 0.0f))
    {
        memcpy(context->process_accel_std_mps2, snapshot->process_accel_std,
               sizeof(snapshot->process_accel_std));
    }
    else
    {
        context->process_accel_std_mps2[0] = NAV_KF_DEFAULT_PROCESS_E_STD_MPS2;
        context->process_accel_std_mps2[1] = NAV_KF_DEFAULT_PROCESS_N_STD_MPS2;
        context->process_accel_std_mps2[2] = NAV_KF_DEFAULT_PROCESS_U_STD_MPS2;
    }
    context->baro_std_m =
        (isfinite(snapshot->baro_std) && (snapshot->baro_std > 0.0f)) ?
        snapshot->baro_std : NAV_KF_DEFAULT_BARO_STD_M;
}

static void NavigationKf_NisConfigRestore(
    NavigationKfContext *context,
    const NavigationKfConfigSnapshot *snapshot)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(snapshot, NavigationKfConfigSnapshot,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((NavigationKf_IsFiniteVector(snapshot->nis_soft_threshold, 3U) != 0U) &&
        (NavigationKf_IsFiniteVector(snapshot->nis_hard_threshold, 3U) != 0U) &&
        (snapshot->nis_soft_threshold[0] > 0.0f) &&
        (snapshot->nis_soft_threshold[1] > 0.0f) &&
        (snapshot->nis_soft_threshold[2] > 0.0f) &&
        (snapshot->nis_hard_threshold[0] > snapshot->nis_soft_threshold[0]) &&
        (snapshot->nis_hard_threshold[1] > snapshot->nis_soft_threshold[1]) &&
        (snapshot->nis_hard_threshold[2] > snapshot->nis_soft_threshold[2]) &&
        isfinite(snapshot->nis_max_r_scale) &&
        (snapshot->nis_max_r_scale >= 1.0f))
    {
        memcpy(context->nis_soft_threshold, snapshot->nis_soft_threshold,
               sizeof(snapshot->nis_soft_threshold));
        memcpy(context->nis_hard_threshold, snapshot->nis_hard_threshold,
               sizeof(snapshot->nis_hard_threshold));
        context->nis_max_r_scale = snapshot->nis_max_r_scale;
    }
    else
    {
        context->nis_soft_threshold[0] = NAV_KF_DEFAULT_NIS_1D_SOFT;
        context->nis_soft_threshold[1] = NAV_KF_DEFAULT_NIS_2D_SOFT;
        context->nis_soft_threshold[2] = NAV_KF_DEFAULT_NIS_3D_SOFT;
        context->nis_hard_threshold[0] = NAV_KF_DEFAULT_NIS_1D_HARD;
        context->nis_hard_threshold[1] = NAV_KF_DEFAULT_NIS_2D_HARD;
        context->nis_hard_threshold[2] = NAV_KF_DEFAULT_NIS_3D_HARD;
        context->nis_max_r_scale = NAV_KF_DEFAULT_NIS_MAX_R_SCALE;
    }
}

static void NavigationKf_ReacquisitionReset(NavigationKfContext *context)
{
    uint8_t group;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    context->gnss_reacquisition.last_inflation_group =
        NAV_KF_GNSS_GROUP_INVALID;
    context->gnss_reacquisition.last_inflation_factor = 1.0f;
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        context->gnss_reacquisition.group[group].last_inflation_factor =
            1.0f;
    }
}

void NavigationKf_Reset(NavigationKfContext *context)
{
    NavigationKfConfigSnapshot snapshot;

    if (context == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationKf_ConfigSnapshotCapture(context, &snapshot);
    memset(context, 0, sizeof(*context));
    NavigationKf_ProcessConfigRestore(context, &snapshot);
    NavigationKf_NisConfigRestore(context, &snapshot);
    NavigationKf_CovarianceInitialSet(context);
    NavigationKf_ReacquisitionReset(context);
    context->initialized = 1U;
}

uint8_t NavigationKf_ResetWithCovariance(
    NavigationKfContext *context,
    const float *covariance)
{
    uint8_t row;
    uint8_t column;

    if ((context == NULL) || (covariance == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(covariance, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationKf_Reset(context);
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            if (!isfinite(covariance[((uint32_t)row * 6U) + column]))
            {
                context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
                return 0U;
            }
            context->covariance[row][column] =
                covariance[((uint32_t)row * 6U) + column];
        }
    }
    NavigationKf_CovarianceSymmetrizeAndClamp(context);
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        NavigationKf_CovarianceInitialSet(context);
        context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        return 0U;
    }
    return 1U;
}

static void NavigationKf_PredictState(
    NavigationKfContext *context,
    const float delta_velocity_enu_mps[3],
    float dt_s,
    float delta_velocity_variance[3])
{
    float velocity_previous[3];
    uint8_t row;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(delta_velocity_enu_mps, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(velocity_previous, &context->state[3], sizeof(velocity_previous));
    for (row = 0U; row < NAV_KF_VECTOR_DIMENSION; row++)
    {
        float sigma_delta_velocity =
            context->process_accel_std_mps2[row] * dt_s;
        delta_velocity_variance[row] =
            sigma_delta_velocity * sigma_delta_velocity;

        context->state[row] += velocity_previous[row] * dt_s +
                               0.5f * delta_velocity_enu_mps[row] * dt_s;
        context->state[row + 3U] += delta_velocity_enu_mps[row];
    }
}

static void NavigationKf_PredictCovariance(
    const NavigationKfContext *context,
    const float delta_velocity_variance[3],
    float dt_s,
    float covariance_new[6][6])
{
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(covariance_new, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        uint8_t row_axis = (uint8_t)(row % 3U);
        uint8_t row_is_position = (row < 3U) ? 1U : 0U;
        float row_noise_gain = (row_is_position != 0U) ? (0.5f * dt_s) : 1.0f;

        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            uint8_t column_axis = (uint8_t)(column % 3U);
            uint8_t column_is_position = (column < 3U) ? 1U : 0U;
            float column_noise_gain =
                (column_is_position != 0U) ? (0.5f * dt_s) : 1.0f;
            float value = context->covariance[row][column];

            if (row_is_position != 0U)
            {
                value += dt_s * context->covariance[row + 3U][column];
            }
            if (column_is_position != 0U)
            {
                value += dt_s * context->covariance[row][column + 3U];
            }
            if ((row_is_position != 0U) && (column_is_position != 0U))
            {
                value += dt_s * dt_s *
                         context->covariance[row + 3U][column + 3U];
            }
            if (row_axis == column_axis)
            {
                value += row_noise_gain * column_noise_gain *
                         delta_velocity_variance[row_axis];
            }
            covariance_new[row][column] = value;
        }
    }
}

uint8_t NavigationKf_Predict(NavigationKfContext *context,
                             const float delta_velocity_enu_mps[3],
                             float dt_s)
{
    float state_backup[6];
    float covariance_new[6][6];
    float delta_velocity_variance[3];

    if ((context == NULL) || (context->initialized == 0U) ||
        (NavigationKf_IsFiniteVector(delta_velocity_enu_mps, 3U) == 0U) ||
        (!isfinite(dt_s)) || (dt_s <= 0.0f) || (dt_s > NAV_KF_DT_MAX_S))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        }
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(delta_velocity_enu_mps, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(state_backup, context->state, sizeof(state_backup));
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        NavigationKf_NumericRecovery(context, state_backup, 0U);
        return 0U;
    }
    NavigationKf_PredictState(context, delta_velocity_enu_mps, dt_s,
                              delta_velocity_variance);
    NavigationKf_PredictCovariance(
        context, delta_velocity_variance, dt_s, covariance_new);

    memcpy(context->covariance, covariance_new, sizeof(covariance_new));
    NavigationKf_CovarianceSymmetrizeAndClamp(context);
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        memcpy(context->state, state_backup, sizeof(state_backup));
        NavigationKf_NumericRecovery(context, state_backup, 0U);
        return 0U;
    }

    context->predict_count++;
    return 1U;
}

NavigationKfUpdateResult NavigationKf_UpdateGnssPosition(
    NavigationKfContext *context,
    const float position_enu_m[3],
    const float variance_m2[3])
{
    return NavigationKf_UpdateGnssPositionSeparated(
        context, position_enu_m, variance_m2, NULL);
}

static NavigationKfUpdateResult NavigationKf_PositionResultFinalize(
    NavigationKfContext *context,
    const NavigationKfGnssSeparatedUpdateResult *result)
{
    NavigationKfUpdateResult aggregate_result;

    SILVERSTAR_ASSERT_OBJECT(result, NavigationKfGnssSeparatedUpdateResult,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    aggregate_result = NavigationKf_SeparatedResultAggregate(result);
    if (context != NULL)
    {
        context->last_position_nis =
            (context->last_gnss_group_nis[
                 NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL] >
             context->last_gnss_group_nis[
                 NAV_KF_GNSS_GROUP_POSITION_VERTICAL]) ?
                context->last_gnss_group_nis[
                    NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL] :
                context->last_gnss_group_nis[
                    NAV_KF_GNSS_GROUP_POSITION_VERTICAL];
        NavigationKf_UpdateCounters(context, NAV_KF_MEASUREMENT_POSITION,
                                    aggregate_result);
    }
    return aggregate_result;
}

NavigationKfUpdateResult NavigationKf_UpdateGnssPositionSeparated(
    NavigationKfContext *context, const float position_enu_m[3],
    const float variance_m2[3], NavigationKfGnssSeparatedUpdateResult *result)
{
    return NavigationKf_UpdateGnssPositionGroups(context, position_enu_m,
        variance_m2, 3U, result);
}

static NavigationKfUpdateResult NavigationKf_PositionInvalidRecord(
    NavigationKfContext *context, NavigationKfGnssSeparatedUpdateResult *result)
{
    SILVERSTAR_ASSERT_OBJECT(result, NavigationKfGnssSeparatedUpdateResult,
                         SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    result->horizontal_attempted = 1U;
    result->vertical_attempted = 1U;
    result->horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    result->vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    NavigationKf_GnssGroupCountersUpdate(
        context, NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL,
        result->horizontal_result);
    NavigationKf_GnssGroupCountersUpdate(
        context, NAV_KF_GNSS_GROUP_POSITION_VERTICAL,
        result->vertical_result);
    NavigationKf_UpdateCounters(context, NAV_KF_MEASUREMENT_POSITION,
                                NAV_KF_UPDATE_REJECTED_INVALID);
    return NAV_KF_UPDATE_REJECTED_INVALID;
}

NavigationKfUpdateResult NavigationKf_UpdateGnssPositionGroups(
    NavigationKfContext *context,
    const float position_enu_m[3],
    const float variance_m2[3],
    uint8_t valid_group_mask,
    NavigationKfGnssSeparatedUpdateResult *separated_result)
{
    NavigationKfGnssSeparatedUpdateResult local_result;
    NavigationKfGnssSeparatedUpdateResult *result = separated_result;

    if (result == NULL)
    {
        result = &local_result;
    }
    (void)memset(result, 0, sizeof(*result));
    result->horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    result->vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    if ((position_enu_m == NULL) || (variance_m2 == NULL))
    { return NavigationKf_PositionInvalidRecord(context, result); }
    SILVERSTAR_ASSERT_OBJECT(position_enu_m, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(variance_m2, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((valid_group_mask & 1U) != 0U)
    {
        result->horizontal_attempted = 1U;
        result->horizontal_result = NavigationKf_UpdateVector(
            context, position_enu_m, variance_m2, 2U, 0U,
            (context != NULL) ?
                &context->last_gnss_group_nis[
                    NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL] : NULL,
            (context != NULL) ? &context->last_position_innovation[0] : NULL,
            (context != NULL) ?
                &context->last_position_effective_variance[0] : NULL);
        NavigationKf_GnssGroupCountersUpdate(
            context, NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL,
            result->horizontal_result);
    }
    if ((valid_group_mask & 2U) != 0U)
    {
        result->vertical_attempted = 1U;
        result->vertical_result = NavigationKf_UpdateVector(
            context, &position_enu_m[2], &variance_m2[2], 1U, 2U,
            (context != NULL) ?
                &context->last_gnss_group_nis[
                    NAV_KF_GNSS_GROUP_POSITION_VERTICAL] : NULL,
            (context != NULL) ? &context->last_position_innovation[2] : NULL,
            (context != NULL) ?
                &context->last_position_effective_variance[2] : NULL);
        NavigationKf_GnssGroupCountersUpdate(
            context, NAV_KF_GNSS_GROUP_POSITION_VERTICAL,
            result->vertical_result);
    }
    return NavigationKf_PositionResultFinalize(context, result);
}

NavigationKfUpdateResult NavigationKf_UpdateGnssVelocity2D(
    NavigationKfContext *context,
    const float velocity_enu_mps[2],
    const float variance_m2ps2[2])
{
    float velocity_3d[3] = {0.0f, 0.0f, 0.0f};
    float variance_3d[3] = {1.0f, 1.0f, 1.0f};

    if (context == NULL) { return NAV_KF_UPDATE_REJECTED_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if ((velocity_enu_mps != NULL) && (variance_m2ps2 != NULL))
    {
        velocity_3d[0] = velocity_enu_mps[0];
        velocity_3d[1] = velocity_enu_mps[1];
        variance_3d[0] = variance_m2ps2[0];
        variance_3d[1] = variance_m2ps2[1];
    }
    else
    {
        velocity_3d[0] = NAN;
    }
    return NavigationKf_UpdateGnssVelocitySeparated(
        context, velocity_3d, variance_3d, 0U, NULL);
}

NavigationKfUpdateResult NavigationKf_UpdateGnssVelocity3D(
    NavigationKfContext *context,
    const float velocity_enu_mps[3],
    const float variance_m2ps2[3])
{
    return NavigationKf_UpdateGnssVelocitySeparated(
        context, velocity_enu_mps, variance_m2ps2, 1U, NULL);
}

static NavigationKfUpdateResult NavigationKf_VelocityInvalidRecord(
    NavigationKfContext *context,
    NavigationKfGnssSeparatedUpdateResult *result,
    uint8_t vertical_valid)
{
    SILVERSTAR_ASSERT_OBJECT(result, NavigationKfGnssSeparatedUpdateResult,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    result->horizontal_attempted = 1U;
    result->horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    if (vertical_valid != 0U)
    {
        result->vertical_attempted = 1U;
        result->vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    }
    NavigationKf_GnssGroupCountersUpdate(
        context, NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL,
        result->horizontal_result);
    if (result->vertical_attempted != 0U)
    {
        NavigationKf_GnssGroupCountersUpdate(
            context, NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL,
            result->vertical_result);
    }
    NavigationKf_UpdateCounters(context, NAV_KF_MEASUREMENT_VELOCITY,
                                NAV_KF_UPDATE_REJECTED_INVALID);
    return NAV_KF_UPDATE_REJECTED_INVALID;
}

static NavigationKfUpdateResult NavigationKf_VelocityResultFinalize(
    NavigationKfContext *context,
    const NavigationKfGnssSeparatedUpdateResult *result)
{
    NavigationKfUpdateResult aggregate_result;

    SILVERSTAR_ASSERT_OBJECT(result, NavigationKfGnssSeparatedUpdateResult,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    aggregate_result = NavigationKf_SeparatedResultAggregate(result);
    if (context != NULL)
    {
        context->last_velocity_nis = context->last_gnss_group_nis[
            NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL];
        if ((result->vertical_attempted != 0U) &&
            (context->last_gnss_group_nis[
                 NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL] >
             context->last_velocity_nis))
        {
            context->last_velocity_nis = context->last_gnss_group_nis[
                NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL];
        }
        NavigationKf_UpdateCounters(context, NAV_KF_MEASUREMENT_VELOCITY,
                                    aggregate_result);
    }
    return aggregate_result;
}

NavigationKfUpdateResult NavigationKf_UpdateGnssVelocitySeparated(
    NavigationKfContext *context, const float velocity_enu_mps[3],
    const float variance_m2ps2[3], uint8_t vertical_valid,
    NavigationKfGnssSeparatedUpdateResult *result)
{
    return NavigationKf_UpdateGnssVelocityGroups(context, velocity_enu_mps,
        variance_m2ps2, (vertical_valid != 0U) ? 12U : 4U, result);
}

NavigationKfUpdateResult NavigationKf_UpdateGnssVelocityGroups(
    NavigationKfContext *context,
    const float velocity_enu_mps[3],
    const float variance_m2ps2[3],
    uint8_t valid_group_mask,
    NavigationKfGnssSeparatedUpdateResult *separated_result)
{
    NavigationKfGnssSeparatedUpdateResult local_result;
    NavigationKfGnssSeparatedUpdateResult *result = separated_result;

    if (result == NULL)
    {
        result = &local_result;
    }
    (void)memset(result, 0, sizeof(*result));
    result->horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    result->vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    if ((velocity_enu_mps == NULL) || (variance_m2ps2 == NULL))
    {
        return NavigationKf_VelocityInvalidRecord(
            context, result, (uint8_t)((valid_group_mask & 8U) != 0U));
    }
    SILVERSTAR_ASSERT_OBJECT(velocity_enu_mps, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(variance_m2ps2, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((valid_group_mask & 4U) != 0U)
    {
        result->horizontal_attempted = 1U;
        result->horizontal_result = NavigationKf_UpdateVector(
            context, velocity_enu_mps, variance_m2ps2, 2U, 3U,
            (context != NULL) ?
                &context->last_gnss_group_nis[
                    NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL] : NULL,
            (context != NULL) ? &context->last_velocity_innovation[0] : NULL,
            (context != NULL) ?
                &context->last_velocity_effective_variance[0] : NULL);
        NavigationKf_GnssGroupCountersUpdate(
            context, NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL,
            result->horizontal_result);
    }
    if ((valid_group_mask & 8U) != 0U)
    {
            result->vertical_attempted = 1U;
            result->vertical_result = NavigationKf_UpdateVector(
                context, &velocity_enu_mps[2], &variance_m2ps2[2], 1U, 5U,
                (context != NULL) ?
                    &context->last_gnss_group_nis[
                        NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL] : NULL,
                (context != NULL) ? &context->last_velocity_innovation[2] : NULL,
                (context != NULL) ?
                    &context->last_velocity_effective_variance[2] : NULL);
            NavigationKf_GnssGroupCountersUpdate(
                context, NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL,
                result->vertical_result);
    }
    return NavigationKf_VelocityResultFinalize(context, result);
}

NavigationKfUpdateResult NavigationKf_UpdateBaroAltitude(
    NavigationKfContext *context,
    float altitude_up_m,
    float variance_m2)
{
    float observation[1] = {altitude_up_m};
    float variance[1] = {variance_m2};
    float last_innovation[1];
    float last_effective_variance[1];
    NavigationKfUpdateResult result = NavigationKf_UpdateVector(
        context, observation, variance, 1U, 2U,
        (context != NULL) ? &context->last_baro_nis : NULL,
        last_innovation, last_effective_variance);

    if (context != NULL)
    {
        SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                                 SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    }
    NavigationKf_UpdateCounters(context, NAV_KF_MEASUREMENT_BARO, result);
    return result;
}

static float NavigationKf_Max(float lhs, float rhs)
{
    return (lhs > rhs) ? lhs : rhs;
}

static uint8_t NavigationKf_GnssReacquireConfigIsValid(void)
{
    SILVERSTAR_ASSERT(
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MIN_DT_MS <
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_DT_MS,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    SILVERSTAR_ASSERT(
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_REJECT_COUNT > 0U) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT > 0U),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    return (uint8_t)(
        isfinite(SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_FACTOR) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_HORIZONTAL_FLOOR_M) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VERTICAL_FLOOR_M) &&
        isfinite(SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_HORIZONTAL_ACCEL_MPS2) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_VERTICAL_ACCEL_MPS2) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2) &&
        isfinite(
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_VELOCITY_VARIANCE_CAP_M2PS2) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_FACTOR > 1.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_HORIZONTAL_FLOOR_M >
         0.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VERTICAL_FLOOR_M >
         0.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE > 0.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_HORIZONTAL_ACCEL_MPS2 >
         0.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_VERTICAL_ACCEL_MPS2 > 0.0f) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2 >
         NAV_KF_P_DIAGONAL_MIN) &&
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_VELOCITY_VARIANCE_CAP_M2PS2 >
         NAV_KF_P_DIAGONAL_MIN));
}

static uint8_t NavigationKf_GnssEpochGroupFinite(
    const NavigationKfGnssEpoch *epoch,
    NavigationKfGnssGroup group)
{
    if (epoch == NULL)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((group == NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL) ||
        (group == NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL))
    {
        const float *values =
            (group == NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL) ?
                epoch->position_enu_m : epoch->velocity_enu_mps;
        const float *standard_deviation =
            (group == NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL) ?
                epoch->position_std_m : epoch->velocity_std_mps;

        return (uint8_t)(
            (NavigationKf_IsFiniteVector(values, 2U) != 0U) &&
            (NavigationKf_IsFiniteVector(standard_deviation, 2U) != 0U) &&
            (standard_deviation[0] > 0.0f) &&
            (standard_deviation[1] > 0.0f));
    }
    if ((group == NAV_KF_GNSS_GROUP_POSITION_VERTICAL) ||
        (group == NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL))
    {
        uint8_t index = 2U;
        float value = (group == NAV_KF_GNSS_GROUP_POSITION_VERTICAL) ?
            epoch->position_enu_m[index] : epoch->velocity_enu_mps[index];
        float standard_deviation =
            (group == NAV_KF_GNSS_GROUP_POSITION_VERTICAL) ?
                epoch->position_std_m[index] :
                epoch->velocity_std_mps[index];

        return (uint8_t)(isfinite(value) && isfinite(standard_deviation) &&
                         (standard_deviation > 0.0f));
    }
    return 0U;
}

static uint8_t NavigationKf_GnssPositionHorizontalConsistent(
    const NavigationKfGnssEpoch *previous,
    const NavigationKfGnssEpoch *current,
    float dt_s)
{
    SILVERSTAR_ASSERT_OBJECT(previous, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(current, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    float residual_e = (current->position_enu_m[0] -
                        previous->position_enu_m[0]) -
        (0.5f * (previous->velocity_enu_mps[0] +
                 current->velocity_enu_mps[0]) * dt_s);
    float residual_n = (current->position_enu_m[1] -
                        previous->position_enu_m[1]) -
        (0.5f * (previous->velocity_enu_mps[1] +
                 current->velocity_enu_mps[1]) * dt_s);
    float position_variance =
        previous->position_std_m[0] * previous->position_std_m[0] +
        previous->position_std_m[1] * previous->position_std_m[1] +
        current->position_std_m[0] * current->position_std_m[0] +
        current->position_std_m[1] * current->position_std_m[1];
    float velocity_variance =
        previous->velocity_std_mps[0] * previous->velocity_std_mps[0] +
        previous->velocity_std_mps[1] * previous->velocity_std_mps[1] +
        current->velocity_std_mps[0] * current->velocity_std_mps[0] +
        current->velocity_std_mps[1] * current->velocity_std_mps[1];
    float uncertainty = sqrtf(position_variance +
                              (0.25f * dt_s * dt_s * velocity_variance));
    float tolerance = NavigationKf_Max(
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_HORIZONTAL_FLOOR_M,
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE * uncertainty);

    return (uint8_t)(sqrtf(residual_e * residual_e +
                           residual_n * residual_n) <= tolerance);
}

static uint8_t NavigationKf_GnssPositionVerticalConsistent(
    const NavigationKfGnssEpoch *previous,
    const NavigationKfGnssEpoch *current,
    float dt_s)
{
    SILVERSTAR_ASSERT_OBJECT(previous, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(current, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    float residual = (current->position_enu_m[2] -
                      previous->position_enu_m[2]) -
        (0.5f * (previous->velocity_enu_mps[2] +
                 current->velocity_enu_mps[2]) * dt_s);
    float position_variance =
        previous->position_std_m[2] * previous->position_std_m[2] +
        current->position_std_m[2] * current->position_std_m[2];
    float velocity_variance =
        previous->velocity_std_mps[2] * previous->velocity_std_mps[2] +
        current->velocity_std_mps[2] * current->velocity_std_mps[2];
    float uncertainty = sqrtf(position_variance +
                              (0.25f * dt_s * dt_s * velocity_variance));
    float tolerance = NavigationKf_Max(
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VERTICAL_FLOOR_M,
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE * uncertainty);

    return (uint8_t)(fabsf(residual) <= tolerance);
}

static uint8_t NavigationKf_GnssVelocityHorizontalConsistent(
    const NavigationKfGnssEpoch *previous,
    const NavigationKfGnssEpoch *current,
    float dt_s)
{
    float delta_e = current->velocity_enu_mps[0] -
                    previous->velocity_enu_mps[0];
    float delta_n = current->velocity_enu_mps[1] -
                    previous->velocity_enu_mps[1];
    float uncertainty = sqrtf(
        previous->velocity_std_mps[0] * previous->velocity_std_mps[0] +
        previous->velocity_std_mps[1] * previous->velocity_std_mps[1] +
        current->velocity_std_mps[0] * current->velocity_std_mps[0] +
        current->velocity_std_mps[1] * current->velocity_std_mps[1]);
    float tolerance =
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_HORIZONTAL_ACCEL_MPS2 * dt_s +
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE * uncertainty;

    return (uint8_t)(sqrtf(delta_e * delta_e + delta_n * delta_n) <=
                     tolerance);
}

static uint8_t NavigationKf_GnssVelocityVerticalConsistent(
    const NavigationKfGnssEpoch *previous,
    const NavigationKfGnssEpoch *current,
    float dt_s)
{
    float delta = current->velocity_enu_mps[2] -
                  previous->velocity_enu_mps[2];
    float uncertainty = sqrtf(
        previous->velocity_std_mps[2] * previous->velocity_std_mps[2] +
        current->velocity_std_mps[2] * current->velocity_std_mps[2]);
    float tolerance =
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_VERTICAL_ACCEL_MPS2 * dt_s +
        SYSTEM_ESTIMATOR_GNSS_REACQUIRE_UNCERTAINTY_SCALE * uncertainty;

    return (uint8_t)(fabsf(delta) <= tolerance);
}

static uint8_t NavigationKf_GnssCurrentValidMaskGet(
    const NavigationKfGnssEpoch *epoch)
{
    uint8_t valid_mask = 0U;
    uint8_t group;

    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        uint8_t bit = NAV_KF_GNSS_GROUP_MASK(group);
        if (((epoch->valid_group_mask & bit) != 0U) &&
            (NavigationKf_GnssEpochGroupFinite(
                 epoch, (NavigationKfGnssGroup)group) != 0U))
        {
            valid_mask |= bit;
        }
    }
    return valid_mask;
}

static void NavigationKf_GnssEpochBaselineSet(
    NavigationKfGnssReacquisitionContext *reacquisition,
    const NavigationKfGnssEpoch *epoch,
    uint8_t valid_mask)
{
    uint8_t group;

    SILVERSTAR_ASSERT_OBJECT(reacquisition,
                             NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        reacquisition->group[group].consistent_count = 0U;
        reacquisition->group[group].consistency_start_us = 0U;
    }
    reacquisition->previous_epoch = *epoch;
    reacquisition->previous_epoch.valid_group_mask = valid_mask;
    reacquisition->previous_epoch_valid = 1U;
}

static uint8_t NavigationKf_GnssRequiredMaskGet(
    NavigationKfGnssGroup group)
{
    uint8_t required_mask = NAV_KF_GNSS_GROUP_MASK(group);

    if (group == NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL)
    {
        required_mask |= NAV_KF_GNSS_GROUP_MASK(
            NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL);
    }
    else if (group == NAV_KF_GNSS_GROUP_POSITION_VERTICAL)
    {
        required_mask |= NAV_KF_GNSS_GROUP_MASK(
            NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL);
    }
    return required_mask;
}

static uint8_t NavigationKf_GnssGroupConsistencyGet(
    const NavigationKfGnssEpoch *previous,
    const NavigationKfGnssEpoch *current,
    NavigationKfGnssGroup group,
    float dt_s)
{
    SILVERSTAR_ASSERT_OBJECT(previous, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(current, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    switch (group)
    {
        case NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL:
            return NavigationKf_GnssPositionHorizontalConsistent(
                previous, current, dt_s);
        case NAV_KF_GNSS_GROUP_POSITION_VERTICAL:
            return NavigationKf_GnssPositionVerticalConsistent(
                previous, current, dt_s);
        case NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL:
            return NavigationKf_GnssVelocityHorizontalConsistent(
                previous, current, dt_s);
        case NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL:
            return NavigationKf_GnssVelocityVerticalConsistent(
                previous, current, dt_s);
        case NAV_KF_GNSS_GROUP_COUNT:
        default:
            return 0U;
    }
}

static void NavigationKf_GnssConsistencyUpdate(
    NavigationKfGnssReacquisitionContext *reacquisition,
    const NavigationKfGnssEpoch *epoch,
    uint8_t current_valid_mask,
    float dt_s)
{
    uint8_t group;

    SILVERSTAR_ASSERT_OBJECT(reacquisition,
                             NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        uint8_t bit = NAV_KF_GNSS_GROUP_MASK(group);
        uint8_t required_mask = NavigationKf_GnssRequiredMaskGet(
            (NavigationKfGnssGroup)group);
        uint8_t consistent = 0U;

        if (((current_valid_mask & required_mask) == required_mask) &&
            ((reacquisition->previous_epoch.valid_group_mask &
              required_mask) == required_mask))
        {
            consistent = NavigationKf_GnssGroupConsistencyGet(
                &reacquisition->previous_epoch, epoch,
                (NavigationKfGnssGroup)group, dt_s);
        }
        if (consistent != 0U)
        {
            if (reacquisition->group[group].consistent_count == 0U)
            { reacquisition->group[group].consistency_start_us = reacquisition->previous_epoch.timestamp_us; }
            if (reacquisition->group[group].consistent_count < UINT32_MAX)
            {
                reacquisition->group[group].consistent_count++;
            }
            reacquisition->consistency_mask |= bit;
        }
        else
        {
            reacquisition->group[group].consistent_count = 0U;
        reacquisition->group[group].consistency_start_us = 0U;
        }
    }
}

/* Availability uses each group's own valid sample clock, never its NIS result.
 * No new sample is required during loss: the returning epoch closes the gap. */
static void NavigationKf_GnssAvailabilityTrack(
    NavigationKfGnssReacquisitionContext *reacquisition,
    const NavigationKfGnssEpoch *epoch,
    uint8_t valid_mask)
{
    uint8_t group;
    SILVERSTAR_ASSERT_OBJECT(reacquisition, NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        NavigationKfGnssReacquireGroupState *state = &reacquisition->group[group];
        uint8_t bit = NAV_KF_GNSS_GROUP_MASK(group);
        uint64_t anchor = state->availability_timestamp_us;
        if (anchor == 0U)
        {
            state->availability_timestamp_us = epoch->timestamp_us;
        }
        else if ((epoch->timestamp_us - anchor) >
                 ((uint64_t)SYSTEM_ESTIMATOR_GNSS_REACQUIRE_OUTAGE_MS * 1000ULL))
        {
            /* Reset once per loss, including a new loss during recovery. */
            if (state->loss_latched == 0U)
            {
                uint32_t generation = state->generation + 1U;
                (void)memset(state, 0, sizeof(*state));
                state->generation = generation;
                state->availability_timestamp_us = anchor;
                state->outage = 1U;
                state->loss_latched = 1U;
                reacquisition->active_mask &= (uint8_t)(~bit);
            }
        }
        if ((valid_mask & bit) != 0U)
        {
            state->loss_latched = 0U;
            state->availability_timestamp_us = epoch->timestamp_us;
        }
        else
        {
            state->reject_streak = 0U;
            state->accepted_streak = 0U;
            state->consistent_count = 0U;
            state->consistency_start_us = 0U;
        }
    }
}

static void NavigationKf_GnssDuplicateEpochReset(
    NavigationKfGnssReacquisitionContext *reacquisition,
    const NavigationKfGnssEpoch *epoch)
{
    /* A reset/duplicate cannot authorize recovery or accumulate rejects. */
    uint8_t group;
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        uint32_t generation = reacquisition->group[group].generation + 1U;
        (void)memset(&reacquisition->group[group], 0, sizeof(reacquisition->group[group]));
        reacquisition->group[group].generation = generation;
    }
    reacquisition->active_mask = 0U;
    NavigationKf_GnssEpochBaselineSet(reacquisition, epoch, 0U);
}

static void NavigationKf_GnssEpochConsistencyTrack(
    NavigationKfGnssReacquisitionContext *reacquisition,
    const NavigationKfGnssEpoch *epoch, uint8_t current_valid_mask)
{
    uint64_t dt_us;
    float dt_s;
    SILVERSTAR_ASSERT_OBJECT(reacquisition, NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    dt_us = epoch->timestamp_us - reacquisition->previous_epoch.timestamp_us;
    if ((dt_us < ((uint64_t)
                  SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MIN_DT_MS * 1000ULL)) ||
        (dt_us > ((uint64_t)
                  SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_DT_MS * 1000ULL)))
    {
        NavigationKf_GnssEpochBaselineSet(
            reacquisition, epoch, current_valid_mask);
        return;
    }
    dt_s = (float)dt_us * 1.0e-6f;
    NavigationKf_GnssConsistencyUpdate(
        reacquisition, epoch, current_valid_mask, dt_s);
    reacquisition->previous_epoch = *epoch;
    reacquisition->previous_epoch.valid_group_mask = current_valid_mask;
}

void NavigationKf_GnssEpochTrack(
    NavigationKfContext *context,
    const NavigationKfGnssEpoch *epoch)
{
    NavigationKfGnssReacquisitionContext *reacquisition;
    uint8_t current_valid_mask;

    if ((context == NULL) || (epoch == NULL) ||
        (context->initialized == 0U) || (epoch->timestamp_us == 0U))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
            context->gnss_reacquisition.previous_epoch.valid_group_mask = 0U;
        }
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(epoch, NavigationKfGnssEpoch,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ENABLE == 0U)
    {
        return;
    }
    if (NavigationKf_GnssReacquireConfigIsValid() == 0U)
    {
        context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        return;
    }
    reacquisition = &context->gnss_reacquisition;
    current_valid_mask = NavigationKf_GnssCurrentValidMaskGet(epoch);
    reacquisition->consistency_mask = 0U;
    if ((reacquisition->previous_epoch_valid != 0U) &&
        (epoch->timestamp_us <= reacquisition->previous_epoch.timestamp_us))
    {
        NavigationKf_GnssDuplicateEpochReset(reacquisition, epoch);
        return;
    }
    NavigationKf_GnssAvailabilityTrack(reacquisition, epoch, current_valid_mask);
    if (reacquisition->previous_epoch_valid == 0U)
    {
        NavigationKf_GnssEpochBaselineSet(reacquisition, epoch, current_valid_mask);
        return;
    }
    NavigationKf_GnssEpochConsistencyTrack(reacquisition, epoch, current_valid_mask);
}

static void NavigationKf_GnssGroupRangeGet(
    NavigationKfGnssGroup group,
    uint8_t *first_index,
    uint8_t *dimension,
    float *variance_cap)
{
    SILVERSTAR_ASSERT_OBJECT(first_index, uint8_t,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(dimension, uint8_t,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(variance_cap, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (group == NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL)
    {
        *first_index = 0U;
        *dimension = 2U;
        *variance_cap =
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2;
    }
    else if (group == NAV_KF_GNSS_GROUP_POSITION_VERTICAL)
    {
        *first_index = 2U;
        *dimension = 1U;
        *variance_cap =
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_POSITION_VARIANCE_CAP_M2;
    }
    else if (group == NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL)
    {
        *first_index = 3U;
        *dimension = 2U;
        *variance_cap =
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_VELOCITY_VARIANCE_CAP_M2PS2;
    }
    else
    {
        *first_index = 5U;
        *dimension = 1U;
        *variance_cap =
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_VELOCITY_VARIANCE_CAP_M2PS2;
    }
}

static uint8_t NavigationKf_GnssInflationFactorLimit(
    const NavigationKfContext *context,
    uint8_t first_index,
    uint8_t dimension,
    float variance_cap,
    float *factor)
{
    uint8_t row;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(factor, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = first_index; row < (uint8_t)(first_index + dimension); row++)
    {
        float diagonal = context->covariance[row][row];
        float maximum_factor;

        if ((!isfinite(diagonal)) || (diagonal < NAV_KF_P_DIAGONAL_MIN))
        {
            return 0U;
        }
        maximum_factor = sqrtf(variance_cap / diagonal);
        if (*factor > maximum_factor)
        {
            *factor = maximum_factor;
        }
    }
    if (*factor < 1.0f)
    {
        *factor = 1.0f;
    }
    return 1U;
}

static uint8_t NavigationKf_GnssCovarianceScaleApply(
    NavigationKfContext *context,
    uint8_t first_index,
    uint8_t dimension,
    float factor)
{
    float covariance_backup[6][6];
    float scale[6] = {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f};
    uint8_t row;
    uint8_t column;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT((uint8_t)(first_index + dimension) <=
                      NAV_KF_STATE_DIMENSION,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    memcpy(covariance_backup, context->covariance,
           sizeof(covariance_backup));
    for (row = first_index; row < (uint8_t)(first_index + dimension); row++)
    {
        scale[row] = factor;
    }
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        {
            context->covariance[row][column] *= scale[row] * scale[column];
        }
    }
    NavigationKf_CovarianceSymmetrizeAndClamp(context);
    if (NavigationKf_StateAndCovarianceValid(context) == 0U)
    {
        memcpy(context->covariance, covariance_backup,
               sizeof(covariance_backup));
        context->health_flags |= NAV_KF_HEALTH_NUMERIC_ERROR;
        return 0U;
    }
    return 1U;
}

static uint8_t NavigationKf_GnssGroupCovarianceInflate(
    NavigationKfContext *context,
    NavigationKfGnssGroup group,
    float *applied_factor)
{
    float factor = SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_FACTOR;
    float variance_cap;
    uint8_t first_index;
    uint8_t dimension;

    if ((context == NULL) || (applied_factor == NULL) ||
        (group >= NAV_KF_GNSS_GROUP_COUNT) || (!isfinite(factor)) ||
        (factor <= 1.0f))
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(applied_factor, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationKf_GnssGroupRangeGet(
        group, &first_index, &dimension, &variance_cap);
    if ((!isfinite(variance_cap)) ||
        (variance_cap <= NAV_KF_P_DIAGONAL_MIN))
    { return 0U; }
    if (NavigationKf_GnssInflationFactorLimit(
            context, first_index, dimension, variance_cap, &factor) == 0U)
    { return 0U; }
    if (NavigationKf_GnssCovarianceScaleApply(
            context, first_index, dimension, factor) == 0U)
    { return 0U; }
    *applied_factor = factor;
    return 1U;
}

static void NavigationKf_GnssReacquisitionActivate(
    NavigationKfGnssReacquisitionContext *reacquisition,
    NavigationKfGnssReacquireGroupState *state,
    uint8_t bit)
{
    SILVERSTAR_ASSERT_OBJECT(reacquisition,
                             NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfGnssReacquireGroupState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (state->active == 0U)
    {
        state->active = 1U;
        state->inflation_attempt_count = 0U;
        state->epochs_since_inflation =
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES;
        reacquisition->active_mask |= bit;
        reacquisition->reacquire_count++;
    }
}

static void NavigationKf_GnssInflationTry(
    NavigationKfContext *context,
    NavigationKfGnssReacquisitionContext *reacquisition,
    NavigationKfGnssReacquireGroupState *state,
    NavigationKfGnssGroup group)
{
    float applied_factor = 1.0f;

    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfGnssReacquireGroupState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((state->inflation_attempt_count <
         SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS) &&
        (state->epochs_since_inflation >=
         SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES))
    {
        /* An attempt at the cap is still an attempted recovery. */
        (void)NavigationKf_GnssGroupCovarianceInflate(context, group, &applied_factor);
        state->inflation_attempt_count++;
        state->epochs_since_inflation = 0U;
        state->last_inflation_factor = applied_factor;
        reacquisition->last_inflation_group = (uint8_t)group;
        reacquisition->last_inflation_factor = applied_factor;
        reacquisition->last_inflation_attempt =
            state->inflation_attempt_count;
    }
}

static void NavigationKf_GnssRejectedProcess(
    NavigationKfContext *context,
    NavigationKfGnssReacquisitionContext *reacquisition,
    NavigationKfGnssReacquireGroupState *state,
    NavigationKfGnssGroup group,
    uint8_t bit)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfGnssReacquireGroupState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (state->reject_streak < UINT32_MAX) { state->reject_streak++; }
    state->accepted_streak = 0U;
    if ((state->active != 0U) &&
        (state->epochs_since_inflation < UINT32_MAX))
    {
        state->epochs_since_inflation++;
    }
    if ((state->outage != 0U) &&
        (state->reject_streak >=
         SYSTEM_ESTIMATOR_GNSS_REACQUIRE_REJECT_COUNT) &&
        (state->consistent_count >=
         SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT))
    {
        NavigationKf_GnssReacquisitionActivate(reacquisition, state, bit);
        NavigationKf_GnssInflationTry(
            context, reacquisition, state, group);
    }
}

static void NavigationKf_GnssFusedProcess(
    NavigationKfGnssReacquisitionContext *reacquisition,
    NavigationKfGnssReacquireGroupState *state,
    uint8_t bit)
{
    SILVERSTAR_ASSERT_OBJECT(reacquisition,
                             NavigationKfGnssReacquisitionContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfGnssReacquireGroupState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    state->reject_streak = 0U;
    if (state->active == 0U) { state->outage = 0U; }
    if (state->active != 0U)
    {
        if (state->accepted_streak < UINT32_MAX)
        {
            state->accepted_streak++;
        }
        if (state->accepted_streak >=
            SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ACCEPT_COUNT)
        {
            state->active = 0U;
            state->outage = 0U;
            state->accepted_streak = 0U;
            reacquisition->active_mask &= (uint8_t)(~bit);
        }
    }
}

void NavigationKf_GnssGroupResultProcess(
    NavigationKfContext *context,
    NavigationKfGnssGroup group,
    NavigationKfUpdateResult result)
{
    NavigationKfGnssReacquisitionContext *reacquisition;
    NavigationKfGnssReacquireGroupState *state;
    uint8_t bit;

    if ((context == NULL) || (context->initialized == 0U) ||
        (group >= NAV_KF_GNSS_GROUP_COUNT) ||
        (SYSTEM_ESTIMATOR_GNSS_REACQUIRE_ENABLE == 0U))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (NavigationKf_GnssReacquireConfigIsValid() == 0U)
    {
        context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        return;
    }
    reacquisition = &context->gnss_reacquisition;
    state = &reacquisition->group[group];
    bit = NAV_KF_GNSS_GROUP_MASK(group);
    if ((reacquisition->previous_epoch.valid_group_mask & bit) == 0U)
    {
        state->reject_streak = 0U;
        state->accepted_streak = 0U;
        return;
    }
    if (result == NAV_KF_UPDATE_REJECTED_NIS)
    {
        NavigationKf_GnssRejectedProcess(
            context, reacquisition, state, group, bit);
        return;
    }
    if (NavigationKf_UpdateResultFused(result) != 0U)
    {
        NavigationKf_GnssFusedProcess(reacquisition, state, bit);
        return;
    }
    state->reject_streak = 0U;
    state->accepted_streak = 0U;
}

#define NAV_KF_REANCHOR_MIN_CONSISTENCY_US 1000000ULL

static uint8_t NavigationKf_GnssReanchorEligible(
    const NavigationKfGnssReacquireGroupState *state, uint64_t receive_us)
{
    return (uint8_t)((state->outage != 0U) && (state->active != 0U) &&
        (state->loss_latched == 0U) && (state->consistency_start_us != 0U) &&
        (receive_us >= state->consistency_start_us) &&
        (receive_us - state->consistency_start_us >= NAV_KF_REANCHOR_MIN_CONSISTENCY_US) &&
        (state->consistent_count >= SYSTEM_ESTIMATOR_GNSS_REACQUIRE_CONSISTENT_COUNT) &&
        (state->inflation_attempt_count >= SYSTEM_ESTIMATOR_GNSS_REACQUIRE_MAX_ATTEMPTS) &&
        (state->epochs_since_inflation >= SYSTEM_ESTIMATOR_GNSS_REACQUIRE_INFLATION_INTERVAL_SAMPLES));
}

static uint8_t NavigationKf_ReanchorCovarianceValid(const NavigationKfContext *context)
{
    float lower[NAV_KF_STATE_DIMENSION][NAV_KF_STATE_DIMENSION] = {{0.0f}};
    uint8_t row;
    uint8_t column;
    uint8_t inner;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (row = 0U; row < NAV_KF_STATE_DIMENSION; row++)
    {
        for (column = 0U; column <= row; column++)
        {
            float value = context->covariance[row][column];
            if (value != context->covariance[column][row]) { return 0U; }
            for (inner = 0U; inner < column; inner++)
            { value -= lower[row][inner] * lower[column][inner]; }
            if (!isfinite(value)) { return 0U; }
            if (row == column)
            {
                if (value <= 0.0f) { return 0U; }
                lower[row][column] = sqrtf(value);
            }
            else { lower[row][column] = value / lower[column][column]; }
        }
    }
    return 1U;
}

static uint8_t NavigationKf_GnssReanchorApply(
    NavigationKfContext *context, NavigationKfGnssGroup group,
    const float observation[3], const float variance[3])
{
    uint8_t first;
    uint8_t dimension;
    uint8_t axis;
    uint8_t column;
    float cap;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(observation, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationKf_GnssGroupRangeGet(group, &first, &dimension, &cap);
    if ((NavigationKf_StateAndCovarianceValid(context) == 0U) ||
        (NavigationKf_ReanchorCovarianceValid(context) == 0U)) { return 0U; }
    for (axis = 0U; axis < dimension; axis++)
    {
        uint8_t local_axis = (uint8_t)((first + axis) % 3U);
        if (!isfinite(observation[local_axis]) || !isfinite(variance[local_axis]) ||
            (variance[local_axis] <= 0.0f)) { return 0U; }
    }
    /* Independent positive diagonal block + untouched SPD principal block is SPD.
     * Receiver self-consistency authorizes discarding only this group's cross terms. */
    for (axis = 0U; axis < dimension; axis++)
    {
        uint8_t index = first + axis;
        uint8_t local_axis = index % 3U;
        context->state[index] = observation[local_axis];
        for (column = 0U; column < NAV_KF_STATE_DIMENSION; column++)
        { context->covariance[index][column] = 0.0f; context->covariance[column][index] = 0.0f; }
        context->covariance[index][index] = fmaxf(variance[local_axis], NAV_KF_P_DIAGONAL_MIN);
    }
    return 1U;
}

NavigationKfUpdateResult NavigationKf_GnssGroupRecover(
    NavigationKfContext *context, NavigationKfGnssGroup group,
    NavigationKfUpdateResult result, const float observation[3],
    const float variance[3], uint64_t receive_timestamp_us)
{
    NavigationKfGnssReacquireGroupState *state;
    if ((context == NULL) || (observation == NULL) || (variance == NULL) ||
        (group >= NAV_KF_GNSS_GROUP_COUNT)) { return NAV_KF_UPDATE_REJECTED_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(variance, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationKf_GnssGroupResultProcess(context, group, result);
    state = &context->gnss_reacquisition.group[group];
    if ((result != NAV_KF_UPDATE_REJECTED_NIS) ||
        ((context->gnss_reacquisition.previous_epoch.valid_group_mask &
          NAV_KF_GNSS_GROUP_MASK(group)) == 0U) ||
        (NavigationKf_GnssReanchorEligible(state, receive_timestamp_us) == 0U)) { return result; }
    if (NavigationKf_GnssReanchorApply(context, group, observation, variance) == 0U)
    { return NAV_KF_UPDATE_NUMERIC_ERROR; }
    context->gnss_reacquisition.reanchor_count[group]++;
    state->active = 0U;
    state->outage = 0U;
    state->reject_streak = 0U;
    state->accepted_streak = 0U;
    context->gnss_reacquisition.active_mask &= (uint8_t)~NAV_KF_GNSS_GROUP_MASK(group);
    return NAV_KF_UPDATE_ACCEPTED;
}

void NavigationKf_SetProcessAccelStd(NavigationKfContext *context,
                                     const float accel_std_mps2[3])
{
    if ((context == NULL) ||
        (NavigationKf_IsFiniteVector(accel_std_mps2, 3U) == 0U) ||
        (accel_std_mps2[0] <= 0.0f) ||
        (accel_std_mps2[1] <= 0.0f) ||
        (accel_std_mps2[2] <= 0.0f))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        }
        return;
    }

    memcpy(context->process_accel_std_mps2, accel_std_mps2,
           sizeof(context->process_accel_std_mps2));
}

void NavigationKf_SetBaroStd(NavigationKfContext *context,
                             float altitude_std_m)
{
    if ((context == NULL) || (!isfinite(altitude_std_m)) ||
        (altitude_std_m <= 0.0f))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        }
        return;
    }

    context->baro_std_m = altitude_std_m;
}

void NavigationKf_SetNisThresholds(
    NavigationKfContext *context,
    const float soft_threshold[3],
    const float hard_threshold[3],
    float maximum_r_scale)
{
    uint8_t index;

    if ((context == NULL) ||
        (NavigationKf_IsFiniteVector(soft_threshold, 3U) == 0U) ||
        (NavigationKf_IsFiniteVector(hard_threshold, 3U) == 0U) ||
        (!isfinite(maximum_r_scale)) || (maximum_r_scale < 1.0f))
    {
        if (context != NULL)
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
        }
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(soft_threshold, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(hard_threshold, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 3U; index++)
    {
        if ((soft_threshold[index] <= 0.0f) ||
            (hard_threshold[index] <= soft_threshold[index]))
        {
            context->health_flags |= NAV_KF_HEALTH_INVALID_INPUT;
            return;
        }
    }
    memcpy(context->nis_soft_threshold, soft_threshold,
           sizeof(context->nis_soft_threshold));
    memcpy(context->nis_hard_threshold, hard_threshold,
           sizeof(context->nis_hard_threshold));
    context->nis_max_r_scale = maximum_r_scale;
}
