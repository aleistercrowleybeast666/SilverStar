/* Raw IMU input fixture: the actual task and selected alignment strategy compute
 * their own windows, quaternion, readiness, freeze and mission initialization. */
#include "../../APP/Src/ins_task.c"
#include "optional_start_inputs.h"

void Test_InsInputFeed(uint64_t timestamp_us, uint32_t sequence)
{
    InsImuSample sample = {0};
    sample.sample_timestamp_us = timestamp_us;
    sample.receive_timestamp_us = timestamp_us;
    sample.sequence = sequence;
    sample.accel_b_mps2[2] = SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    InsTask_AlignmentProcess(&sample);
}
