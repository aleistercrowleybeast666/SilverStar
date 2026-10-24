/* Current-source integration fixture. No board, scheduler or sensor emulation. */
#include "navigation_journal.h"
#include "logger_bus.h"
#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static NavigationReplay s_ordered, s_delayed;
static NavigationReplayWorkspace s_ordered_work, s_delayed_work;
static NavigationJournal s_journal;
static FILE *s_output;
static uint32_t s_storage_fail;

LoggerBusResult LoggerBus_NavigationOperationPush(uint64_t timestamp_us,
    const FlightLogNavigationOperationPartRecord *record)
{
    if (s_storage_fail != 0U) { return LOGGER_BUS_RESULT_FULL; }
    assert(s_output != NULL && record != NULL);
    assert(fprintf(s_output, "{\"timestamp_us\":%" PRIu64 ",\"record\":{"
        "\"epoch\":%u,\"operation\":%u,\"transaction_crc32\":%u,\"total_size\":%u,"
        "\"part_index\":%u,\"part_count\":%u,\"kind\":%u,\"algorithm_id\":%u,\"revision\":%u,\"data\":[",
        timestamp_us, record->epoch, record->operation, record->transaction_crc32,
        record->total_size, record->part_index, record->part_count, record->kind,
        record->algorithm_id, record->revision) > 0);
    for (uint32_t i=0U; i<160U; i++) {
        assert(fprintf(s_output, "%s%u", i==0U?"":",", record->data[i]) > 0);
    }
    assert(fputs("]}}\n", s_output) >= 0);
    return LOGGER_BUS_RESULT_OK;
}

static void State_Initialize(NavigationState *state, NavigationModel model)
{
    (void)memset(state, 0, sizeof(*state));
    state->model=model;
    uint32_t dimension=model==NavigationInEkf15?15U:20U;
    for (uint32_t i=0U; i<3U; i++) { state->rotation[i*3U+i]=1.0; state->installation[i*3U+i]=1.0; }
    for (uint32_t i=0U; i<dimension; i++) { state->covariance[i*20U+i]=(double)0.25f; }
}

static void Replay_Initialize(NavigationModel model)
{
    NavigationState initial;
    const NavigationInputIdentity imu={1U,1U,0U};
    const NavigationInputIdentity observations[3]={{1U,0U,0U},{1U,0U,0U},{1U,0U,0U}};
    const double gravity[3]={0.0,0.0,-(double)9.78f};
    double density[12];
    for (uint32_t i=0U; i<12U; i++) { density[i]=(double)0.001f; }
    State_Initialize(&initial,model);
    assert(NavigationReplay_Initialize(&s_ordered,&s_ordered_work,&initial,1000000U,
        &imu,observations,gravity,density,100000U)==NavigationSessionResult_Ok);
    assert(NavigationReplay_Initialize(&s_delayed,&s_delayed_work,&initial,1000000U,
        &imu,observations,gravity,density,100000U)==NavigationSessionResult_Ok);
}

static NavigationReplayObservation Observation_Create(uint64_t receive_us)
{
    NavigationReplayObservation value={0};
    value.event.identity=(NavigationInputIdentity){1U,0U,0U};
    value.event.sample_us=1010001U;value.event.receive_us=receive_us;
    value.event.sequence=1U;value.event.timestamp_trusted=1U;
    value.measured[0]=0.02;value.measured[1]=-0.01;value.gate=1000.0;
    for (uint32_t i=0U; i<3U; i++) { value.covariance[i*3U+i]=0.1; }
    return value;
}

static void State_Write(const NavigationState *state)
{
    uint32_t dimension=state->model==NavigationInEkf15?15U:20U;
    assert(fprintf(s_output,"{\"final\":{\"model\":%u,\"position\":[",(unsigned)state->model)>0);
    for (uint32_t i=0U;i<3U;i++) { assert(fprintf(s_output,"%s%.17g",i==0U?"":",",state->position[i])>0); }
    assert(fputs("],\"velocity\":[",s_output)>=0);
    for (uint32_t i=0U;i<3U;i++) { assert(fprintf(s_output,"%s%.17g",i==0U?"":",",state->velocity[i])>0); }
    assert(fputs("],\"rotation\":[",s_output)>=0);
    for (uint32_t i=0U;i<9U;i++) { assert(fprintf(s_output,"%s%.17g",i==0U?"":",",state->rotation[i])>0); }
    assert(fputs("],\"covariance\":[",s_output)>=0);
    for (uint32_t i=0U;i<dimension;i++) {
        for (uint32_t j=0U;j<dimension;j++) {
            assert(fprintf(s_output,"%s%.17g",(i==0U && j==0U)?"":",",state->covariance[i*20U+j])>0);
        }
    }
    assert(fputs("]}}\n",s_output)>=0);
}

static void Quality_Check(void)
{
    NavigationMagQuality state={0};NavigationMagQualityOutput output;
    NavigationMagQualityConfig config={.minimum_samples=16U,.minimum_duration_us=15000U,
        .maximum_gap_us=2000U,.maximum_sequence_step=1U,.variance_floor_uT2=0.01f,
        .maximum_std_uT=2.0f,.maximum_span_uT=4.0f,.gyro_max_radps=0.1f,
        .accel_tolerance_mps2=0.1f,.accel_span_mps2=0.1f,.gravity_mps2=9.78f,
        .field_reference_uT=50.0f,.field_min_ratio=0.5f,.field_max_ratio=1.5f,
        .delay_us=100U,.uncertainty_us=10U,.maximum_time_uncertainty_us=100U,
        .maximum_queue_bytes=32U,.delay_bound_verified=0U};
    NavigationMagQualityInput input={.sensor_uT={50.0f,0.0f,0.0f},
        .corrected_uT={50.0f,0.0f,0.0f},.accel_mps2={0.0f,0.0f,9.78f},
        .transport_valid=1U,.imu_valid=1U,.transport_epoch=1U,.calibration_generation=3U,
        .decode_span_us=5U};
    for(uint32_t i=0U;i<config.minimum_samples;i++) {
        input.decode_us=1000000U+i*1000U;input.now_us=input.decode_us+10U;
        input.accel_decode_us=input.decode_us;input.gyro_decode_us=input.decode_us;input.sequence=i;
        assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Ok);
    }
    assert(output.covariance_valid==1U && output.time_admitted==0U);
    assert((output.flags&NAVIGATION_MAG_Q_UNVERIFIED)!=0U);
    assert(output.covariance_sensor_uT2[0]>0.0f);
    config.delay_bound_verified=1U;input.decode_us+=1000U;input.now_us+=1000U;
    input.accel_decode_us=input.decode_us;input.gyro_decode_us=input.decode_us;input.sequence++;
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Ok);
    assert(output.time_admitted==1U && output.uncertainty_us==15U && output.sample_us==input.decode_us-100U);
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Duplicate);
    input.calibration_generation++;input.sequence++;input.decode_us+=1000U;input.now_us+=1000U;
    input.accel_decode_us=input.decode_us;input.gyro_decode_us=input.decode_us;
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Ok);
    assert(output.covariance_valid==0U && state.count==1U);
    input.sequence++;input.decode_us+=1000U;input.now_us+=1000U;input.transport_valid=0U;
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Ok);
    assert(output.time_admitted==0U && state.count==0U);
    input.sensor_uT[0]=NAN;
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_InvalidInput);
    config.minimum_samples=0U;
    assert(NavigationMagQuality_Process(&state,&config,&input,&output)==NavigationMagQualityResult_Unconfigured);
    assert(fputs("{\"quality\":{\"boundary_checks\":8,\"hardware_qualified\":false}}\n",s_output)>=0);
}

static void Replay_Check(NavigationModel model)
{
    const double gyro[6]={0.0,0.0,0.0,0.0,0.0,0.0};
    const double force[6]={2.0,0.0,(double)9.78f,2.0,1.0,(double)9.78f};
    const int32_t geodetic[3]={0,0,0};
    NavigationReplayOutcome outcome;
    NavigationReplayObservation observation=Observation_Create(1010001U);
    NavigationInputIdentity imu={1U,1U,0U};
    Replay_Initialize(model);
    assert(NavigationJournal_Initial(&s_journal,&s_delayed,geodetic,0U,0U,0U)==NavigationJournalResult_Ok);
    assert(NavigationReplay_Predict(&s_ordered,&s_ordered_work,&imu,1000000U,1010001U,gyro,force)==NavigationSessionResult_Ok);
    assert(NavigationReplay_Observe(&s_ordered,&s_ordered_work,&observation,&outcome)==NavigationSessionResult_Ok);
    assert(NavigationReplay_Predict(&s_ordered,&s_ordered_work,&imu,1010001U,1020002U,gyro,force)==NavigationSessionResult_Ok);
    assert(NavigationReplay_Predict(&s_delayed,&s_delayed_work,&imu,1000000U,1010001U,gyro,force)==NavigationSessionResult_Ok);
    assert(NavigationJournal_Predict(&s_journal,&imu,1000000U,1010001U,gyro,force,NavigationSessionResult_Ok)==NavigationJournalResult_Ok);
    assert(NavigationReplay_Predict(&s_delayed,&s_delayed_work,&imu,1010001U,1020002U,gyro,force)==NavigationSessionResult_Ok);
    assert(NavigationJournal_Predict(&s_journal,&imu,1010001U,1020002U,gyro,force,NavigationSessionResult_Ok)==NavigationJournalResult_Ok);
    observation.event.receive_us=1020002U;
    assert(NavigationReplay_Observe(&s_delayed,&s_delayed_work,&observation,&outcome)==NavigationSessionResult_Ok);
    assert(NavigationJournal_Observe(&s_journal,1020002U,&observation,&outcome)==NavigationJournalResult_Ok);
    const NavigationState *a=&s_ordered.current.navigation,*b=&s_delayed.current.navigation;
    for (uint32_t i=0U;i<3U;i++) { assert(fabs(a->position[i]-b->position[i])<1e-12);assert(fabs(a->velocity[i]-b->velocity[i])<1e-12); }
    for (uint32_t i=0U;i<400U;i++) { assert(fabs(a->covariance[i]-b->covariance[i])<1e-12); }
    NavigationState before=*b;
    assert(NavigationReplay_Observe(&s_delayed,&s_delayed_work,&observation,&outcome)==NavigationSessionResult_Duplicate);
    assert(memcmp(&before,b,sizeof(before))==0);
    assert(NavigationJournal_Observe(&s_journal,1020002U,&observation,&outcome)==NavigationJournalResult_Ok);
    assert(NavigationJournal_End(&s_journal,1020002U,0U)==NavigationJournalResult_Ok);
    State_Write(b);
    /* Fixed body capacity retires an anchor; older observations must refuse. */
    for (uint32_t i=2U;i<NAVIGATION_REPLAY_BODY_CAPACITY;i++) {
        uint64_t start=s_delayed.current.state_us;
        assert(NavigationReplay_Predict(&s_delayed,&s_delayed_work,&imu,start,start+1000U,gyro,force)==NavigationSessionResult_Ok);
    }
    uint64_t start=s_delayed.current.state_us;
    uint64_t anchor=s_delayed.anchor.state_us;
    assert(NavigationReplay_Predict(&s_delayed,&s_delayed_work,&imu,start,start+1000U,gyro,force)==NavigationSessionResult_Ok);
    assert(s_delayed.body_count==NAVIGATION_REPLAY_BODY_CAPACITY && s_delayed.anchor.state_us>anchor);
    before=s_delayed.current.navigation;
    observation.event.sample_us=1000000U;observation.event.receive_us=s_delayed.current.state_us;
    assert(NavigationReplay_Observe(&s_delayed,&s_delayed_work,&observation,&outcome)==NavigationSessionResult_HistoryMiss);
    assert(memcmp(&before,&s_delayed.current.navigation,sizeof(before))==0);
    s_storage_fail=1U;
    assert(NavigationJournal_Initial(&s_journal,&s_ordered,geodetic,0U,0U,0U)==NavigationJournalResult_InvalidInput);
    Replay_Initialize(model);
    assert(NavigationJournal_Initial(&s_journal,&s_delayed,geodetic,0U,0U,0U)==NavigationJournalResult_StorageUnavailable);
    assert(s_journal.healthy==0U && s_journal.failures==1U);
}

int main(int argc,char **argv)
{
    assert(argc==3);
    int model=atoi(argv[1]);assert(model>=1 && model<=3);
    s_output=fopen(argv[2],"w");assert(s_output!=NULL);
    Quality_Check();
    Replay_Check((NavigationModel)model);
    assert(fclose(s_output)==0);s_output=NULL;
    return EXIT_SUCCESS;
}
