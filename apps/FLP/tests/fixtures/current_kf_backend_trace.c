/* Host-only deterministic trace fixture, migrated from the retained
 * current-state software evidence. All included firmware files are supplied
 * from a freshly generated project at compilation, never a retained binary. */
/* Execute the real task's collectors, freeze, preparation and selected kernel.
 * Including its translation unit exposes private state only to this Host test;
 * no readiness/kernel routine is replaced. Hardware, clock and alignment input
 * are deterministic fixtures. Unused RTOS run loops are linker-collected. */
#include "APP/Src/estimator_task.c"
#include "host_platform_mock.h"
#include "system_calibration.h"
#include "system_log_policy.h"
#include <stdio.h>
#include "test_common.h"
#include "system_gnss_quality.h"

static uint64_t s_test_now = 1000000ULL;
static uint8_t s_test_alignment_ready = 1U;
static uint8_t s_test_quaternion_ready = 1U;
static uint8_t s_test_quaternion_invalid;
static uint8_t s_test_gnss_source;
static SystemGnssSample s_test_gnss;
static EstimatorPressureSnapshot s_test_pressure;
static SystemLifecycleState s_test_lifecycle = SYSTEM_STATE_PREFLIGHT;


SystemLifecycleState SystemLifecycle_GetState(void) { return s_test_lifecycle; }
uint8_t SystemAlignment_IsReady(void) { return s_test_alignment_ready; }
uint8_t SystemAlignment_IsCollecting(void) { return 1U; }
SystemDeviceResult SystemAlignment_PreflightQuaternionGet(float q[4], SystemAlignmentPreflightAttitudeSource *source)
{
    if (s_test_quaternion_ready == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    q[0] = (s_test_quaternion_invalid == 0U) ? 1.0f : 0.0f;
    q[1] = 0.0f; q[2] = 0.0f; q[3] = 0.0f;
    *source = SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_test_gnss; return SystemGnssQuality_Evaluate(sample, s_test_now); }
const char *SystemGnss_NameGet(void) { return "HostGnss"; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = 0U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{ *instance = s_test_gnss_source; return SYSTEM_DEVICE_OK; }
void vTaskDelay(TickType_t ticks) { s_test_now += (uint64_t)ticks * 1000ULL; HostPlatformMock_TimeSetUs(s_test_now); }

static void Test_Collect(uint8_t gnss_available)
{
    uint16_t index;
    (void)memset(&s_test_gnss, 0, sizeof(s_test_gnss));
    (void)memset(&s_test_pressure, 0, sizeof(s_test_pressure));
    s_test_gnss.position_usable = gnss_available;
    s_test_gnss.online = gnss_available;
    s_test_gnss.fix_type = 3U;
    s_test_gnss.fix_ok = 1U;
    s_test_gnss.supported_fields = 0x3FFU;
    s_test_gnss.valid_fields = s_test_gnss.supported_fields;
    s_test_gnss.satellite_count = 8U;
    s_test_gnss.speed_accuracy_mps = 0.2f;
    s_test_gnss.latitude_e7 = 300000000;
    s_test_gnss.longitude_e7 = 1200000000;
    s_test_gnss.horizontal_accuracy_m = 1.0f;
    s_test_gnss.vertical_accuracy_m = 2.0f;
    s_test_gnss.velocity_valid_mask = 7U;
    s_test_gnss.velocity_variance_m2ps2[0] = 0.04f;
    s_test_gnss.velocity_variance_m2ps2[1] = 0.04f;
    s_test_gnss.velocity_variance_m2ps2[2] = 0.04f;
    s_test_pressure.altitude_m = 10.0f;
    s_test_pressure.pressure_pa = 101325.0f;
    s_test_pressure.valid = 1U;
    s_test_pressure.supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
    s_test_pressure.valid_fields = s_test_pressure.supported_fields;
    for (index = 0U; index < SYSTEM_ESTIMATOR_GNSS_ORIGIN_WINDOW_SAMPLES; index++)
    {
        s_test_now += 50000ULL; HostPlatformMock_TimeSetUs(s_test_now);
        s_test_gnss.sequence++;
        s_test_pressure.sequence++;
        s_test_gnss.sample_timestamp_us = s_test_now;
        s_test_gnss.receive_timestamp_us = s_test_now;
        s_test_pressure.timestamp_us = s_test_now;
        s_test_pressure.receive_timestamp_us = s_test_now;
        TEST_CHECK(EstimatorBus_PressurePublish(&s_test_pressure) == ESTIMATOR_BUS_RESULT_OK);
        Estimator_OriginWindowCollect();
    }
}

#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
static void Test_GnssHealthVarianceScale(void)
{
    EstimatorGnssUpdateWork work = {0};
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    uint8_t group;
    work.sample.satellite_count = 5U;
    work.sample.valid_fields = SYSTEM_GNSS_FIELD_SATELLITE_COUNT;
    work.integrity_decision.position_r_scale = 3.0f;
    for (group = 0U; group < 4U; group++)
    {
        float soft = ((group & 1U) != 0U) ? profile->nis_1d_soft : profile->nis_2d_soft;
        float base = (group == 0U) ? 4.5f : 1.5f;
        TEST_CHECK_NEAR(Estimator_GnssHealthVarianceScale(&work, profile, group,
            NAV_KF_UPDATE_SOFT_WEIGHTED, soft * 2.0f), base * 2.0f, 0.00001f);
        TEST_CHECK_NEAR(Estimator_GnssHealthVarianceScale(&work, profile, group,
            NAV_KF_UPDATE_ACCEPTED, soft * 2.0f), base, 0.00001f);
        TEST_CHECK_NEAR(Estimator_GnssHealthVarianceScale(&work, profile, group,
            NAV_KF_UPDATE_REJECTED_NIS, soft * 2.0f), base, 0.00001f);
        TEST_CHECK_NEAR(Estimator_GnssHealthVarianceScale(&work, profile, group,
            NAV_KF_UPDATE_SOFT_WEIGHTED, soft * (profile->nis_max_r_scale + 5.0f)),
            base * profile->nis_max_r_scale, 0.00001f);
    }
}

static void Test_GnssHealthProducerVariance(void)
{
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    const float delta[3] = {0.0f, 0.0f, 0.0f};
    uint8_t group;
    for (group = 0U; group < 4U; group++)
    {
        EstimatorGnssUpdateWork work = {0};
        NavigationReplayEvent event = {0};
        SystemNavigationGroupHealth health;
        uint8_t axis = (group & 1U) ? 2U : 0U;
        uint8_t state_axis = (uint8_t)(axis + ((group < 2U) ? 0U : 3U));
        float soft = ((group & 1U) != 0U) ? profile->nis_1d_soft : profile->nis_2d_soft;
        float hard = ((group & 1U) != 0U) ? profile->nis_1d_hard : profile->nis_2d_hard;
        float target_nis = 0.5f * (soft + hard);
        float robust = fminf(target_nis / soft, profile->nis_max_r_scale);
        float scale = (group == 0U) ? 4.5f : 1.5f;
        NavigationKf_Init(&s_estimator.kf);
#if (SYSTEM_FUSION_TIMING_MODE == 0U)
        TEST_CHECK(NavigationCurrent_Reset(&s_current_fusion, &s_estimator.kf, 1000000ULL,
            7U, SystemCalibration_GenerationGet()) == NAV_CURRENT_OK);
        TEST_CHECK(NavigationCurrent_Predict(&s_current_fusion, &s_estimator.kf,
            1010000ULL, delta, 0.01f) == NAV_CURRENT_OK);
#else
        NavigationReplay_Reset(&s_replay, &s_replay_storage, &s_estimator.kf, 1000000ULL, 7U);
        TEST_CHECK(NavigationReplay_Predict(&s_replay, &s_estimator.kf, 1010000ULL, delta, 0.01f) == NAV_REPLAY_OK);
#endif
        SystemNavigationHealth_Reset(1000000ULL);
        work.sample.satellite_count = 5U;
        work.sample.valid_fields = SYSTEM_GNSS_FIELD_SATELLITE_COUNT;
        work.integrity_decision.position_r_scale = 3.0f;
        event.measurement_timestamp_us = 1010000ULL; event.receive_timestamp_us = 1010000ULL;
        event.epoch = 7U; event.sequence = 1U;
        event.kind = (group < 2U) ? NAV_REPLAY_POSITION : NAV_REPLAY_VELOCITY;
        event.valid_group_mask = (uint8_t)(1U << group); event.vertical_valid = 1U;
        for (uint8_t index = 0U; index < 3U; index++)
        { event.position_variance[index] = scale; event.velocity_variance[index] = scale; }
        if (group < 2U)
        { event.position[axis] = sqrtf(target_nis * (s_estimator.kf.covariance[state_axis][state_axis] + scale)); }
        else
        { event.velocity[axis] = sqrtf(target_nis * (s_estimator.kf.covariance[state_axis][state_axis] + scale)); }
        Estimator_GnssReplayEventApply(&event, &work);
        SystemDeviceResult health_result = SystemNavigationHealth_GroupGet(group, 1010000ULL, &health);
        TEST_CHECK(health_result == SYSTEM_DEVICE_OK);
        /* TEST_CHECK records a failure but continues. An error leaves health
         * untouched, so do not inspect it after recording that failed check. */
        if (health_result != SYSTEM_DEVICE_OK) { return; }
        TEST_CHECK(health.has_success == 1U && health.last_successful_fusion_us == 1010000ULL);
        TEST_CHECK(health.state == SYSTEM_NAVIGATION_SOFT_WEIGHTED);
        TEST_CHECK_NEAR(health.variance_scale, scale * robust, 0.0001f);
        TEST_CHECK_NEAR(health.nis, target_nis, 0.0001f);
    }
}
#endif

int ExistingPreparation_Main(void)
{
    EstimatorPreparationSnapshot preparation;
    EstimatorOutputSnapshot initial = {0};
    uint32_t generation;
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(EstimatorTask_OriginsReset() == SYSTEM_DEVICE_OK);
    Test_Collect(0U);
    if ((SYSTEM_USER_ALIGNMENT_REQUIRED_MASK &
         SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U)
    {
        TEST_CHECK(EstimatorTask_FreezeOrigins() == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(EstimatorTask_PrepareNavigation() != SYSTEM_DEVICE_OK);
        TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
        TEST_CHECK(preparation.initialized == 0U);
    }
    else
    {
        TEST_CHECK(EstimatorTask_FreezeOrigins() == SYSTEM_DEVICE_OK);
        TEST_CHECK(s_estimator.gnss_origin_valid == 0U);
        TEST_CHECK(s_estimator.gnss_fusion_enabled == 0U);
        TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
        TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
        TEST_CHECK(preparation.initialized == 1U && preparation.last_result == SYSTEM_DEVICE_OK);
        TEST_CHECK(Estimator_GetLatestSnapshot(&initial) != 0U);
        TEST_CHECK(initial.gnss_origin_valid == 0U && initial.baro_origin_valid == 1U);
        if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE)
        { TEST_CHECK((initial.health_flags & ESTIMATOR_HEALTH_GNSS_ORIGIN_UNAVAILABLE) != 0U); }
    }
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    {
        EstimatorGnssUpdateWork work = {0};
        TEST_CHECK(Estimator_GnssSamplePrepare(s_test_now, &work) == ESTIMATOR_GNSS_PREPARE_STOP);
    }
#endif
    TEST_CHECK(EstimatorTask_OriginsReset() == SYSTEM_DEVICE_OK);
    Test_Collect((uint8_t)(SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE));
    s_test_quaternion_ready = 0U;
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
    TEST_CHECK(preparation.initialized == 0U && preparation.last_result == SYSTEM_DEVICE_NOT_READY);
    s_test_quaternion_ready = 1U;
    /* A previous mission's cached counter must not escape a fresh initialize. */
    s_snapshot.predict_count = 1234U;
    s_published_snapshot.predict_count = 1234U;
    if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_KF6)
    {
        /* Actual INS/ESKF kernels must reject a zero quaternion. */
        s_test_quaternion_invalid = 1U;
        TEST_CHECK(EstimatorTask_PrepareNavigation() != SYSTEM_DEVICE_OK);
        TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
        TEST_CHECK(preparation.initialized == 0U && preparation.last_result != SYSTEM_DEVICE_OK);
        s_test_quaternion_invalid = 0U;
    }
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
    TEST_CHECK(preparation.algorithm_id == SYSTEM_FUSION_ALGORITHM);
    TEST_CHECK(preparation.initialized == 1U && preparation.last_result == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_estimator.initialized == 1U && s_estimator.mission_running == 0U);
    TEST_CHECK(s_estimator.origin_collection_frozen == 0U);
    TEST_CHECK(Estimator_GetLatestSnapshot(&initial) != 0U);
    TEST_CHECK(initial.initialized == 1U && initial.mission_running == 0U && initial.predict_count == 0U);
    TEST_CHECK(fabsf(initial.q_nb[0] - 1.0f) < 0.00001f);
    if (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_SF6)
    {
        uint8_t axis;
        /* SF6's committed contract has gains, not a covariance estimate;
         * its backend explicitly publishes NAN for these unavailable fields. */
        for (axis = 0U; axis < 6U; axis++)
        { TEST_CHECK(isnan(initial.covariance_diagonal[axis])); }
    }
    else if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE)
    {
        uint8_t axis;
        for (axis = 0U; axis < 6U; axis++)
        {
            if (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_SF6)
            { TEST_CHECK(isnan(initial.covariance_diagonal[axis])); }
            else
            { TEST_CHECK(initial.covariance_diagonal[axis] > 0.0f && isfinite(initial.covariance_diagonal[axis])); }
        }
    }
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(Estimator_GetLatestSnapshot(&initial) != 0U && initial.predict_count == 0U);
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    {
        uint8_t axis;
        EstimatorGnssUpdateWork work = {0};
        s_test_gnss.sequence++;
        s_test_now += 50000ULL; HostPlatformMock_TimeSetUs(s_test_now);
        s_test_gnss.sample_timestamp_us = s_test_now;
        s_test_gnss.receive_timestamp_us = s_test_now;
        TEST_CHECK(Estimator_GnssSamplePrepare(s_test_now, &work) == ESTIMATOR_GNSS_PREPARE_CONTINUE);
        TEST_CHECK(Estimator_GnssSamplePrepare(s_test_now, &work) == ESTIMATOR_GNSS_PREPARE_STOP);
        s_test_gnss_source = 1U;
        TEST_CHECK(Estimator_GnssSamplePrepare(s_test_now, &work) == ESTIMATOR_GNSS_PREPARE_CONTINUE);
        TEST_CHECK(s_estimator.last_gnss_source == 1U);
        for (axis = 0U; axis < 6U; axis++)
        {
            TEST_CHECK(isfinite(s_estimator.kf.covariance[axis][axis]) &&
                s_estimator.kf.covariance[axis][axis] > 0.0f);
        }
    }
#endif
    generation = preparation.generation;
    s_test_alignment_ready = 0U;
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
    TEST_CHECK(preparation.generation > generation && preparation.initialized == 0U);
    TEST_CHECK(s_estimator.initialized == 0U && s_estimator.mission_running == 0U);
    s_test_alignment_ready = 1U;
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorTask_OriginsReset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
    TEST_CHECK(preparation.initialized == 0U);
    s_test_lifecycle = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(EstimatorTask_PreparationGet(&preparation) == SYSTEM_DEVICE_OK);
    TEST_CHECK(preparation.last_result == SYSTEM_DEVICE_BAD_STATE && preparation.initialized == 0U);
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    Test_GnssHealthVarianceScale();
    Test_GnssHealthProducerVariance();
#endif
    return Test_Finish("estimator_preparation_actual");
}

SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{
    memset(time, 0, sizeof(*time)); time->sequence=s_test_gnss.sequence;
    time->time_of_week_ms=(uint32_t)(s_test_gnss.sample_timestamp_us/1000ULL);
    return SYSTEM_DEVICE_OK;
}
static FILE *s_trace_file;
static uint32_t s_trace_sequence;
static void Trace_Array(const float *v, unsigned count)
{
    fputc('[', s_trace_file);
    for (unsigned i=0;i<count;i++) { if(i) fputc(',',s_trace_file); fprintf(s_trace_file,"%.9g",(double)v[i]); }
    fputc(']',s_trace_file);
}
static void Trace_State(unsigned cycle)
{
    fprintf(s_trace_file,"{\"kind\":\"state\",\"cycle\":%u,\"time_us\":%llu,\"epoch\":%u,\"calibration_generation\":%u,\"state\":",cycle,(unsigned long long)Estimator_FusionPresentGet(),Estimator_FusionEpochGet(),SystemCalibration_GenerationGet());
    Trace_Array(s_estimator.kf.state,6); fputs(",\"P\":",s_trace_file);Trace_Array(&s_estimator.kf.covariance[0][0],36);
    fputs(",\"q\":",s_trace_file);Trace_Array(s_estimator.q_nb,4);
    fprintf(s_trace_file,",\"predict_count\":%u,\"faulted\":%u,\"initialized\":%u,\"mission_running\":%u,\"replay_count\":%u,\"nis\":",s_estimator.kf.predict_count,Estimator_FusionFaultGet(),s_snapshot.initialized,s_snapshot.mission_running,Estimator_FusionDiagnosticsGet()->replay_count);
    Trace_Array(s_estimator.kf.last_gnss_group_nis,4);fputs("}\n",s_trace_file);
}
static void Trace_Drain(unsigned cycle)
{
    FlightLogRecord record;uint8_t bytes[512];uint16_t size=0U;
    while(LoggerBus_NextPop(&record)==LOGGER_BUS_RESULT_OK) {
        FlightLogSerializeResult serialize_result=FlightLog_RecordSerialize(&record,++s_trace_sequence,bytes,sizeof(bytes),&size);
        TEST_CHECK(serialize_result==FLIGHT_LOG_SERIALIZE_RESULT_OK);
        if(serialize_result!=FLIGHT_LOG_SERIALIZE_RESULT_OK) { return; }
        fprintf(s_trace_file,"{\"kind\":\"wire\",\"cycle\":%u,\"record_type\":%u,\"timestamp_us\":%llu,\"hex\":\"",cycle,(unsigned)record.record_type,(unsigned long long)record.timestamp_us);
        for(unsigned i=0;i<size;i++) { fprintf(s_trace_file,"%02x",bytes[i]); }
        fputs("\"}\n",s_trace_file);
    }
}
int main(int argc,char **argv)
{
    SystemInertialIncrement prediction={0};
    if(argc!=2) { return 2; }
    s_trace_file=fopen(argv[1],"wb");if(!s_trace_file) { return 3; }
    HostPlatformMock_Reset();TEST_CHECK(SystemTime_Init()==SYSTEM_DEVICE_OK);
    HostPlatformMock_TimeSetUs(s_test_now);SystemCalibration_Init();
    TEST_CHECK(EstimatorBus_Init()==ESTIMATOR_BUS_RESULT_OK);TEST_CHECK(LoggerBus_Init()==LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_StreamingReady()==LOGGER_BUS_RESULT_OK);
    const FlightLogRecordType streams[]={FLIGHT_LOG_RECORD_GNSS_MEASUREMENT,FLIGHT_LOG_RECORD_BARO_MEASUREMENT,FLIGHT_LOG_RECORD_ESTIMATOR_STEP};
    for(unsigned i=0;i<3;i++){SystemLogStreamConfig config;TEST_CHECK(SystemLogPolicy_StreamGet(streams[i],&config)==SYSTEM_DEVICE_OK);config.enabled=1U;config.decimation=1U;TEST_CHECK(SystemLogPolicy_StreamConfigure(&config)==SYSTEM_DEVICE_OK);}
    TEST_CHECK(EstimatorTask_OriginsReset()==SYSTEM_DEVICE_OK);Test_Collect(1U);
    TEST_CHECK(EstimatorTask_FreezeOrigins()==SYSTEM_DEVICE_OK);TEST_CHECK(EstimatorTask_PrepareNavigation()==SYSTEM_DEVICE_OK);
    /* Fixture only controls mission activation; the initialization and all
       prediction/admission/observation/log paths below are owning source. */
    s_estimator.mission_running=1U;s_snapshot.mission_running=1U;s_test_lifecycle=SYSTEM_STATE_FLIGHT;
    Trace_State(0);Trace_Drain(0);
    prediction.dt_s=0.004f;prediction.delta_velocity_b_sculling_corrected[2]=9.80665f*prediction.dt_s;
    s_test_pressure.healthy=1U;s_test_pressure.variance_m2=1.0f;s_test_pressure.measurement_timestamp_trusted=1U;
    s_test_gnss.measurement_timestamp_trusted=1U;
    for(unsigned cycle=1;cycle<=200;cycle++) {
        s_test_now+=4000ULL;HostPlatformMock_TimeSetUs(s_test_now);prediction.timestamp_us=s_test_now;prediction.sequence=cycle;
        prediction.delta_velocity_b_sculling_corrected[0]=0.0001f;
        if(cycle%10U==0U){s_test_gnss.sequence++;s_test_gnss.receive_timestamp_us=s_test_now;s_test_gnss.sample_timestamp_us=s_test_now-1000ULL;s_test_gnss.latitude_e7++;s_test_gnss.velocity_enu_mps[0]=0.02f;}
        if(cycle==151U) { s_test_gnss_source=1U; }
        if(cycle==152U) { s_test_gnss_source=0U; }
        if(cycle%8U==0U){s_test_pressure.sequence++;s_test_pressure.receive_timestamp_us=s_test_now;s_test_pressure.timestamp_us=s_test_now-1000ULL;s_test_pressure.altitude_m=10.0f+(float)cycle*0.001f;TEST_CHECK(EstimatorBus_PressurePublish(&s_test_pressure)==ESTIMATOR_BUS_RESULT_OK);}
        fprintf(s_trace_file,"{\"kind\":\"input\",\"cycle\":%u,\"time_us\":%llu,\"dt_s\":%.9g,\"dv_body\":",cycle,(unsigned long long)s_test_now,(double)prediction.dt_s);Trace_Array(prediction.delta_velocity_b_sculling_corrected,3);fputs(",\"dtheta_body\":",s_trace_file);Trace_Array(prediction.delta_theta_b_corrected,3);fprintf(s_trace_file,",\"gnss_source\":%u,\"gnss_sequence\":%u,\"gnss_receive_us\":%llu,\"gnss_source_us\":%llu}\n",s_test_gnss_source,s_test_gnss.sequence,(unsigned long long)s_test_gnss.receive_timestamp_us,(unsigned long long)s_test_gnss.sample_timestamp_us);
        Estimator_PredictionProcess(&prediction);Trace_Drain(cycle);Trace_State(cycle);
        TEST_CHECK(s_estimator.kf.predict_count==cycle);
    }
    TEST_CHECK(LoggerBus_OverflowCountGet()==0U);TEST_CHECK(LoggerBus_Count()==0U);
    TEST_CHECK(fclose(s_trace_file)==0);return Test_Finish("kf6_actual_pipeline_trace");
}
