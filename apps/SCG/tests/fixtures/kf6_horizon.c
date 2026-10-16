/* Host-only direct accessors; numerical implementation is the owning payload. */
#include "navigation_kf_horizon.h"
#include <math.h>
#include <string.h>

static NavigationKfHorizon s_horizon;
static NavigationKfContext s_output;

int Test_KfReset(uint64_t lag);
int Test_KfBody(uint64_t end_us, float dt_s, const float delta[3], uint32_t source, uint32_t generation);
int Test_KfInsert(uint64_t source_us, uint64_t receive_us, uint32_t sequence, uint32_t source,
    uint32_t generation, uint32_t group, uint32_t valid, uint32_t operation, const float values[4]);
int Test_KfAdvance(void);
int Test_KfPop(uint32_t ids[6], float values[6]);
void Test_KfSnapshot(float primary[42], float output[42], float acceleration[3], uint64_t times[3], uint32_t counts[9]);
void Test_KfCorrupt(uint32_t kind);
int Test_KfTrack(uint64_t receive_us, uint32_t sequence, uint32_t source, uint32_t valid);
uint32_t Test_KfSize(void);
int Test_KfResetInvalid(uint32_t kind);

int Test_KfReset(uint64_t lag)
{
    NavigationKf_Init(&s_output);
    return (int)NavigationKfHorizon_Reset(&s_horizon,&s_output,1000000ULL,7U,0U,1U,lag);
}

int Test_KfBody(uint64_t end_us, float dt_s, const float delta[3], uint32_t source, uint32_t generation)
{ return (int)NavigationKfHorizon_BodyReceive(&s_horizon,end_us,delta,dt_s,source,generation); }

int Test_KfInsert(uint64_t source_us, uint64_t receive_us, uint32_t sequence, uint32_t source,
    uint32_t generation, uint32_t group, uint32_t valid, uint32_t operation, const float values[4])
{
    NavigationKfHorizonEvent event;
    memset(&event,0,sizeof(event));
    event.source_us = source_us; event.receive_us = receive_us; event.sample_us = source_us;
    event.sequence = sequence; event.source = source; event.generation = generation; event.epoch = 7U;
    event.group = (uint8_t)group; event.physically_valid = (uint8_t)valid; event.operation_sequence = operation;
    memcpy(event.observation,values,2U*sizeof(float)); memcpy(event.variance,values+2,2U*sizeof(float));
    memcpy(event.base_variance,values+2,2U*sizeof(float)); event.quality_scale = 1.0f; event.consistency_scale = 1.0f;
    return (int)NavigationKfHorizon_Insert(&s_horizon,&event);
}

int Test_KfAdvance(void) { return (int)NavigationKfHorizon_Advance(&s_horizon,&s_output); }

int Test_KfPop(uint32_t ids[6], float values[6])
{
    NavigationKfHorizonEvent event;
    NavigationKfHorizonResult result = NavigationKfHorizon_CompletionPop(&s_horizon,&event);
    if (result != NAV_KF_HORIZON_OK) { return (int)result; }
    ids[0] = event.operation_sequence; ids[1] = event.sequence; ids[2] = event.group; ids[3] = event.source;
    ids[4] = (uint32_t)event.result; ids[5] = event.effective_update;
    values[0] = event.nis; values[1] = event.robust_scale;
    memcpy(values+2,event.innovation,2U*sizeof(float)); memcpy(values+4,event.effective_variance,2U*sizeof(float));
    return (int)result;
}

void Test_KfSnapshot(float primary[42], float output[42], float acceleration[3], uint64_t times[3], uint32_t counts[9])
{
    memcpy(primary,s_horizon.primary.state,6U*sizeof(float));
    memcpy(primary+6,s_horizon.primary.covariance,36U*sizeof(float));
    memcpy(output,s_output.state,6U*sizeof(float)); memcpy(output+6,s_output.covariance,36U*sizeof(float));
    memcpy(acceleration,s_horizon.output_acceleration,3U*sizeof(float));
    times[0] = s_horizon.primary_us; times[1] = s_horizon.output_us; times[2] = s_horizon.present_us;
    counts[0] = s_horizon.body_count; counts[1] = s_horizon.event_count; counts[2] = s_horizon.completion_count;
    counts[3] = s_horizon.faulted; counts[4] = s_horizon.warmup; counts[5] = s_horizon.last_work;
    counts[6] = s_horizon.maximum_work; counts[7] = s_horizon.late_count; counts[8] = s_horizon.capacity_count;
}

void Test_KfCorrupt(uint32_t kind)
{
    if (kind == 1U) { s_horizon.primary.covariance[0][0] = -1.0f; }
    if (kind == 2U) { s_horizon.body[s_horizon.body_head].delta_velocity[0] = NAN; }
    if (kind == 3U) { s_horizon.body_count = NAV_KF_HORIZON_BODY_CAPACITY+1U; }
    if (kind == 4U) { s_horizon.event_count = NAV_KF_HORIZON_EVENT_CAPACITY+1U; }
    if (kind == 5U) { s_horizon.completion_read = NAV_KF_HORIZON_EVENT_CAPACITY; }
    if (kind == 6U) { s_horizon.primary.process_accel_std_mps2[0] *= 2.0f; }
    if (kind == 7U) { s_output.state[0] = 12345.0f; s_output.covariance[0][0] = -1.0f; }
    if (kind == 8U) { s_horizon.primary.covariance[1][0] = 100.0f; s_horizon.primary.covariance[0][1] = 100.0f; }
    if (kind == 9U) { s_horizon.event[0].variance[0] = NAN; }
    if (kind == 10U) { s_output.process_accel_std_mps2[0] *= 2.0f; }
    if (kind == 11U) { s_horizon.receive_tracker[1].initialized = 0U; }
}

int Test_KfTrack(uint64_t receive_us, uint32_t sequence, uint32_t source, uint32_t valid)
{
    NavigationKfGnssEpoch epoch;
    NavigationReplayEvent event;
    memset(&epoch,0,sizeof(epoch)); memset(&event,0,sizeof(event));
    epoch.timestamp_us = receive_us; epoch.valid_group_mask = (uint8_t)valid;
    for (uint32_t axis = 0U; axis < 3U; axis++) { epoch.position_std_m[axis] = 1.0f; epoch.velocity_std_mps[axis] = 1.0f; }
    event.sequence = sequence; event.source = source; event.calibration_generation = 1U;
    return (int)NavigationKfHorizon_ReceiveTrack(&s_horizon,&epoch,&event);
}

uint32_t Test_KfSize(void) { return (uint32_t)sizeof(s_horizon); }

int Test_KfResetInvalid(uint32_t kind)
{
    NavigationKfContext state;
    NavigationKf_Init(&state);
    if (kind == 0U) { state.process_accel_std_mps2[0] = 0.0f; }
    if (kind == 1U) { state.nis_soft_threshold[0] = 0.0f; }
    return (int)NavigationKfHorizon_Reset(&s_horizon,&state,1000000ULL,7U,0U,1U,30000ULL);
}
