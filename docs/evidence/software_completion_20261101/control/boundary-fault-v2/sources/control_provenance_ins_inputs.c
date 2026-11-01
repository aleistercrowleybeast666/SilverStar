/* Actual INS numerical aggregation and queue publisher. Hardware input only is
 * injected; no task readiness, correction, delta or publication is mocked. */
#include "../../APP/Src/ins_task.c"
#include "optional_start_inputs.h"
static uint8_t s_alignment_source_change;
void Test_ControlAlignmentSourceChange(uint8_t enabled) { s_alignment_source_change = enabled; }

void Test_InsInputFeed(uint64_t timestamp_us, uint32_t sequence)
{
    InsImuSample sample = {0};
    sample.sample_timestamp_us = timestamp_us;
    sample.receive_timestamp_us = timestamp_us;
    sample.sequence = sequence;
    sample.accel_b_mps2[2] = SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    sample.canonical_source_instance = (uint8_t)((s_alignment_source_change != 0U) && (sequence <= 3U));
    sample.canonical_source_valid = 1U;
    InsTask_AlignmentProcess(&sample);
}

void Test_ControlRawFeed(uint64_t timestamp_us, uint32_t sequence, uint8_t source_valid, uint8_t source)
{
    InsImuSample sample = {0};
    sample.sample_timestamp_us = timestamp_us;
    sample.receive_timestamp_us = timestamp_us;
    sample.sequence = sequence;
    sample.accel_b_mps2[2] = SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.gyro_b_radps[1] = .01f;
    sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    sample.canonical_source_instance = source;
    sample.canonical_source_valid = source_valid;
    InsTask_Propagate(&sample);
}

uint8_t Test_ControlInsFaultGet(void) { return s_input_fault_latched; }
