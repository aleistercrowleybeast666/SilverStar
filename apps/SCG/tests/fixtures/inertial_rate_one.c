#include <stdint.h>
#include <string.h>

#include "ins_mechanization.h"

int main(void)
{
    InsInertialContext context;
    InsAlgorithmSample sample = {0};
    InsState state;
    uint16_t index;
    uint16_t ready_count = 0U;

    InsInertial_Reset(&context);
    sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample.accel_b_mps2[2] = 9.78f;
    for (index = 0U; index <= 400U; index++)
    {
        sample.timestamp_us = 1000000ULL + ((uint64_t)index * 5000ULL);
        if (InsInertial_Update(&context, &sample, &state) ==
            INS_INERTIAL_UPDATE_READY)
        {
            ready_count++;
            if (state.interval_start_timestamp_us !=
                sample.timestamp_us - 5000ULL ||
                state.dt_s < 0.0049f || state.dt_s > 0.0051f)
            {
                return 1;
            }
        }
    }
    if (ready_count != 400U) { return 2; }
    /* A missing interval is rejected, never filled with a synthetic sample. */
    sample.timestamp_us += 100000ULL;
    if (InsInertial_Update(&context, &sample, &state) !=
        INS_INERTIAL_UPDATE_INVALID)
    {
        return 3;
    }
    sample.timestamp_us += 5000ULL;
    if (InsInertial_Update(&context, &sample, &state) !=
        INS_INERTIAL_UPDATE_READY)
    {
        return 4;
    }
    return 0;
}
