#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "ins_mechanization.h"

static int Test_BadSample(float value, unsigned int gyro)
{
    InsInertialContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    InsInertial_Reset(&context);
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.timestamp_us = 1000000ULL;
    sample.accel_b_mps2[2] = 9.78f;
    if (gyro != 0U) { sample.gyro_b_radps[0] = value; }
    else { sample.accel_b_mps2[0] = value; }
    return (InsInertial_Update(&context, &sample, &output) != INS_INERTIAL_UPDATE_INVALID) ||
        (output.valid != 0U) || (context.sample_count != 0U) ||
        ((output.health_flags & INS_HEALTH_INVALID_SAMPLE) == 0U);
}

static int Test_OverflowIncrement(void)
{
    InsInertialContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    InsInertialUpdateResult result = INS_INERTIAL_UPDATE_WAITING;
    InsInertial_Reset(&context);
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.accel_b_mps2[0] = FLT_MAX;
    sample.accel_b_mps2[2] = 9.78f;
    for (unsigned int index = 0U; index < 3U; index++)
    {
        sample.timestamp_us = 1000000ULL + 5000ULL * index;
        result = InsInertial_Update(&context, &sample, &output);
        if (result != INS_INERTIAL_UPDATE_WAITING) { break; }
    }
    return (result != INS_INERTIAL_UPDATE_INVALID) || (output.valid != 0U) ||
        (context.update_count != 0U) ||
        ((output.health_flags & INS_HEALTH_INVALID_SAMPLE) == 0U);
}

static int Test_NavigationCommit(float gravity, unsigned int overflow)
{
    InsMechanizationContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    float previous_velocity[3];
    float previous_position[3];
    unsigned int ready = 0U;
    InsMechanization_Init(&context, gravity);
    if (InsMechanization_ResetNavigationWithAttitude(&context, q) == 0U) { return 1; }
    if (overflow != 0U)
    {
        context.velocity_n_mps[0] = FLT_MAX;
        context.position_n_m[0] = FLT_MAX;
    }
    memcpy(previous_velocity, context.velocity_n_mps, sizeof(previous_velocity));
    memcpy(previous_position, context.position_n_m, sizeof(previous_position));
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.accel_b_mps2[2] = 9.78f;
    for (unsigned int index = 0U; index < 3U; index++)
    {
        sample.timestamp_us = 1000000ULL + 5000ULL * index;
        ready |= InsMechanization_Update(&context, &sample, &output);
    }
    return (ready != 0U) || (output.valid != 0U) || (context.update_count != 0U) ||
        (memcmp(context.velocity_n_mps, previous_velocity, sizeof(previous_velocity)) != 0) ||
        (memcmp(context.position_n_m, previous_position, sizeof(previous_position)) != 0) ||
        (memcmp(context.q_nb_propagated, q, sizeof(q)) != 0) ||
        ((output.health_flags & INS_HEALTH_INVALID_SAMPLE) == 0U);
}

int main(void)
{
    int failures = 0;
    failures += Test_BadSample(NAN, 0U);
    failures += Test_BadSample(INFINITY, 0U);
    failures += Test_BadSample(NAN, 1U);
    failures += Test_BadSample(-INFINITY, 1U);
    failures += Test_OverflowIncrement();
    failures += Test_NavigationCommit(NAN, 0U);
    failures += Test_NavigationCommit(9.78f, 1U);
    printf("inertial numeric rejection: cases=7 failures=%d\n", failures);
    return failures != 0;
}
