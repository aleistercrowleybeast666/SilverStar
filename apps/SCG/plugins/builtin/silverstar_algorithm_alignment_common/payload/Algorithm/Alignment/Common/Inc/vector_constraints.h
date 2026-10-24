#ifndef __VECTOR_CONSTRAINTS_H
#define __VECTOR_CONSTRAINTS_H

#include <stdint.h>

#define VECTOR_CONSTRAINTS_MAX_COUNT 6U
#define VECTOR_CONSTRAINTS_MAX_PAIRS 15U

typedef struct
{
    float body[3];
    float navigation[3];
    float weight;
} VectorConstraint;

typedef enum
{
    VectorConstraintsSolveOk = 0,
    VectorConstraintsSolveInvalidArgument,
    VectorConstraintsSolveDegenerate,
    VectorConstraintsSolveInconsistent
} VectorConstraintsSolveResult;

typedef struct
{
    float q_nb[4];
    float rms_mismatch_rad;
    float max_mismatch_rad;
    float minimum_pair_sine;
    uint8_t valid_pair_count;
} VectorConstraintsSolution;

/* Weighted least squares on DIRECTIONS: each input vector is normalized.
 * q_nb is scalar-first (w,x,y,z), right handed, and maps body to navigation.
 * The arrays, counts and result enum retain the existing API.
 * Success requires >= 1 pair separated by >= 10 degrees in both frames,
 * a numerically rank-two cross-covariance and a unique proper rotation.
 * Degenerate also reports bounded SVD nonconvergence/failed numerical checks;
 * Inconsistent reports reflection ambiguity or weighted RMS > 0.35 rad.
 * On any failure, a non-null solution is zeroed and has no usable quaternion.
 * No heap, shared mutable state, or outer attitude iteration is used.
 */
VectorConstraintsSolveResult VectorConstraints_Solve(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraintsSolution *solution);

#endif /* __VECTOR_CONSTRAINTS_H */
