#include "vector_constraints.h"

#include <assert.h>
#include <math.h>

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
    return 0;
}
