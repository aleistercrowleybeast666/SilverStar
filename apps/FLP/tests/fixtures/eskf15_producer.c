/* Synthetic Host fixture: actual C filter + SSLOG codecs + generated descriptor.
 * This is not recorded flight data and is never written onto a target. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "navigation_eskf.h"
#include "navigation_eskf_config.h"
#include "sslog_protocol.h"
#include "project_log_decoder_profile.h"

static NavigationEskfState s_state;
static NavigationEskfWorkspace s_work;
static uint32_t s_sequence;
static unsigned s_interleaved;
static unsigned s_pending_valid;
static FlightLogRecord s_pending;
static const NavigationEskfConfig s_config = {
    SYSTEM_ESKF_GRAVITY_MPS2, SYSTEM_ESKF_GYRO_NOISE_DENSITY,
    SYSTEM_ESKF_ACCEL_NOISE_DENSITY, SYSTEM_ESKF_GYRO_BIAS_RW, SYSTEM_ESKF_ACCEL_BIAS_RW,
    {SYSTEM_ESKF_NIS_1D_SOFT, SYSTEM_ESKF_NIS_2D_SOFT},
    {SYSTEM_ESKF_NIS_1D_HARD, SYSTEM_ESKF_NIS_2D_HARD}, SYSTEM_ESKF_NIS_MAX_R_SCALE
};

static void RecordRaw_Write(FILE *file, const FlightLogRecord *record)
{
    uint8_t wire[300];
    uint16_t length;
    assert(FlightLog_RecordSerialize(record, s_sequence++, wire, sizeof(wire), &length)
        == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    assert(fwrite(wire, 1, length, file) == length);
}

static void Record_Write(FILE *file, FlightLogRecord *record)
{
    if (s_interleaved && record->record_type==FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART &&
        record->payload.eskf15_full_p_part.part_index==3U) {
        assert(!s_pending_valid);
        s_pending=*record; s_pending_valid=1U;
        return;
    }
    RecordRaw_Write(file,record);
    if (s_pending_valid) {
        RecordRaw_Write(file,&s_pending); s_pending_valid=0U;
    }
}

static void Snapshot_Write(FILE *file, uint32_t id, uint8_t initial)
{
    FlightLogRecord record = {0};
    FlightLogEskf15StateRecord *state = &record.payload.eskf15_state;
    record.record_type = initial ? FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE :
        FLIGHT_LOG_RECORD_ESKF15_STATE;
    record.timestamp_us = s_state.timestamp_us;
    state->snapshot_id = id; state->epoch = 1U; state->calibration_generation = 1U;
    state->algorithm_id = 2U; state->algorithm_revision = 1U; state->quality_revision = 3U;
    memcpy(state->position_enu_m, s_state.position, sizeof(state->position_enu_m));
    memcpy(state->velocity_enu_mps, s_state.velocity, sizeof(state->velocity_enu_mps));
    memcpy(state->q_nb, s_state.quaternion, sizeof(state->q_nb));
    memcpy(state->gyro_bias_radps, s_state.gyro_bias, sizeof(state->gyro_bias_radps));
    memcpy(state->accel_bias_mps2, s_state.accel_bias, sizeof(state->accel_bias_mps2));
    for (unsigned i=0; i<15; ++i) { state->p_diagonal[i] = s_state.covariance[i][i]; }
    Record_Write(file, &record);
    unsigned row=0U, column=0U;
    for (unsigned part=0U; part<4U; ++part) {
        memset(&record, 0, sizeof(record));
        record.record_type = initial ? FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART :
            FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART;
        record.timestamp_us = s_state.timestamp_us;
        FlightLogEskf15CovariancePartRecord *p = &record.payload.eskf15_full_p_part;
        p->snapshot_id=id; p->epoch=1U; p->calibration_generation=1U;
        p->algorithm_id=2U; p->phase=initial ? 0U : 1U;
        p->part_index=part; p->part_count=4U; p->count=30U; p->offset=part*30U;
        for (unsigned i=0U; i<30U; ++i) {
            p->values[i]=s_state.covariance[row][column++];
            if (column==15U) { row++; column=row; }
        }
        Record_Write(file, &record);
    }
}

static void Bootstrap_Write(FILE *file)
{
    FlightLogFileHeaderInfo info = {0};
    uint8_t bytes[64]; uint16_t length;
    info.nominal_imu_rate_hz=200U; info.nominal_ins_rate_hz=100U;
    info.coordinate_frame=1U; info.position_axis_order[0]=3U;
    info.position_axis_order[1]=1U; info.position_axis_order[2]=2U;
    info.quaternion_order=1U; info.quaternion_semantics=1U;
    info.local_gravity_mps2=SYSTEM_ESKF_GRAVITY_MPS2;
    info.mechanization_subsample_count=2U; info.firmware_version[3]=12U;
    memcpy(info.air_compatibility_tag,"AIR-NCRC",8U); memcpy(info.build_tag,"SYNESKF1",8U);
    assert(FlightLog_FileHeaderSerialize(&info,bytes,sizeof(bytes),&length)
        == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    assert(fwrite(bytes,1,length,file)==length);
    FlightLogRecord record = {0}; ProjectLogDecoderProfile profile;
    ProjectLogDecoderProfile_Get(&profile);
    record.record_type=FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR;
    record.timestamp_us=999990U;
    FlightLogDecoderProfileDescriptorRecord *d=&record.payload.decoder_profile_descriptor;
    d->package_schema_major=profile.package_schema_major;
    d->package_schema_minor=profile.package_schema_minor;
    d->container_format_major=profile.container_format_major;
    d->container_format_minor=profile.container_format_minor;
    memcpy(d->record_catalog_hash_128,profile.record_catalog_hash_128,16U);
    memcpy(d->project_semantics_hash_128,profile.project_semantics_hash_128,16U);
    memcpy(d->generation_profile_hash_128,profile.generation_profile_hash_128,16U);
    Record_Write(file,&record);
    memset(&record,0,sizeof(record)); record.record_type=FLIGHT_LOG_RECORD_CALIBRATION_RESULT;
    record.timestamp_us=999992U;
    record.payload.calibration_result.state=4U; record.payload.calibration_result.ready=1U;
    for (unsigned i=0; i<3; ++i) {
        record.payload.calibration_result.accel_scale[i]=1.0f;
        record.payload.calibration_result.gyro_scale[i]=1.0f;
    }
    Record_Write(file,&record);
    memset(&record,0,sizeof(record)); record.record_type=FLIGHT_LOG_RECORD_INITIAL_STATE;
    record.timestamp_us=999995U; record.payload.initial_state.q_nb[0]=1.0f;
    record.payload.initial_state.origin_valid_flags=3U;
    record.payload.initial_state.gnss_origin_latitude_e7=310000000;
    record.payload.initial_state.gnss_origin_longitude_e7=1210000000;
    Record_Write(file,&record);
    memset(&record,0,sizeof(record)); record.record_type=FLIGHT_LOG_RECORD_EVENT;
    record.timestamp_us=1000000U; record.payload.event.event_id=FLIGHT_LOG_EVENT_MISSION_START;
    Record_Write(file,&record);
}

int main(int argc, char **argv)
{
    assert(argc==2 || argc==3);
    s_interleaved=(argc==3);
    FILE *file=fopen(argv[1],"wb"); assert(file!=NULL);
    const float nominal[16]={0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0};
    const float diagonal[15]={4,4,9,.25,.25,.25,.030461742f,.030461742f,.030461742f,
                             .0001f,.0001f,.0001f,.01f,.01f,.01f};
    for (unsigned i=0; i<15; ++i) { s_work.f[i][i]=diagonal[i]; }
    assert(NavigationEskf_Initialize(&s_state,&s_work,nominal,
        (const float (*)[15])s_work.f,1000000U,0U,1U)==NAV_ESKF_OK);
    Bootstrap_Write(file); Snapshot_Write(file,0U,1U);
    for (unsigned step=1U; step<=100U; ++step) {
        NavigationEskfBodyInput body={0}; FlightLogRecord record={0};
        body.start_us=s_state.timestamp_us; body.end_us=body.start_us+10000U;
        body.dt_s=.01f; body.generation=1U;
        body.accel_mps2[0][2]=body.accel_mps2[1][2]=SYSTEM_ESKF_GRAVITY_MPS2+.01f;
        body.gyro_radps[0][0]=body.gyro_radps[1][0]=.005f;
        record.record_type=FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT;
        record.timestamp_us=body.end_us;
        FlightLogEskf15BodyInputRecord *b=&record.payload.eskf15_body_input;
        b->interval_start_timestamp_us=body.start_us; b->interval_end_timestamp_us=body.end_us;
        b->sequence=step; b->calibration_generation=1U; b->dt_s=body.dt_s;
        memcpy(b->body_accel_mps2,body.accel_mps2,sizeof(b->body_accel_mps2));
        memcpy(b->body_gyro_radps,body.gyro_radps,sizeof(b->body_gyro_radps));
        Record_Write(file,&record);
        assert(NavigationEskf_Predict(&s_state,&s_work,&s_config,&body)==NAV_ESKF_OK);
        if (step%10U==0U) for (unsigned group=0U; group<5U; ++group) {
            NavigationEskfMeasurement observation={0}; NavigationEskfOutcome outcome;
            observation.group=group; observation.physically_valid=1U;
            observation.variance[0]=observation.variance[1]=1.0f;
            observation.angular_rate_b_radps[0]=.005f;
            assert(NavigationEskf_Update(&s_state,&s_work,&s_config,&observation,&outcome)
                == NAV_ESKF_OK);
            memset(&record,0,sizeof(record));
            record.record_type=FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT;
            record.timestamp_us=s_state.timestamp_us;
            FlightLogEskf15MeasurementRecord *m=&record.payload.eskf15_measurement;
            m->sample_timestamp_us=m->receive_timestamp_us=m->measurement_timestamp_us=
                m->evaluation_timestamp_us=s_state.timestamp_us;
            m->operation_sequence=step*5U+group; m->epoch=1U; m->calibration_generation=1U;
            m->group=group; m->physically_valid=m->admitted=1U; m->update_result=outcome.result;
            m->quality_scale=m->consistency_scale=m->robust_scale=1.0f; m->nis=outcome.nis;
            memcpy(m->base_variance,observation.variance,sizeof(m->base_variance));
            memcpy(m->innovation,outcome.innovation,sizeof(m->innovation));
            memcpy(m->effective_variance,outcome.effective_variance,sizeof(m->effective_variance));
            Record_Write(file,&record);
        }
        Snapshot_Write(file,step,0U);
    }
    if (s_pending_valid) { RecordRaw_Write(file,&s_pending); s_pending_valid=0U; }
    assert(fclose(file)==0); return 0;
}
