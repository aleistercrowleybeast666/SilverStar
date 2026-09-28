#include <math.h>
#include <string.h>
#include "ins_mechanization.h"

int main(void)
{
    InsInertialContext frontend;
    InsMechanizationContext navigation;
    InsAlgorithmSample sample = {0};
    InsState increment;
    InsState state;
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    unsigned int index;
    unsigned int count = 0;
    InsInertial_Reset(&frontend);
    InsMechanization_Init(&navigation, 9.78f);
    if (InsMechanization_ResetNavigationWithAttitude(&navigation, q) == 0) { return 1; }
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    for (index = 0; index < 2001; index++)
    {
        sample.timestamp_us = 1234567ULL + (uint64_t)index * 5000ULL;
        sample.gyro_b_radps[0] = (float)(index % 13) * 0.003f;
        sample.gyro_b_radps[1] = (float)(index % 17) * -0.002f;
        sample.accel_b_mps2[0] = (float)(index % 11) * 0.13f;
        sample.accel_b_mps2[2] = 9.78f;
        /* An increment generator has no dependency on attitude initialization. */
        sample.q_nb[0] = NAN;
        InsInertialUpdateResult result = InsInertial_Update(&frontend, &sample, &increment);
        unsigned int ready = InsMechanization_Update(&navigation, &sample, &state);
        if ((result == INS_INERTIAL_UPDATE_READY) != (ready != 0)) { return 2; }
        if (ready != 0)
        {
            count++;
            if (increment.interval_start_timestamp_us != sample.timestamp_us - 10000ULL ||
                increment.timestamp_us != sample.timestamp_us || increment.dt_s != state.dt_s ||
                memcmp(increment.delta_theta_b_coning_corrected,
                       state.delta_theta_b_coning_corrected, sizeof(state.delta_theta_b)) ||
                memcmp(increment.delta_velocity_b_sculling_corrected,
                       state.delta_velocity_b_sculling_corrected, sizeof(state.delta_velocity_b)))
            { return 3; }
            if (increment.position_n_m[0] != 0 || increment.velocity_n_mps[0] != 0 ||
                increment.q_nb[0] != 0) { return 4; }
        }
    }
    if (count != 1000 || state.position_n_m[0] == 0) { return 5; }
    /* A gap restarts sample grouping and must not integrate the missing time. */
    sample.timestamp_us += 1000000;
    if (InsInertial_Update(&frontend, &sample, &increment) != INS_INERTIAL_UPDATE_WAITING)
    { return 6; }
    sample.timestamp_us += 5000;
    if (InsInertial_Update(&frontend, &sample, &increment) != INS_INERTIAL_UPDATE_INVALID ||
        (increment.health_flags & INS_HEALTH_SAMPLE_GAP) == 0) { return 7; }
    sample.timestamp_us += 5000;
    (void)InsInertial_Update(&frontend, &sample, &increment);
    sample.timestamp_us += 5000;
    if (InsInertial_Update(&frontend, &sample, &increment) != INS_INERTIAL_UPDATE_READY ||
        increment.interval_start_timestamp_us != sample.timestamp_us - 10000) { return 8; }
    return 0;
}
