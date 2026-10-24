#include "vector_constraints.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define VECTOR_CONSTRAINTS_NORM_MIN 1.0e-6F
#define VECTOR_CONSTRAINTS_PAIR_SINE_MIN 0.17364818F
#define VECTOR_CONSTRAINTS_MAX_RMS_RAD 0.35F
#define VECTOR_CONSTRAINTS_SVD_SWEEPS 16U
#define VECTOR_CONSTRAINTS_SVD_TOLERANCE 1.0e-6F
#define VECTOR_CONSTRAINTS_RANK_TOLERANCE 1.0e-5F
#define VECTOR_CONSTRAINTS_ORTHOGONAL_TOLERANCE 2.0e-5F
#define VECTOR_CONSTRAINTS_COLUMN_ZERO_SQUARED 1.0e-14F

/* Column-major work arrays: left = A * right. No heap or shared state. */
typedef struct
{
    float left[3][3];
    float right[3][3];
    float singular[3];
} VectorConstraintsSvd;

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
    float matrix[3][3], float q[4])
{
    float trace;
    float root;
    SILVERSTAR_ASSERT(matrix != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(q != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2];
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

static uint8_t VectorConstraints_InputsNormalize(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT])
{
    float maximum_weight = 0.0F;
    float total_weight = 0.0F;
    uint8_t index;
    SILVERSTAR_ASSERT((count >= 2U) && (count <= VECTOR_CONSTRAINTS_MAX_COUNT),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U; index < VECTOR_CONSTRAINTS_MAX_COUNT; index++)
    {
        if (index >= count) { break; }
        normalized[index] = constraints[index];
        if ((!isfinite(normalized[index].weight)) ||
            (normalized[index].weight <= 0.0F) ||
            (normalized[index].weight > 1000000.0F) ||
            (VectorConstraints_Normalize(normalized[index].body) == 0U) ||
            (VectorConstraints_Normalize(normalized[index].navigation) == 0U))
        { return 0U; }
        if (normalized[index].weight > maximum_weight)
        { maximum_weight = normalized[index].weight; }
    }
    /* Scaling by the maximum first also handles uniformly tiny weights. */
    for (index = 0U; index < VECTOR_CONSTRAINTS_MAX_COUNT; index++)
    {
        if (index >= count) { break; }
        normalized[index].weight /= maximum_weight;
        total_weight += normalized[index].weight;
    }
    SILVERSTAR_ASSERT(isfinite(total_weight) && (total_weight >= 1.0F),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (index = 0U; index < VECTOR_CONSTRAINTS_MAX_COUNT; index++)
    {
        if (index >= count) { break; }
        normalized[index].weight /= total_weight;
    }
    return 1U;
}

static uint8_t VectorConstraints_GeometryEvaluate(
    const VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT],
    uint8_t count, VectorConstraintsSolution *solution)
{
    uint8_t first;
    uint8_t second;
    SILVERSTAR_ASSERT((count >= 2U) && (count <= VECTOR_CONSTRAINTS_MAX_COUNT),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    solution->minimum_pair_sine = 1.0F;
    for (first = 0U; first < VECTOR_CONSTRAINTS_MAX_COUNT; first++)
    {
        if (first >= count) { break; }
        for (second = (uint8_t)(first + 1U);
             second < VECTOR_CONSTRAINTS_MAX_COUNT; second++)
        {
            float cross[3];
            float body_sine;
            float navigation_sine;
            if (second >= count) { break; }
            VectorConstraints_Cross(normalized[first].body,
                normalized[second].body, cross);
            body_sine = sqrtf(VectorConstraints_Dot(cross, cross));
            VectorConstraints_Cross(normalized[first].navigation,
                normalized[second].navigation, cross);
            navigation_sine = sqrtf(VectorConstraints_Dot(cross, cross));
            if ((body_sine < VECTOR_CONSTRAINTS_PAIR_SINE_MIN) ||
                (navigation_sine < VECTOR_CONSTRAINTS_PAIR_SINE_MIN))
            { continue; }
            if (body_sine < solution->minimum_pair_sine)
            { solution->minimum_pair_sine = body_sine; }
            if (navigation_sine < solution->minimum_pair_sine)
            { solution->minimum_pair_sine = navigation_sine; }
            solution->valid_pair_count++;
        }
    }
    return (uint8_t)(solution->valid_pair_count != 0U);
}

static uint8_t VectorConstraints_MatrixBuild(
    const VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT],
    uint8_t count, VectorConstraintsSvd *svd)
{
    float scale = 0.0F;
    uint8_t index;
    uint8_t row;
    uint8_t column;
    SILVERSTAR_ASSERT((count >= 2U) && (count <= VECTOR_CONSTRAINTS_MAX_COUNT),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (column = 0U; column < 3U; column++)
    {
        svd->right[column][column] = 1.0F;
        for (row = 0U; row < 3U; row++)
        {
            for (index = 0U; index < VECTOR_CONSTRAINTS_MAX_COUNT; index++)
            {
                if (index >= count) { break; }
                svd->left[column][row] += normalized[index].weight *
                    normalized[index].navigation[row] *
                    normalized[index].body[column];
            }
            if (fabsf(svd->left[column][row]) > scale)
            { scale = fabsf(svd->left[column][row]); }
        }
    }
    if ((!isfinite(scale)) || (scale < VECTOR_CONSTRAINTS_NORM_MIN))
    { return 0U; }
    /* A positive common scale preserves its optimal rotation. */
    for (column = 0U; column < 3U; column++)
    {
        for (row = 0U; row < 3U; row++)
        { svd->left[column][row] /= scale; }
    }
    return 1U;
}

static void VectorConstraints_ColumnsRotate(float matrix[3][3],
    uint8_t first, uint8_t second, float cosine, float sine)
{
    uint8_t row;
    SILVERSTAR_ASSERT((first < second) && (second < 3U),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    for (row = 0U; row < 3U; row++)
    {
        float a = matrix[first][row];
        float b = matrix[second][row];
        matrix[first][row] = cosine * a - sine * b;
        matrix[second][row] = sine * a + cosine * b;
    }
}

static uint8_t VectorConstraints_JacobiRotate(VectorConstraintsSvd *svd,
    uint8_t first, uint8_t second)
{
    float alpha;
    float beta;
    float gamma;
    float delta;
    float root;
    float tangent;
    float cosine;
    SILVERSTAR_ASSERT((first < second) && (second < 3U),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    alpha = VectorConstraints_Dot(svd->left[first], svd->left[first]);
    beta = VectorConstraints_Dot(svd->left[second], svd->left[second]);
    gamma = VectorConstraints_Dot(svd->left[first], svd->left[second]);
    SILVERSTAR_ASSERT(isfinite(alpha) && isfinite(beta) && isfinite(gamma),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
    if ((alpha <= VECTOR_CONSTRAINTS_COLUMN_ZERO_SQUARED) ||
        (beta <= VECTOR_CONSTRAINTS_COLUMN_ZERO_SQUARED) ||
        (fabsf(gamma) <= VECTOR_CONSTRAINTS_SVD_TOLERANCE *
            sqrtf(alpha) * sqrtf(beta)))
    { return 0U; }
    delta = beta - alpha;
    root = sqrtf(delta * delta + 4.0F * gamma * gamma);
    /* Stable Jacobi tangent, |t| <= 1; avoid division by a small gamma. */
    tangent = (2.0F * gamma) /
        ((delta >= 0.0F) ? delta + root : delta - root);
    cosine = 1.0F / sqrtf(1.0F + tangent * tangent);
    VectorConstraints_ColumnsRotate(svd->left,
        first, second, cosine, cosine * tangent);
    VectorConstraints_ColumnsRotate(svd->right,
        first, second, cosine, cosine * tangent);
    return 1U;
}

static uint8_t VectorConstraints_SvdDecompose(VectorConstraintsSvd *svd)
{
    uint8_t sweep;
    uint8_t first;
    uint8_t second;
    SILVERSTAR_ASSERT(svd != NULL, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (sweep = 0U; sweep < VECTOR_CONSTRAINTS_SVD_SWEEPS; sweep++)
    {
        uint8_t changed = 0U;
        for (first = 0U; first < 2U; first++)
        {
            for (second = (uint8_t)(first + 1U); second < 3U; second++)
            { changed |= VectorConstraints_JacobiRotate(svd, first, second); }
        }
        /* A whole unchanged sweep verifies all three column correlations. */
        if (changed == 0U) { return 1U; }
    }
    return 0U;
}

static void VectorConstraints_SingularSort(VectorConstraintsSvd *svd)
{
    uint8_t first;
    uint8_t second;
    uint8_t row;
    for (first = 0U; first < 3U; first++)
    {
        svd->singular[first] = sqrtf(VectorConstraints_Dot(
            svd->left[first], svd->left[first]));
    }
    for (first = 0U; first < 2U; first++)
    {
        for (second = (uint8_t)(first + 1U); second < 3U; second++)
        {
            if (svd->singular[first] < svd->singular[second])
            {
                float temporary = svd->singular[first];
                svd->singular[first] = svd->singular[second];
                svd->singular[second] = temporary;
                for (row = 0U; row < 3U; row++)
                {
                    temporary = svd->left[first][row];
                    svd->left[first][row] = svd->left[second][row];
                    svd->left[second][row] = temporary;
                    temporary = svd->right[first][row];
                    svd->right[first][row] = svd->right[second][row];
                    svd->right[second][row] = temporary;
                }
            }
        }
    }
}

static float VectorConstraints_Determinant(float matrix[3][3])
{
    float cross[3];
    VectorConstraints_Cross(matrix[0], matrix[1], cross);
    return VectorConstraints_Dot(cross, matrix[2]);
}

static uint8_t VectorConstraints_BasisComplete(float basis[3][3])
{
    float projection;
    uint8_t row;
    if ((VectorConstraints_Normalize(basis[0]) == 0U) ||
        (VectorConstraints_Normalize(basis[1]) == 0U))
    { return 0U; }
    projection = VectorConstraints_Dot(basis[0], basis[1]);
    if ((!isfinite(projection)) ||
        (fabsf(projection) > VECTOR_CONSTRAINTS_ORTHOGONAL_TOLERANCE))
    { return 0U; }
    /* Remove only roundoff after checking, never repair a failed SVD. */
    for (row = 0U; row < 3U; row++)
    { basis[1][row] -= projection * basis[0][row]; }
    if (VectorConstraints_Normalize(basis[1]) == 0U) { return 0U; }
    VectorConstraints_Cross(basis[0], basis[1], basis[2]);
    return VectorConstraints_Normalize(basis[2]);
}

static uint8_t VectorConstraints_RotationValid(float matrix[3][3])
{
    uint8_t row;
    uint8_t column;
    float determinant = VectorConstraints_Determinant(matrix);
    if ((!isfinite(determinant)) ||
        (fabsf(determinant - 1.0F) > VECTOR_CONSTRAINTS_ORTHOGONAL_TOLERANCE))
    { return 0U; }
    for (row = 0U; row < 3U; row++)
    {
        for (column = row; column < 3U; column++)
        {
            float dot = VectorConstraints_Dot(matrix[row], matrix[column]);
            float expected = (row == column) ? 1.0F : 0.0F;
            if ((!isfinite(dot)) ||
                (fabsf(dot - expected) > VECTOR_CONSTRAINTS_ORTHOGONAL_TOLERANCE))
            { return 0U; }
        }
    }
    return 1U;
}

static VectorConstraintsSolveResult VectorConstraints_RotationBuild(
    VectorConstraintsSvd *svd, float matrix[3][3])
{
    float orientation;
    uint8_t row;
    uint8_t column;
    uint8_t component;
    VectorConstraints_SingularSort(svd);
    if ((!isfinite(svd->singular[0])) ||
        (svd->singular[1] <= VECTOR_CONSTRAINTS_RANK_TOLERANCE *
            svd->singular[0]))
    { return VectorConstraintsSolveDegenerate; }
    orientation = VectorConstraints_Determinant(svd->left) *
        VectorConstraints_Determinant(svd->right);
    if ((orientation < 0.0F) &&
        ((svd->singular[1] - svd->singular[2]) <=
            VECTOR_CONSTRAINTS_RANK_TOLERANCE * svd->singular[0]))
    { return VectorConstraintsSolveInconsistent; }
    /* Completing both bases with cross products gives
     * U diag(1,1,det(U V^T)) V^T, including rank-two input.
     * The sorted third direction is the minimum singular direction. */
    if ((VectorConstraints_BasisComplete(svd->left) == 0U) ||
        (VectorConstraints_BasisComplete(svd->right) == 0U))
    { return VectorConstraintsSolveDegenerate; }
    for (row = 0U; row < 3U; row++)
    {
        for (column = 0U; column < 3U; column++)
        {
            matrix[row][column] = 0.0F;
            for (component = 0U; component < 3U; component++)
            {
                matrix[row][column] += svd->left[component][row] *
                    svd->right[component][column];
            }
        }
    }
    if (VectorConstraints_RotationValid(matrix) == 0U)
    { return VectorConstraintsSolveDegenerate; }
    return VectorConstraintsSolveOk;
}

static VectorConstraintsSolveResult VectorConstraints_MismatchEvaluate(
    const VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT],
    uint8_t count, VectorConstraintsSolution *solution)
{
    float total_error = 0.0F;
    float total_weight = 0.0F;
    uint8_t first;
    SILVERSTAR_ASSERT((count >= 2U) && (count <= VECTOR_CONSTRAINTS_MAX_COUNT),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
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

VectorConstraintsSolveResult VectorConstraints_Solve(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraintsSolution *solution)
{
    VectorConstraint normalized[VECTOR_CONSTRAINTS_MAX_COUNT] = {0};
    VectorConstraintsSvd svd = {0};
    VectorConstraintsSolution candidate = {0};
    float matrix[3][3];
    VectorConstraintsSolveResult result;
    if (solution == NULL) { return VectorConstraintsSolveInvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(solution, VectorConstraintsSolution,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    /* No usable quaternion survives any ordinary failure, including bad input. */
    (void)memset(solution, 0, sizeof(*solution));
    if ((constraints == NULL) ||
        (count < 2U) || (count > VECTOR_CONSTRAINTS_MAX_COUNT))
    { return VectorConstraintsSolveInvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(constraints, VectorConstraint,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (VectorConstraints_InputsNormalize(constraints, count, normalized) == 0U)
    { return VectorConstraintsSolveInvalidArgument; }
    if ((VectorConstraints_GeometryEvaluate(normalized, count, &candidate) == 0U) ||
        (VectorConstraints_MatrixBuild(normalized, count, &svd) == 0U) ||
        (VectorConstraints_SvdDecompose(&svd) == 0U))
    { return VectorConstraintsSolveDegenerate; }
    result = VectorConstraints_RotationBuild(&svd, matrix);
    if (result != VectorConstraintsSolveOk) { return result; }
    if (VectorConstraints_QuaternionFromMatrix(matrix, candidate.q_nb) == 0U)
    { return VectorConstraintsSolveDegenerate; }
    result = VectorConstraints_MismatchEvaluate(normalized, count, &candidate);
    if (result == VectorConstraintsSolveOk) { *solution = candidate; }
    return result;
}