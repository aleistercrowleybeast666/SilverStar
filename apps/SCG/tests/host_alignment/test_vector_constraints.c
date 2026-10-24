#include "vector_constraints.h"

#include <assert.h>
#include <math.h>
#include <float.h>
#include <stdio.h>
#include <string.h>

static void TestVectorConstraints_Rotate(const float q[4],
    const float v[3], float out[3])
{
    const float w = q[0], x = q[1], y = q[2], z = q[3];
    out[0] = (1.0F - 2.0F * (y*y + z*z))*v[0] +
        2.0F*(x*y - w*z)*v[1] + 2.0F*(x*z + w*y)*v[2];
    out[1] = 2.0F*(x*y + w*z)*v[0] +
        (1.0F - 2.0F * (x*x + z*z))*v[1] + 2.0F*(y*z - w*x)*v[2];
    out[2] = 2.0F*(x*z - w*y)*v[0] + 2.0F*(y*z + w*x)*v[1] +
        (1.0F - 2.0F * (x*x + y*y))*v[2];
}

static void TestVectorConstraints_ProperRotation(const float q[4])
{
    float columns[3][3];
    float determinant;
    unsigned int row;
    unsigned int column;
    for (column = 0U; column < 3U; column++)
    {
        float basis[3] = {0};
        basis[column] = 1.0F;
        TestVectorConstraints_Rotate(q, basis, columns[column]);
    }
    for (row = 0U; row < 3U; row++)
    {
        for (column = 0U; column < 3U; column++)
        {
            float dot = 0.0F;
            unsigned int k;
            for (k = 0U; k < 3U; k++)
            { dot += columns[row][k] * columns[column][k]; }
            assert(fabsf(dot - ((row == column) ? 1.0F : 0.0F)) < 3.0e-6F);
        }
    }
    determinant =
        columns[0][0]*(columns[1][1]*columns[2][2] - columns[1][2]*columns[2][1]) -
        columns[1][0]*(columns[0][1]*columns[2][2] - columns[0][2]*columns[2][1]) +
        columns[2][0]*(columns[0][1]*columns[1][2] - columns[0][2]*columns[1][1]);
    assert(fabsf(determinant - 1.0F) < 3.0e-6F);
}

static void TestVectorConstraints_KnownRotations(void)
{
    const float rotations[][4] = {
        {1.0F, 0.0F, 0.0F, 0.0F},
        {0.0F, 1.0F, 0.0F, 0.0F},
        {0.0F, 0.0F, 1.0F, 0.0F},
        {0.0F, 0.0F, 0.0F, 1.0F},
        {0.5F, -0.5F, 0.5F, 0.5F},
        {0.000001F, 0.577350269F, -0.577350269F, 0.577350269F}
    };
    const float directions[6][3] = {
        {1.0F, 0.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, {0.0F, 0.0F, 1.0F},
        {0.6F, 0.8F, 0.0F}, {-0.8F, 0.0F, 0.6F}, {0.0F, -0.6F, 0.8F}
    };
    unsigned int rotation;
    uint8_t count;
    for (rotation = 0U; rotation < sizeof(rotations)/sizeof(rotations[0]); rotation++)
    {
        for (count = 2U; count <= 6U; count++)
        {
            VectorConstraint constraints[6] = {0};
            VectorConstraint original[6];
            VectorConstraintsSolution solution;
            float dot = 0.0F;
            unsigned int i;
            for (i = 0U; i < count; i++)
            {
                (void)memcpy(constraints[i].body, directions[i], sizeof(directions[i]));
                TestVectorConstraints_Rotate(rotations[rotation],
                    directions[i], constraints[i].navigation);
                constraints[i].weight = 0.25F + (float)i;
            }
            (void)memcpy(original, constraints, sizeof(original));
            assert(VectorConstraints_Solve(constraints, count, &solution) ==
                VectorConstraintsSolveOk);
            assert(memcmp(original, constraints, sizeof(original)) == 0);
            for (i = 0U; i < 4U; i++)
            { dot += rotations[rotation][i] * solution.q_nb[i]; }
            assert(fabsf(dot) > 0.999999F);
            assert(solution.rms_mismatch_rad < 0.001F);
            TestVectorConstraints_ProperRotation(solution.q_nb);
        }
    }
}

static void TestVectorConstraints_FailureClears(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraintsSolveResult expected)
{
    VectorConstraintsSolution solution;
    const VectorConstraintsSolution zero = {0};
    (void)memset(&solution, 0x5a, sizeof(solution));
    assert(VectorConstraints_Solve(constraints, count, &solution) == expected);
    assert(memcmp(&solution, &zero, sizeof(solution)) == 0);
}

static void TestVectorConstraints_InvalidAndGeometry(void)
{
    const VectorConstraint original[2] = {
        {{1.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F}, 1.0F},
        {{0.0F, 1.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, 1.0F}
    };
    const float invalid_weights[] = {0.0F, -1.0F, NAN, INFINITY, 1000001.0F};
    const float invalid_vectors[] = {0.0F, 1.0e-8F, NAN, INFINITY, FLT_MAX};
    VectorConstraint constraints[2];
    unsigned int i;
    for (i = 0U; i < sizeof(invalid_weights)/sizeof(invalid_weights[0]); i++)
    {
        (void)memcpy(constraints, original, sizeof(constraints));
        constraints[0].weight = invalid_weights[i];
        TestVectorConstraints_FailureClears(constraints, 2U,
            VectorConstraintsSolveInvalidArgument);
    }
    for (i = 0U; i < sizeof(invalid_vectors)/sizeof(invalid_vectors[0]); i++)
    {
        (void)memcpy(constraints, original, sizeof(constraints));
        constraints[0].body[0] = invalid_vectors[i];
        TestVectorConstraints_FailureClears(constraints, 2U,
            VectorConstraintsSolveInvalidArgument);
        (void)memcpy(constraints, original, sizeof(constraints));
        constraints[0].navigation[0] = invalid_vectors[i];
        TestVectorConstraints_FailureClears(constraints, 2U,
            VectorConstraintsSolveInvalidArgument);
    }
    TestVectorConstraints_FailureClears(NULL, 2U, VectorConstraintsSolveInvalidArgument);
    TestVectorConstraints_FailureClears(original, 0U, VectorConstraintsSolveInvalidArgument);
    TestVectorConstraints_FailureClears(original, 1U, VectorConstraintsSolveInvalidArgument);
    TestVectorConstraints_FailureClears(original, 7U, VectorConstraintsSolveInvalidArgument);
    TestVectorConstraints_FailureClears(original, 255U, VectorConstraintsSolveInvalidArgument);
    assert(VectorConstraints_Solve(original, 2U, NULL) == VectorConstraintsSolveInvalidArgument);
    (void)memcpy(constraints, original, sizeof(constraints));
    (void)memcpy(constraints[1].body, constraints[0].body, sizeof(constraints[0].body));
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
    constraints[1].body[0] = -1.0F;
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
    constraints[1].body[1] = 0.001F;
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
    (void)memcpy(constraints, original, sizeof(constraints));
    (void)memcpy(constraints[1].navigation, constraints[0].navigation,
        sizeof(constraints[0].navigation));
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
    (void)memcpy(constraints, original, sizeof(constraints));
    constraints[1].weight = 1.0e-8F;
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
}

static void TestVectorConstraints_Reflection(void)
{
    VectorConstraint constraints[3] = {
        {{1.0F, 0.0F, 0.0F}, {-1.0F, 0.0F, 0.0F}, 0.001F},
        {{0.0F, 1.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, 3.0F},
        {{0.0F, 0.0F, 1.0F}, {0.0F, 0.0F, 1.0F}, 2.0F}
    };
    VectorConstraintsSolution solution;
    assert(VectorConstraints_Solve(constraints, 3U, &solution) == VectorConstraintsSolveOk);
    assert(fabsf(solution.q_nb[0] - 1.0F) < 1.0e-6F);
    assert(solution.max_mismatch_rad > 3.14F);
    TestVectorConstraints_ProperRotation(solution.q_nb);
    constraints[0].weight = 2.0F; /* sigma_2 == sigma_3, no unique proper rotation. */
    TestVectorConstraints_FailureClears(constraints, 3U, VectorConstraintsSolveInconsistent);
    constraints[0].weight = 2.000001F; /* Also reject a float-ill-conditioned gap. */
    TestVectorConstraints_FailureClears(constraints, 3U, VectorConstraintsSolveInconsistent);
    constraints[0].weight = 1.0F;
    constraints[1].weight = 1.0F;
    constraints[2].weight = 1.0F;
    TestVectorConstraints_FailureClears(constraints, 3U, VectorConstraintsSolveInconsistent);
}

static void TestVectorConstraints_CrossCovarianceRank(void)
{
    VectorConstraint constraints[6] = {0};
    VectorConstraintsSolution solution;
    unsigned int axis;
    for (axis = 0U; axis < 3U; axis++)
    {
        constraints[2U * axis].body[axis] = 1.0F;
        constraints[2U * axis + 1U].body[axis] = -1.0F;
        constraints[2U * axis].navigation[axis] = 1.0F;
        constraints[2U * axis + 1U].navigation[axis] = 1.0F;
        constraints[2U * axis].weight = 1.0F;
        constraints[2U * axis + 1U].weight = 1.0F;
    }
    /* Both frames contain well separated pairs but A has rank zero, then one. */
    TestVectorConstraints_FailureClears(constraints, 6U, VectorConstraintsSolveDegenerate);
    constraints[1].navigation[0] = -1.0F;
    TestVectorConstraints_FailureClears(constraints, 6U, VectorConstraintsSolveDegenerate);
    (void)memset(constraints, 0, sizeof(constraints));
    constraints[0].body[0] = constraints[0].navigation[0] = 1.0F;
    constraints[0].weight = constraints[1].weight = 1000000.0F;
    constraints[1].body[0] = constraints[1].navigation[0] = cosf(0.15707963F);
    constraints[1].body[1] = constraints[1].navigation[1] = sinf(0.15707963F);
    TestVectorConstraints_FailureClears(constraints, 2U, VectorConstraintsSolveDegenerate);
    constraints[1].body[0] = constraints[1].navigation[0] = cosf(0.19198622F);
    constraints[1].body[1] = constraints[1].navigation[1] = sinf(0.19198622F);
    assert(VectorConstraints_Solve(constraints, 2U, &solution) == VectorConstraintsSolveOk);
    assert(solution.valid_pair_count == 1U);
    TestVectorConstraints_ProperRotation(solution.q_nb);
}

static void TestVectorConstraints_WeightAndMagnitudeScale(void)
{
    VectorConstraint constraints[3] = {
        {{2.0F, 0.0F, 0.0F}, {0.0F, 3.0F, 0.0F}, 1.0e-25F},
        {{0.0F, 0.001F, 0.0F}, {-1000.0F, 0.0F, 0.0F}, 2.0e-25F},
        {{0.0F, 0.0F, 50.0F}, {0.0F, 0.0F, 0.01F}, 3.0e-25F}
    };
    VectorConstraintsSolution tiny;
    VectorConstraintsSolution large;
    unsigned int i;
    assert(VectorConstraints_Solve(constraints, 3U, &tiny) == VectorConstraintsSolveOk);
    for (i = 0U; i < 3U; i++) { constraints[i].weight = 1000.0F * (float)(i + 1U); }
    assert(VectorConstraints_Solve(constraints, 3U, &large) == VectorConstraintsSolveOk);
    for (i = 0U; i < 4U; i++) { assert(fabsf(tiny.q_nb[i] - large.q_nb[i]) < 1.0e-6F); }
    assert(fabsf(tiny.q_nb[0] - 0.70710678F) < 1.0e-6F);
    assert(fabsf(tiny.q_nb[3] - 0.70710678F) < 1.0e-6F);
}

/* Independent planar least-squares solution; TRIAD incorrectly pins vector 0. */
static void TestVectorConstraints_WeightedNoisyPair(void)
{
    const float first = 0.20F;
    const float second = -0.10F;
    const float expected = atan2f(sinf(first) + 3.0F * sinf(second),
        cosf(first) + 3.0F * cosf(second));
    const VectorConstraint constraints[2] = {
        {{1.0F, 0.0F, 0.0F}, {cosf(first), sinf(first), 0.0F}, 1.0F},
        {{0.0F, 1.0F, 0.0F}, {-sinf(second), cosf(second), 0.0F}, 3.0F}
    };
    VectorConstraintsSolution solution;
    assert(VectorConstraints_Solve(constraints, 2U, &solution) ==
        VectorConstraintsSolveOk);
    (void)printf("weighted noisy pair: expected=%.9f actual=%.9f rad\n",
        (double)expected,
        (double)(2.0F * atan2f(solution.q_nb[3], solution.q_nb[0])));
    (void)fflush(stdout);
    assert(fabsf(2.0F * atan2f(solution.q_nb[3], solution.q_nb[0]) -
        expected) < 2.0e-5F);
}

static void TestVectorConstraints_WeightedNoisyMulti(void)
{
    const float deviations[6] = {0.10F, -0.05F, 0.02F, -0.08F, 0.12F, 0.04F};
    uint8_t count;
    for (count = 3U; count <= 6U; count++)
    {
        VectorConstraint constraints[6] = {0};
        VectorConstraint reversed[6] = {0};
        VectorConstraintsSolution solution;
        VectorConstraintsSolution reordered;
        float sine_sum = 0.0F;
        float cosine_sum = 0.0F;
        float expected;
        float squared_error = 0.0F;
        float weight_sum = 0.0F;
        unsigned int i;
        for (i = 0U; i < count; i++)
        {
            float angle = 0.7F * (float)i;
            constraints[i].body[0] = cosf(angle);
            constraints[i].body[1] = sinf(angle);
            constraints[i].navigation[0] = cosf(angle + deviations[i]);
            constraints[i].navigation[1] = sinf(angle + deviations[i]);
            constraints[i].weight = 0.5F + (float)i;
            sine_sum += constraints[i].weight * sinf(deviations[i]);
            cosine_sum += constraints[i].weight * cosf(deviations[i]);
            weight_sum += constraints[i].weight;
            reversed[(unsigned int)count - 1U - i] = constraints[i];
        }
        expected = atan2f(sine_sum, cosine_sum);
        for (i = 0U; i < count; i++)
        {
            float error = deviations[i] - expected;
            squared_error += constraints[i].weight * error * error;
        }
        assert(VectorConstraints_Solve(constraints, count, &solution) ==
            VectorConstraintsSolveOk);
        assert(VectorConstraints_Solve(reversed, count, &reordered) ==
            VectorConstraintsSolveOk);
        assert(fabsf(2.0F * atan2f(solution.q_nb[3], solution.q_nb[0]) -
            expected) < 2.0e-5F);
        assert(fabsf(solution.rms_mismatch_rad -
            sqrtf(squared_error / weight_sum)) < 2.0e-5F);
        for (i = 0U; i < 4U; i++)
        { assert(fabsf(solution.q_nb[i] - reordered.q_nb[i]) < 2.0e-5F); }
        TestVectorConstraints_ProperRotation(solution.q_nb);
    }
}

static void TestVectorConstraints_TriadYaw(void)
{
    const VectorConstraint constraints[2] = {
        {{1.0F, 0.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, 1.0F},
        {{0.0F, 1.0F, 0.0F}, {-1.0F, 0.0F, 0.0F}, 1.0F}
    };
    VectorConstraintsSolution solution;
    assert(VectorConstraints_Solve(constraints, 2U, &solution) ==
        VectorConstraintsSolveOk);
    assert(solution.valid_pair_count == 1U);
    assert(fabsf(solution.q_nb[0] - 0.70710678F) < 0.0001F);
    assert(fabsf(solution.q_nb[3] - 0.70710678F) < 0.0001F);
    assert(solution.rms_mismatch_rad < 0.001F);
}

static void TestVectorConstraints_MultiVectorMean(void)
{
    const VectorConstraint constraints[3] = {
        {{1.0F, 0.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, 2.0F},
        {{0.0F, 1.0F, 0.0F}, {-1.0F, 0.0F, 0.0F}, 1.0F},
        {{0.0F, 0.0F, 1.0F}, {0.0F, 0.0F, 1.0F}, 1.0F}
    };
    VectorConstraintsSolution solution;
    assert(VectorConstraints_Solve(constraints, 3U, &solution) ==
        VectorConstraintsSolveOk);
    assert(solution.valid_pair_count == 3U);
    assert(fabsf(solution.q_nb[0] - 0.70710678F) < 0.0001F);
    assert(fabsf(solution.q_nb[3] - 0.70710678F) < 0.0001F);
    assert(solution.rms_mismatch_rad < 0.001F);
}

static void TestVectorConstraints_Rejection(void)
{
    const VectorConstraint collinear[2] = {
        {{1.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F}, 1.0F},
        {{1.0F, 0.001F, 0.0F}, {1.0F, 0.001F, 0.0F}, 1.0F}
    };
    const VectorConstraint contradictory[3] = {
        {{1.0F, 0.0F, 0.0F}, {1.0F, 0.0F, 0.0F}, 1.0F},
        {{0.0F, 1.0F, 0.0F}, {0.0F, 1.0F, 0.0F}, 1.0F},
        {{0.0F, 0.0F, 1.0F}, {0.0F, 0.0F, -1.0F}, 1.0F}
    };
    VectorConstraintsSolution solution;
    assert(VectorConstraints_Solve(collinear, 2U, &solution) ==
        VectorConstraintsSolveDegenerate);
    assert(VectorConstraints_Solve(contradictory, 3U, &solution) ==
        VectorConstraintsSolveInconsistent);
    assert(VectorConstraints_Solve(contradictory, 7U, &solution) ==
        VectorConstraintsSolveInvalidArgument);
}

int main(void)
{
    TestVectorConstraints_TriadYaw();
    TestVectorConstraints_MultiVectorMean();
    TestVectorConstraints_Rejection();
    TestVectorConstraints_WeightedNoisyPair();
    TestVectorConstraints_WeightedNoisyMulti();
    TestVectorConstraints_KnownRotations();
    TestVectorConstraints_InvalidAndGeometry();
    TestVectorConstraints_Reflection();
    TestVectorConstraints_CrossCovarianceRank();
    TestVectorConstraints_WeightAndMagnitudeScale();
    (void)puts("vector SVD: known rotations/counts/weights/noise/geometry/invalid/SO3 PASS");
    return 0;
}
