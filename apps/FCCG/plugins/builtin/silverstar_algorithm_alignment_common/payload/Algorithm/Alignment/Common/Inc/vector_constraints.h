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

VectorConstraintsSolveResult VectorConstraints_Solve(
    const VectorConstraint *constraints, uint8_t count,
    VectorConstraintsSolution *solution);

#endif /* __VECTOR_CONSTRAINTS_H */
