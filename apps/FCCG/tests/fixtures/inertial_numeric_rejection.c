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

static int Test_OverflowAcceleration(void)
{
    InsMechanizationContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    InsMechanization_Init(&context, 9.78f);
    if (InsMechanization_ResetNavigationWithAttitude(&context, q) == 0U) { return 1; }
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    /* Must overflow published acceleration for both 5 ms and 10 ms outputs. */
    sample.gyro_b_radps[0] = 2.0e11f;
    sample.accel_b_mps2[1] = 1.0e30f;
    for (unsigned int index = 0U; index < 3U; index++)
    {
        sample.timestamp_us = 1000000ULL + 5000ULL * index;
        if (InsMechanization_Update(&context, &sample, &output) != 0U) { return 1; }
    }
    return output.valid || context.update_count ||
        memcmp(context.q_nb_propagated, q, sizeof(q)) ||
        context.position_n_m[0] || context.position_n_m[1] || context.position_n_m[2] ||
        context.velocity_n_mps[0] || context.velocity_n_mps[1] || context.velocity_n_mps[2] ||
        !(output.health_flags & INS_HEALTH_INVALID_SAMPLE);
}

static int Test_Recovery(void)
{
    InsInertialContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    unsigned int ready = 0U;
    InsInertial_Reset(&context);
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.accel_b_mps2[2] = 9.78f;
    for (unsigned int index = 0U; index < 24U; index++)
    {
        sample.timestamp_us = 1000000ULL + 5000ULL * index;
        sample.gyro_b_radps[0] = (index == 4U) ? NAN : 0.0f;
        InsInertialUpdateResult result = InsInertial_Update(&context, &sample, &output);
        if (index == 4U && (result != INS_INERTIAL_UPDATE_INVALID || output.valid)) { return 1; }
        if (index > 8U && result == INS_INERTIAL_UPDATE_READY)
        {
            ready++;
            if (!output.valid || !isfinite(output.delta_velocity_b_sculling_corrected[2])) { return 1; }
        }
    }
    return ready == 0U || !(output.health_flags & INS_HEALTH_INVALID_SAMPLE);
}

static int Test_DtBoundaries(uint64_t delta, unsigned int accepted)
{
    InsInertialContext context;
    InsAlgorithmSample sample = {0};
    InsState output;
    InsInertialUpdateResult result = INS_INERTIAL_UPDATE_WAITING;
    InsInertial_Reset(&context);
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.accel_b_mps2[2] = 9.78f;
    for (unsigned int index = 0U; index < 3U; index++)
    {
        sample.timestamp_us = 1000000ULL + delta * index;
        result = InsInertial_Update(&context, &sample, &output);
        if (result != INS_INERTIAL_UPDATE_WAITING) { break; }
    }
    return accepted ? (result != INS_INERTIAL_UPDATE_READY || !output.valid) :
        (result != INS_INERTIAL_UPDATE_INVALID || output.valid ||
         !(output.health_flags & INS_HEALTH_SAMPLE_GAP));
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
    failures += Test_OverflowAcceleration();
    failures += Test_Recovery();
    failures += Test_DtBoundaries(0ULL, 0U);
    failures += Test_DtBoundaries(1ULL, 0U);
    failures += Test_DtBoundaries(5000ULL, 1U);
    failures += Test_DtBoundaries(1000000ULL, 0U);
    /* Current 50..500 Hz / 35% tolerance: one microsecond inside/outside. */
    failures += Test_DtBoundaries(1299ULL, 0U);
    failures += Test_DtBoundaries(1301ULL, 1U);
    failures += Test_DtBoundaries(26999ULL, 1U);
    failures += Test_DtBoundaries(27001ULL, 0U);
    printf("inertial numeric rejection/recovery: cases=17 failures=%d\n", failures);
    return failures != 0;
}
