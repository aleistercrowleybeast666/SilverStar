#include "vector_constraints.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define VECTOR_CONSTRAINTS_NORM_MIN 1.0e-6F
#define VECTOR_CONSTRAINTS_PAIR_SINE_MIN 0.17364818F
#define VECTOR_CONSTRAINTS_MAX_RMS_RAD 0.35F
#define VECTOR_CONSTRAINTS_MEAN_ITERATIONS 24U

static float VectorConstraints_Dot(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static void VectorConstraints_Cross(const float a[3], const float b[3],
    float result[3])
{
    result[0] = a[1] * b[2] - a[2] * b[1];
    result[1] = a[2] * b[0] - a[0] * b[2];
    result[2] = a[0] * b[1] - a[1] * b[0];
}

static uint8_t VectorConstraints_Normalize(float vector[3])
{
    float norm = sqrtf(VectorConstraints_Dot(vector, vector));
    uint8_t axis;
    if ((!isfinite(norm)) || (norm < VECTOR_CONSTRAINTS_NORM_MIN))
    { return 0U; }
    for (axis = 0U; axis < 3U; axis++) { vector[axis] /= norm; }
    return 1U;
}

static uint8_t VectorConstraints_QuaternionNormalize(float q[4])
{
    float norm = sqrtf(q[0] * q[0] + q[1] * q[1] +
        q[2] * q[2] + q[3] * q[3]);
    uint8_t component;
    if ((!isfinite(norm)) || (norm < VECTOR_CONSTRAINTS_NORM_MIN))
    { return 0U; }
    for (component = 0U; component < 4U; component++)
    { q[component] /= norm; }
    if (q[0] < 0.0F)
    {
        for (component = 0U; component < 4U; component++)
        { q[component] = -q[component]; }
    }
    return 1U;
}

static uint8_t VectorConstraints_QuaternionFromMatrix(
    const float matrix[3][3], float q[4])
{
    float trace = matrix[0][0] + matrix[1][1] + matrix[2][2];
    float root;
    if (trace > 0.0F)
    {
        root = sqrtf(trace + 1.0F) * 2.0F;
        q[0] = 0.25F * root;
        q[1] = (matrix[2][1] - matrix[1][2]) / root;
        q[2] = (matrix[0][2] - matrix[2][0]) / root;
        q[3] = (matrix[1][0] - matrix[0][1]) / root;
    }
    else if ((matrix[0][0] > matrix[1][1]) &&
             (matrix[0][0] > matrix[2][2]))
    {
        root = sqrtf(1.0F + matrix[0][0] -
            matrix[1][1] - matrix[2][2]) * 2.0F;
        q[0] = (matrix[2][1] - matrix[1][2]) / root;
        q[1] = 0.25F * root;
        q[2] = (matrix[0][1] + matrix[1][0]) / root;
        q[3] = (matrix[0][2] + matrix[2][0]) / root;
    }
    else if (matrix[1][1] > matrix[2][2])
    {
        root = sqrtf(1.0F + matrix[1][1] -
            matrix[0][0] - matrix[2][2]) * 2.0F;
        q[0] = (matrix[0][2] - matrix[2][0]) / root;
        q[1] = (matrix[0][1] + matrix[1][0]) / root;
        q[2] = 0.25F * root;
        q[3] = (matrix[1][2] + matrix[2][1]) / root;
    }
    else
    {
        root = sqrtf(1.0F + matrix[2][2] -
            matrix[0][0] - matrix[1][1]) * 2.0F;
        q[0] = (matrix[1][0] - matrix[0][1]) / root;
        q[1] = (matrix[0][2] + matrix[2][0]) / root;
        q[2] = (matrix[1][2] + matrix[2][1]) / root;
        q[3] = 0.25F * root;
    }
    return VectorConstraints_QuaternionNormalize(q);
}

static uint8_t VectorConstraints_PairSolve(
    const VectorConstraint *first, const VectorConstraint *second,
    float q[4], float *body_sine, float *navigation_sine)
{
    float body_cross[3];
    float navigation_cross[3];
    float body_third[3];
    float navigation_third[3];
    float matrix[3][3];
    uint8_t row;
    uint8_t column;
    VectorConstraints_Cross(first->body, second->body, body_cross);
    VectorConstraints_Cross(first->navigation, second->navigation,
        navigation_cross);
    *body_sine = sqrtf(VectorConstraints_Dot(body_cross, body_cross));
    *navigation_sine = sqrtf(VectorConstraints_Dot(
        navigation_cross, navigation_cross));
    if ((*body_sine < VECTOR_CONSTRAINTS_PAIR_SINE_MIN) ||
        (*navigation_sine < VECTOR_CONSTRAINTS_PAIR_SINE_MIN))
    { return 0U; }
    (void)VectorConstraints_Normalize(body_cross);
    (void)VectorConstraints_Normalize(navigation_cross);
    VectorConstraints_Cross(first->body, body_cross, body_third);
    VectorConstraints_Cross(first->navigation, navigation_cross,
        navigation_third);
    for (row = 0U; row < 3U; row++)
    {
        for (column = 0U; column < 3U; column++)
        {
            matrix[row][column] =
                first->navigation[row] * first->body[column] +
                navigation_cross[row] * body_cross[column] +
                navigation_third[row] * body_third[column];
        }
    }
    return VectorConstraints_QuaternionFromMatrix(matrix, q);
}

static void VectorConstraints_Rotate(const float q[4],
    const float vector[3], float result[3])
{
    float q_vector[3] = { q[1], q[2], q[3] };
    float cross[3];
    float second[3];
    uint8_t axis;
    VectorConstraints_Cross(q_vector, vector, cross);
    VectorConstraints_Cross(q_vector, cross, second);
    for (axis = 0U; axis < 3U; axis++)
    { result[axis] = vector[axis] + 2.0F *
        (q[0] * cross[axis] + second[axis]); }
}

static uint8_t VectorConstraints_MeanGet(const float covariance[4][4],
    float q[4])
{
    float next[4];
    uint8_t iteration;
    uint8_t row;
    uint8_t column;
    for (iteration = 0U; iteration < VECTOR_CONSTRAINTS_MEAN_ITERATIONS;
         iteration++)
    {
        for (row = 0U; row < 4U; row++)
        {
            next[row] = 0.0F;
            for (column = 0U; column < 4U; column++)
            { next[row] += covariance[row][column] * q[column]; }
        }
        if (VectorConstraints_QuaternionNormalize(next) == 0U)
        { return 0U; }
        (void)memcpy(q, next, sizeof(next));
    }
    return 1U;
}

VectorConstraintsSolveResult VectorConstraints_Solve(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraintsSolution *solution)
{
    VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT];
    float covariance[4][4] = {{0.0F}};
    float strongest[4] = {1.0F, 0.0F, 0.0F, 0.0F};
    float strongest_weight = 0.0F;
    float total_error = 0.0F;
    float total_weight = 0.0F;
    uint8_t first;
    uint8_t second;
    uint8_t row;
    uint8_t column;
    if ((constraints == NULL) || (solution == NULL) ||
        (count < 2U) || (count > VECTOR_CONSTRAINTS_MAX_COUNT))
    { return VectorConstraintsSolveInvalidArgument; }
    (void)memset(solution, 0, sizeof(*solution));
    for (first = 0U; first < VECTOR_CONSTRAINTS_MAX_COUNT; first++)
    {
        if (first >= count) { break; }
        normalized[first] = constraints[first];
        if ((!isfinite(normalized[first].weight)) ||
            (normalized[first].weight <= 0.0F) ||
            (normalized[first].weight > 1000000.0F) ||
            (VectorConstraints_Normalize(normalized[first].body) == 0U) ||
            (VectorConstraints_Normalize(normalized[first].navigation) == 0U))
        { return VectorConstraintsSolveInvalidArgument; }
    }
    solution->minimum_pair_sine = 1.0F;
    for (first = 0U; first < VECTOR_CONSTRAINTS_MAX_COUNT; first++)
    {
        if (first >= count) { break; }
        for (second = (uint8_t)(first + 1U);
             second < VECTOR_CONSTRAINTS_MAX_COUNT; second++)
        {
            float q[4];
            float body_sine;
            float navigation_sine;
            float weight;
            if (second >= count) { break; }
            if (VectorConstraints_PairSolve(&normalized[first],
                    &normalized[second], q, &body_sine,
                    &navigation_sine) == 0U)
            { continue; }
            weight = normalized[first].weight *
                normalized[second].weight *
                body_sine * body_sine *
                navigation_sine * navigation_sine;
            if ((!isfinite(weight)) || (weight <= 0.0F))
            { return VectorConstraintsSolveInvalidArgument; }
            if (weight > strongest_weight)
            {
                strongest_weight = weight;
                (void)memcpy(strongest, q, sizeof(strongest));
            }
            for (row = 0U; row < 4U; row++)
            {
                for (column = 0U; column < 4U; column++)
                { covariance[row][column] += weight * q[row] * q[column]; }
            }
            if (body_sine < solution->minimum_pair_sine)
            { solution->minimum_pair_sine = body_sine; }
            if (navigation_sine < solution->minimum_pair_sine)
            { solution->minimum_pair_sine = navigation_sine; }
            solution->valid_pair_count++;
        }
    }
    if (solution->valid_pair_count == 0U)
    { return VectorConstraintsSolveDegenerate; }
    (void)memcpy(solution->q_nb, strongest, sizeof(strongest));
    if ((count > 2U) &&
        (VectorConstraints_MeanGet(covariance, solution->q_nb) == 0U))
    { return VectorConstraintsSolveDegenerate; }
    for (first = 0U; first < VECTOR_CONSTRAINTS_MAX_COUNT; first++)
    {
        float rotated[3];
        float dot;
        float error;
        if (first >= count) { break; }
        VectorConstraints_Rotate(solution->q_nb,
            normalized[first].body, rotated);
        dot = VectorConstraints_Dot(rotated, normalized[first].navigation);
        if (dot > 1.0F) { dot = 1.0F; }
        if (dot < -1.0F) { dot = -1.0F; }
        error = acosf(dot);
        total_error += normalized[first].weight * error * error;
        total_weight += normalized[first].weight;
        if (error > solution->max_mismatch_rad)
        { solution->max_mismatch_rad = error; }
    }
    solution->rms_mismatch_rad = sqrtf(total_error / total_weight);
    if (!isfinite(solution->rms_mismatch_rad))
    { return VectorConstraintsSolveInvalidArgument; }
    if (solution->rms_mismatch_rad > VECTOR_CONSTRAINTS_MAX_RMS_RAD)
    { return VectorConstraintsSolveInconsistent; }
    return VectorConstraintsSolveOk;
}
