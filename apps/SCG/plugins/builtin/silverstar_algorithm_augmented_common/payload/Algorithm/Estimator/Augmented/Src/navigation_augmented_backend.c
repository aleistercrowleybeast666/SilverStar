#include "system_navigation_backend.h"
#include "navigation_augmented_backend.h"
#include "navigation_replay.h"
#include "navigation_journal.h"
#include "navigation_mag_quality.h"
#include "project_device_instances.h"
#include "system_user_config.h"
#include "system_calibration.h"
#include "system_source_selector.h"
#include "system_gnss_quality.h"
#include "system_navigation_health.h"
#include "system_imu_if.h"
#include "geodesy_local.h"
#include "attitude_frame.h"
#include "silverstar_assert.h"
#include "system_mag_calibration.h"
#include <float.h>
#include <math.h>
#include <string.h>

_Static_assert(SYSTEM_BUILD_AUGMENTED_MODEL>=1U && SYSTEM_BUILD_AUGMENTED_MODEL<=3U,"Unknown augmented model");
_Static_assert((SYSTEM_FUSION_ALGORITHM==SYSTEM_FUSION_ESKF20 && SYSTEM_BUILD_AUGMENTED_MODEL==1U) ||
 (SYSTEM_FUSION_ALGORITHM==SYSTEM_FUSION_INEKF15 && SYSTEM_BUILD_AUGMENTED_MODEL==2U) ||
 (SYSTEM_FUSION_ALGORITHM==SYSTEM_FUSION_INEKF20 && SYSTEM_BUILD_AUGMENTED_MODEL==3U),"Model/algorithm ID mismatch");
/* Static, CPU-only memory. EstimatorTask is the sole owner; no DMA or callbacks. */
static NavigationReplay s_replay;
static NavigationMagQuality s_mag_quality;
static NavigationMagQualityInput s_mag_quality_input;
static NavigationMagQualityOutput s_mag_quality_output;
static const NavigationMagQualityConfig s_mag_quality_config={
    .minimum_samples=SYSTEM_AUG_MAGNETIC_NOISE_MIN_SAMPLES,
    .minimum_duration_us=SYSTEM_AUG_MAGNETIC_NOISE_DURATION_US,
    .maximum_gap_us=SYSTEM_AUG_MAGNETIC_NOISE_MAXIMUM_GAP_US,
    .maximum_sequence_step=SYSTEM_AUG_MAGNETIC_NOISE_MAXIMUM_SEQUENCE_STEP,
    .variance_floor_uT2=SYSTEM_AUG_MAGNETIC_NOISE_VARIANCE_FLOOR_UT2,
    .maximum_std_uT=SYSTEM_AUG_MAGNETIC_NOISE_MAXIMUM_STD_UT,
    .maximum_span_uT=SYSTEM_AUG_MAGNETIC_NOISE_MAXIMUM_SPAN_UT,
    .gyro_max_radps=SYSTEM_AUG_MAGNETIC_STATIONARY_GYRO_MAX_RADPS,
    .accel_tolerance_mps2=SYSTEM_AUG_MAGNETIC_STATIONARY_ACCEL_TOLERANCE_MPS2,
    .accel_span_mps2=SYSTEM_AUG_MAGNETIC_STATIONARY_ACCEL_SPAN_MPS2,
    .gravity_mps2=SYSTEM_AUG_GRAVITY_MPS2,.field_reference_uT=SYSTEM_AUG_MAGNETIC_REFERENCE_UT,
    .field_min_ratio=SYSTEM_AUG_MAGNETIC_MIN_NORM_RATIO,.field_max_ratio=SYSTEM_AUG_MAGNETIC_MAX_NORM_RATIO,
    .delay_us=SYSTEM_AUG_MAGNETIC_TIME_DELAY_US,.uncertainty_us=SYSTEM_AUG_MAGNETIC_TIME_UNCERTAINTY_US,
    .maximum_time_uncertainty_us=SYSTEM_AUG_MAGNETIC_TIME_MAXIMUM_UNCERTAINTY_US,
    .maximum_queue_bytes=SYSTEM_AUG_MAGNETIC_TIME_MAXIMUM_QUEUE_BYTES,
    .delay_bound_verified=SYSTEM_AUG_MAGNETIC_TIME_BOUND_VERIFIED
};

static NavigationJournal s_journal;
static NavigationReplayObservation s_incoming;
static NavigationReplayOutcome s_outcome;
/* Ordinary static SRAM: preserve existing CCM task-stack allocations. */
static NavigationReplayWorkspace s_replay_work;
static GeoLocalFrame s_frame;
static NavigationAugmentedDiagnostics s_diagnostics;
static uint8_t s_active,s_started,s_gnss_source,s_gnss_seen;
static uint32_t s_gnss_sequence,s_input_sequence;
static const double s_density[12]={
 SYSTEM_AUG_GYRO_DENSITY_X,SYSTEM_AUG_GYRO_DENSITY_Y,SYSTEM_AUG_GYRO_DENSITY_Z,
 SYSTEM_AUG_ACCEL_DENSITY_X,SYSTEM_AUG_ACCEL_DENSITY_Y,SYSTEM_AUG_ACCEL_DENSITY_Z,
 SYSTEM_AUG_GYRO_BIAS_RW_DENSITY_X,SYSTEM_AUG_GYRO_BIAS_RW_DENSITY_Y,SYSTEM_AUG_GYRO_BIAS_RW_DENSITY_Z,
 SYSTEM_AUG_ACCEL_BIAS_RW_DENSITY_X,SYSTEM_AUG_ACCEL_BIAS_RW_DENSITY_Y,SYSTEM_AUG_ACCEL_BIAS_RW_DENSITY_Z};
static const double s_p0[20]={SYSTEM_AUG_INITIAL_VARIANCE_0,SYSTEM_AUG_INITIAL_VARIANCE_1,SYSTEM_AUG_INITIAL_VARIANCE_2,
 SYSTEM_AUG_INITIAL_VARIANCE_3,SYSTEM_AUG_INITIAL_VARIANCE_4,SYSTEM_AUG_INITIAL_VARIANCE_5,
 SYSTEM_AUG_INITIAL_VARIANCE_6,SYSTEM_AUG_INITIAL_VARIANCE_7,SYSTEM_AUG_INITIAL_VARIANCE_8,
 SYSTEM_AUG_INITIAL_VARIANCE_9,SYSTEM_AUG_INITIAL_VARIANCE_10,SYSTEM_AUG_INITIAL_VARIANCE_11,
 SYSTEM_AUG_INITIAL_VARIANCE_12,SYSTEM_AUG_INITIAL_VARIANCE_13,SYSTEM_AUG_INITIAL_VARIANCE_14,
 SYSTEM_AUG_INITIAL_VARIANCE_15,SYSTEM_AUG_INITIAL_VARIANCE_16,SYSTEM_AUG_INITIAL_VARIANCE_17,
 SYSTEM_AUG_INITIAL_VARIANCE_18,SYSTEM_AUG_INITIAL_VARIANCE_19
};
static NavigationMagCorrection s_mag_correction;
static uint16_t s_mag_physical,s_mag_descriptor;
static uint32_t s_mag_generation,s_mag_sequence;
static uint8_t s_mag_seen;
static uint32_t s_unadmitted_rejections[3];
static int32_t s_origin_geodetic[3];

static uint8_t Backend_AdmittedResult(NavigationSessionResult result)
{
    return (uint8_t)(result==NavigationSessionResult_Ok || result==NavigationSessionResult_RejectedNis ||
        result==NavigationSessionResult_RejectedCorrection || result==NavigationSessionResult_FieldRejected);
}

static void Backend_JournalResult(NavigationJournalResult result)
{ if(result!=NavigationJournalResult_Ok) { s_diagnostics.journal_failures++; } }

static uint32_t Backend_Dimension(void)
{ return SYSTEM_BUILD_AUGMENTED_MODEL==2U?15U:20U; }

static uint8_t Backend_QuaternionMatrix(const float q[4],double r[9])
{
    double n=0.0,w,x,y,z;
    for(uint32_t i=0;i<4U;i++) { if(!isfinite(q[i])) { return 0U; } n+=(double)q[i]*(double)q[i]; }
    if(!isfinite(n) || n<0.5 || n>1.5) { return 0U; }
    n=sqrt(n);w=(double)q[0]/n;x=(double)q[1]/n;y=(double)q[2]/n;z=(double)q[3]/n;
    r[0]=1-2*(y*y+z*z);r[1]=2*(x*y-w*z);r[2]=2*(x*z+w*y);
    r[3]=2*(x*y+w*z);r[4]=1-2*(x*x+z*z);r[5]=2*(y*z-w*x);
    r[6]=2*(x*z-w*y);r[7]=2*(y*z+w*x);r[8]=1-2*(x*x+y*y);
    return 1U;
}

static uint8_t Backend_ConfigurationValid(void)
{
    if(SYSTEM_AUG_INITIALIZATION_CONFIRMED!=1U || SYSTEM_AUG_GNSS_IMU_COLOCATED_CONFIRMED!=1U || SYSTEM_AUG_SOFTWARE_VALIDATION_BUILD!=1U ||
       !isfinite(SYSTEM_AUG_GRAVITY_MPS2) || SYSTEM_AUG_GRAVITY_MPS2<=0 ||
       !isfinite(SYSTEM_AUG_POSITION_NIS_GATE) || SYSTEM_AUG_POSITION_NIS_GATE<=0 ||
       !isfinite(SYSTEM_AUG_VELOCITY_NIS_GATE) || SYSTEM_AUG_VELOCITY_NIS_GATE<=0) { return 0U; }
    for(uint32_t i=0;i<Backend_Dimension();i++) { if(!isfinite(s_p0[i]) || s_p0[i]<=0) { return 0U; } }
    for(uint32_t i=0;i<12U;i++) { if(!isfinite(s_density[i]) || s_density[i]<0) { return 0U; } }
    if (SYSTEM_BUILD_AUGMENTED_MODEL != 2U) {
    if(!isfinite(SYSTEM_AUG_MAGNETIC_REFERENCE_UT) || SYSTEM_AUG_MAGNETIC_REFERENCE_UT<=0 ||
       !isfinite(SYSTEM_AUG_MAGNETIC_NIS_GATE) || SYSTEM_AUG_MAGNETIC_NIS_GATE<=0 ||
       !isfinite(SYSTEM_AUG_MAGNETIC_MIN_NORM_RATIO) || SYSTEM_AUG_MAGNETIC_MIN_NORM_RATIO<=0 ||
       !isfinite(SYSTEM_AUG_MAGNETIC_MAX_NORM_RATIO) || SYSTEM_AUG_MAGNETIC_MAX_NORM_RATIO<=SYSTEM_AUG_MAGNETIC_MIN_NORM_RATIO) { return 0U; }
    }
    return 1U;
}

void SystemNavigationBackend_Reset(void)
{
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_End(&s_journal,s_replay.current.state_us,0U)); }
    memset(&s_replay,0,sizeof(s_replay));memset(&s_journal,0,sizeof(s_journal));
    memset(&s_frame,0,sizeof(s_frame));memset(&s_diagnostics,0,sizeof(s_diagnostics));
    s_mag_seen=0U;s_mag_sequence=0U;NavigationMagQuality_Reset(&s_mag_quality);
    memset(s_unadmitted_rejections,0,sizeof(s_unadmitted_rejections));
    s_active=0U;s_started=0U;s_gnss_seen=0U;s_input_sequence=0U;
    s_diagnostics.algorithm_id=(uint8_t)SYSTEM_FUSION_ALGORITHM;
    s_diagnostics.error_dimension=(uint8_t)Backend_Dimension();
    s_diagnostics.magnetic_result=NavigationAugmentedMag_Missing;
    if (SYSTEM_BUILD_AUGMENTED_MODEL != 2U) {
    memset(&s_mag_correction,0,sizeof(s_mag_correction));s_mag_generation=0U;s_mag_physical=0U;s_mag_descriptor=0U;
    }
}

/* Native instance adapters omit registry identity; canonical LatestSampleGet
 * adds it but also applies S(m-b). Bind native data to the same Descriptor here
 * without applying calibration twice or granting time/covariance qualification. */
static SystemDeviceResult Backend_MagneticSampleGet(SystemMagnetometerSample *sample)
{
    if(SYSTEM_BUILD_AUGMENTED_MODEL!=2U) {
        SystemDeviceDescriptor descriptor;
        SystemDeviceResult result;
        if(sample==NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        result=ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_MAGNETOMETER,
            (uint8_t)SYSTEM_AUG_MAGNETIC_INSTANCE,&descriptor);
        if(result!=SYSTEM_DEVICE_OK) { return result; }
        if(descriptor.physical_device_id==0U || descriptor.descriptor_id==0U ||
           descriptor.device_class!=SYSTEM_DEVICE_CLASS_MAGNETOMETER ||
           descriptor.instance_id!=SYSTEM_AUG_MAGNETIC_INSTANCE ||
           (descriptor.flags&SYSTEM_DESCRIPTOR_FLAG_ENABLED)==0U) { return SYSTEM_DEVICE_VERIFY_FAILED; }
        result=ProjectMagnetometerInstance_LatestSampleGet(descriptor.instance_id,sample);
        if(result!=SYSTEM_DEVICE_OK) { return result; }
        if((sample->physical_device_id!=0U && sample->physical_device_id!=descriptor.physical_device_id) ||
           (sample->descriptor_id!=0U && sample->descriptor_id!=descriptor.descriptor_id) ||
           (sample->instance_id!=0U && sample->instance_id!=descriptor.instance_id)) { return SYSTEM_DEVICE_VERIFY_FAILED; }
        sample->physical_device_id=descriptor.physical_device_id;
        sample->descriptor_id=descriptor.descriptor_id;sample->instance_id=descriptor.instance_id;
        return SYSTEM_DEVICE_OK;
    }
    (void)sample;
    return SYSTEM_DEVICE_NOT_PRESENT;
}

static void Backend_MagneticBind(NavigationInputIdentity *identity)
{
    if (SYSTEM_BUILD_AUGMENTED_MODEL != 2U) {
    SystemMagCalibrationSnapshot calibration;
    SystemMagnetometerSample sample;
    s_diagnostics.magnetic_result=NavigationAugmentedMag_UnboundCalibration;
    if(Backend_MagneticSampleGet(&sample)!=SYSTEM_DEVICE_OK ||
       sample.instance_id!=SYSTEM_AUG_MAGNETIC_INSTANCE ||
       SystemMagCalibration_SnapshotGet(sample.instance_id,&calibration)!=SystemMagCalibrationResult_Ok ||
       calibration.status.active!=1U || calibration.status.physical_device_id!=sample.physical_device_id) { return; }
    s_mag_physical=sample.physical_device_id;s_mag_descriptor=sample.descriptor_id;s_mag_generation=calibration.status.generation;
    memcpy(s_mag_correction.bias_uT,calibration.bias,sizeof(s_mag_correction.bias_uT));
    memcpy(s_mag_correction.soft_iron,calibration.matrix,sizeof(s_mag_correction.soft_iron));
    s_mag_correction.reference_uT=SYSTEM_AUG_MAGNETIC_REFERENCE_UT;
    s_mag_correction.minimum_norm_ratio=SYSTEM_AUG_MAGNETIC_MIN_NORM_RATIO;
    s_mag_correction.maximum_norm_ratio=SYSTEM_AUG_MAGNETIC_MAX_NORM_RATIO;
    identity->source=((uint32_t)s_mag_physical<<8U)|sample.instance_id;identity->calibration=s_mag_generation;
    s_diagnostics.magnetic_bound=1U;s_diagnostics.magnetic_result=NavigationAugmentedMag_UntrustedClock;
    } else {
    (void)identity;
    }
}

static uint8_t Backend_InitialBuild(const float q_nb[4],const SystemGnssSample *origin)
{
    NavigationState *initial=&s_replay_work.session.staged;
    memset(initial,0,sizeof(*initial));initial->model=(NavigationModel)SYSTEM_BUILD_AUGMENTED_MODEL;
    if(!Backend_QuaternionMatrix(q_nb,initial->rotation)) { return 0U; }
    for(uint32_t i=0;i<Backend_Dimension();i++) { initial->covariance[i*20U+i]=s_p0[i]; }
    if(origin->velocity_valid_mask!=7U) { return 0U; }
    for(uint32_t i=0;i<3U;i++) { initial->velocity[i]=(double)origin->velocity_enu_mps[i]; }
    initial->gyro_bias[0]=SYSTEM_AUG_INITIAL_GYRO_BIAS_X;initial->gyro_bias[1]=SYSTEM_AUG_INITIAL_GYRO_BIAS_Y;initial->gyro_bias[2]=SYSTEM_AUG_INITIAL_GYRO_BIAS_Z;
    initial->accel_bias[0]=SYSTEM_AUG_INITIAL_ACCEL_BIAS_X;initial->accel_bias[1]=SYSTEM_AUG_INITIAL_ACCEL_BIAS_Y;initial->accel_bias[2]=SYSTEM_AUG_INITIAL_ACCEL_BIAS_Z;
    if (SYSTEM_BUILD_AUGMENTED_MODEL != 2U) {
    const float installation[4]={SYSTEM_AUG_INSTALLATION_Q_0,SYSTEM_AUG_INSTALLATION_Q_1,SYSTEM_AUG_INSTALLATION_Q_2,SYSTEM_AUG_INSTALLATION_Q_3};
    if(!Backend_QuaternionMatrix(installation,initial->installation)) { return 0U; }
    initial->inclination=SYSTEM_AUG_INCLINATION_RAD;initial->declination=SYSTEM_AUG_DECLINATION_RAD;
    }
    return 1U;
}

SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],const SystemGnssSample *origin,
 float barometer_origin_m,uint8_t barometer_origin_valid,uint32_t generation,uint8_t activate)
{
    NavigationInputIdentity imu={0},observations[3]={{0}};uint8_t source;
    SystemNavigationBackend_Reset();
    if(q_nb==NULL || origin==NULL || activate>1U || barometer_origin_valid>1U || !isfinite(barometer_origin_m)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if(!Backend_ConfigurationValid() || !SystemCalibration_IsReady() ||
       SystemSourceSelector_ImuActiveInstanceGet(&source)!=SYSTEM_DEVICE_OK || origin->position_usable!=1U ||
       SystemSourceSelector_GnssActiveInstanceGet(&s_gnss_source)!=SYSTEM_DEVICE_OK ||
       !GeoLocalFrame_Init(&s_frame,origin->latitude_e7,origin->longitude_e7,origin->ellipsoid_height_mm) ||
       !Backend_InitialBuild(q_nb,origin)) { return SYSTEM_DEVICE_NOT_READY; }
    imu.epoch=generation;imu.source=source;imu.calibration=SystemCalibration_GenerationGet();
    for(uint32_t i=0;i<3U;i++) { observations[i].epoch=generation; }
    observations[0].source=s_gnss_source;observations[1].source=s_gnss_source;
    Backend_MagneticBind(&observations[2]);
    s_diagnostics.last_result=NavigationSession_Initialize(&s_replay.current,&s_replay_work.session,&s_replay_work.session.staged,0U,&imu,observations);
    if(s_diagnostics.last_result!=NavigationSessionResult_Ok) { return SYSTEM_DEVICE_NOT_READY; }
    s_diagnostics.generation=generation;s_diagnostics.calibration_generation=imu.calibration;s_active=activate;
    s_origin_geodetic[0]=origin->latitude_e7;s_origin_geodetic[1]=origin->longitude_e7;s_origin_geodetic[2]=origin->ellipsoid_height_mm;
    SystemNavigationHealth_Reset(0U);
    return SYSTEM_DEVICE_OK;
}

void SystemNavigationBackend_RecordedSeal(uint32_t reason)
{
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_End(&s_journal,s_replay.current.state_us,0x100U+reason)); }
}

void SystemNavigationBackend_IntervalStartSet(SystemInertialIncrement *input,uint64_t start_us)
{
    SILVERSTAR_ASSERT(input!=NULL,SILVERSTAR_ASSERT_MODULE_ALGORITHM,SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    input->interval_start_timestamp_us=start_us;
}

void SystemNavigationBackend_BodyInputFill(SystemInertialIncrement *input,const float *gyro_pair,const float *accel_pair,uint32_t quality_flags)
{
    SILVERSTAR_ASSERT(input!=NULL && gyro_pair!=NULL && accel_pair!=NULL,SILVERSTAR_ASSERT_MODULE_ALGORITHM,SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    memcpy(input->body_gyro_radps,gyro_pair,sizeof(input->body_gyro_radps));memcpy(input->body_accel_mps2,accel_pair,sizeof(input->body_accel_mps2));input->quality_flags=quality_flags;
}

static SystemDeviceResult Backend_Fault(EstimatorOutputSnapshot *output,NavigationSessionResult reason)
{
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_End(&s_journal,s_replay.current.state_us,(uint32_t)reason)); }
    s_active=0U;s_replay.current.initialized=0U;s_diagnostics.last_result=reason;
    if(output!=NULL) { output->initialized=0U;output->mission_running=0U;output->health_flags|=ESTIMATOR_HEALTH_KF_NUMERIC_ERROR; }
    return SYSTEM_DEVICE_VERIFY_FAILED;
}

static void Backend_HealthPublish(const NavigationInputEvent *event,uint8_t velocity,uint8_t physical,NavigationSessionResult result)
{
    SystemNavigationFusionEvidence evidence={0};
    evidence.receive_us=event->receive_us;evidence.measurement_us=event->sample_us;evidence.evaluation_us=s_replay.current.state_us;
    evidence.sequence=event->sequence;evidence.source=s_gnss_source;evidence.physically_valid=physical;
    evidence.attempted=(uint8_t)(result==NavigationSessionResult_Ok || result==NavigationSessionResult_RejectedNis || result==NavigationSessionResult_RejectedCorrection);
    evidence.effective_update=(uint8_t)(result==NavigationSessionResult_Ok);/* Session result codes are private; 5 means MODEL_MISMATCH in public health. */
    evidence.reason=result==NavigationSessionResult_Ok?0U:0x50U;evidence.variance_scale=1.0f;
    evidence.nis=evidence.attempted?(float)s_replay_work.session.core.nis:0.0f;
    for(uint8_t i=0U;i<2U;i++) {
        if(SystemNavigationHealth_Observe((uint8_t)((velocity?2U:0U)+i),&evidence)!=SYSTEM_DEVICE_OK) { s_diagnostics.last_result=NavigationSessionResult_InvalidState; }
    }
}

static void Backend_GnssVector(const SystemGnssSample *sample,const float position[3],uint8_t velocity,EstimatorOutputSnapshot *output)
{
    NavigationInputEvent event={0};double measured[3],covariance[9]={0};NavigationSessionResult result;uint8_t valid;
    event.identity=s_replay.current.observation[velocity?1U:0U].identity;event.sample_us=sample->sample_timestamp_us;
    event.receive_us=sample->receive_timestamp_us;event.sequence=sample->sequence;event.timestamp_trusted=sample->measurement_timestamp_trusted;
    valid=(uint8_t)((sample->valid_group_mask&(velocity?12U:3U))==(velocity?12U:3U));
    uint32_t required_accuracy=velocity?SYSTEM_GNSS_FIELD_SPEED_ACCURACY:(SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY|SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY);
    if((sample->supported_fields&sample->valid_fields&required_accuracy)!=required_accuracy) { valid=0U; }
    for(uint32_t i=0;i<3U;i++) {
        measured[i]=velocity?sample->velocity_enu_mps[i]:position[i];
        double sigma=i==2U?sample->vertical_accuracy_m:sample->horizontal_accuracy_m;
        covariance[i*3U+i]=velocity?(double)sample->velocity_variance_m2ps2[i]:sigma*sigma;
        if((!velocity && (!isfinite(sigma) || sigma<=0)) || !isfinite(measured[i]) || !isfinite(covariance[i*3U+i]) || covariance[i*3U+i]<=0) { valid=0U; }
    }
    memset(&s_incoming,0,sizeof(s_incoming));s_incoming.event=event;s_incoming.kind=velocity?1U:0U;
    s_incoming.admission=valid?0U:1U;
    s_incoming.gate=velocity?SYSTEM_AUG_VELOCITY_NIS_GATE:SYSTEM_AUG_POSITION_NIS_GATE;
    memcpy(s_incoming.measured,measured,sizeof(measured));memcpy(s_incoming.covariance,covariance,sizeof(covariance));
    result=NavigationReplay_Observe(&s_replay,&s_replay_work,&s_incoming,&s_outcome);
    if(!Backend_AdmittedResult(result)) { s_unadmitted_rejections[velocity?1U:0U]++; }
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_Observe(&s_journal,s_replay.current.state_us,&s_incoming,&s_outcome)); }
    s_replay_work.session.core.nis=s_outcome.nis;
    Backend_HealthPublish(&event,velocity,valid,result);s_diagnostics.last_result=result;
    uint8_t attempted=(uint8_t)(result==NavigationSessionResult_Ok || result==NavigationSessionResult_RejectedNis || result==NavigationSessionResult_RejectedCorrection);
    SystemEstimatorMeasurementResult outcome=result==NavigationSessionResult_Ok?SYSTEM_ESTIMATOR_MEAS_ACCEPTED:
        result==NavigationSessionResult_RejectedNis?SYSTEM_ESTIMATOR_MEAS_REJECTED_NIS:
        result==NavigationSessionResult_NumericError?SYSTEM_ESTIMATOR_MEAS_NUMERIC_ERROR:SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    if(velocity) {
        output->measurement_attempt_mask|=ESTIMATOR_ATTEMPT_GNSS_VELOCITY;output->velocity_update_result=outcome;
        if(result==NavigationSessionResult_Ok) { output->gnss_velocity_update_count++; } else { output->velocity_reject_count++; }
        output->last_velocity_nis=attempted?(float)s_replay_work.session.core.nis:NAN;output->velocity_update_dimension=attempted?3U:0U;
    } else {
        output->measurement_attempt_mask|=ESTIMATOR_ATTEMPT_GNSS_POSITION;output->position_update_result=outcome;
        if(result==NavigationSessionResult_Ok) { output->gnss_position_update_count++; } else { output->position_reject_count++; }
        output->last_position_nis=attempted?(float)s_replay_work.session.core.nis:NAN;
    }
}

static void Backend_GnssUpdate(EstimatorOutputSnapshot *output)
{
    SystemGnssSample sample;float position[3]={0};uint8_t source;
    if(SystemSourceSelector_GnssActiveInstanceGet(&source)!=SYSTEM_DEVICE_OK || source!=s_gnss_source) {
        output->health_flags|=ESTIMATOR_HEALTH_GNSS_MEASUREMENT_INVALID;return;
    }
    if(SystemGnss_LatestSampleGet(&sample)!=SYSTEM_DEVICE_OK || sample.receive_timestamp_us>s_replay.current.state_us ||
       (s_gnss_seen && sample.sequence==s_gnss_sequence)) { return; }
    s_gnss_seen=1U;s_gnss_sequence=sample.sequence;
    if(SystemGnssQuality_Evaluate(&sample,s_replay.current.state_us)!=SYSTEM_DEVICE_OK) { sample.valid_group_mask=0U; }
    if(!GeoLocalFrame_ToEnu(&s_frame,sample.latitude_e7,sample.longitude_e7,sample.ellipsoid_height_mm,position)) { sample.valid_group_mask&=(uint8_t)~3U; }
    output->last_gnss_timestamp_us=sample.receive_timestamp_us;output->last_gnss_sequence=sample.sequence;
    memcpy(output->gnss_position_enu_m,position,sizeof(position));memcpy(output->gnss_velocity_enu_mps,sample.velocity_enu_mps,sizeof(sample.velocity_enu_mps));
    Backend_GnssVector(&sample,position,0U,output);
    if(s_diagnostics.last_result==NavigationSessionResult_NumericError || s_diagnostics.last_result==NavigationSessionResult_InvalidState) { (void)Backend_Fault(output,s_diagnostics.last_result);return; }
    Backend_GnssVector(&sample,position,1U,output);
    if(s_diagnostics.last_result==NavigationSessionResult_NumericError || s_diagnostics.last_result==NavigationSessionResult_InvalidState) { (void)Backend_Fault(output,s_diagnostics.last_result); }
}

static uint8_t Backend_StateFloatable(void)
{
    const NavigationState *n=&s_replay.current.navigation;
    for(uint32_t i=0;i<3U;i++) { if(fabs(n->position[i])>(double)FLT_MAX || fabs(n->velocity[i])>(double)FLT_MAX) { return 0U; } }
    for(uint32_t i=0;i<Backend_Dimension();i++) { for(uint32_t j=0;j<Backend_Dimension();j++) {
        if(fabs(n->covariance[i*20U+j])>(double)FLT_MAX/16.0) { return 0U; }
    } }
    return 1U;
}

static double Backend_WorldCovariance(uint32_t row,uint32_t column)
{
    const NavigationState *n=&s_replay.current.navigation;
    if(n->model==NavigationEskf20) { return n->covariance[row*20U+column]; }
    uint32_t rb=row<3U?6U:3U,cb=column<3U?6U:3U;double value=0.0;
    for(uint32_t i=0;i<3U;i++) { for(uint32_t j=0;j<3U;j++) {
        value+=n->rotation[(row%3U)*3U+i]*n->covariance[(rb+i)*20U+cb+j]*n->rotation[(column%3U)*3U+j];
    } }
    return value;
}

SystemDeviceResult SystemNavigationBackend_SnapshotGet(EstimatorOutputSnapshot *output)
{
    float r[3][3],q[4];
    if(output==NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if(s_replay.current.initialized!=1U) { output->initialized=0U;output->mission_running=0U;return SYSTEM_DEVICE_NOT_READY; }
    if(Navigation_Validate(&s_replay.current.navigation,&s_replay_work.session.core)!=NavigationOk || !Backend_StateFloatable()) { return Backend_Fault(output,NavigationSessionResult_InvalidState); }
    for(uint32_t i=0;i<3U;i++) { for(uint32_t j=0;j<3U;j++) { r[i][j]=(float)s_replay.current.navigation.rotation[i*3U+j]; } }
    if(!Attitude_RotationMatrixToQuaternionWxyz((const float (*)[3])r,q)) { return Backend_Fault(output,NavigationSessionResult_NumericError); }
    memcpy(output->q_nb,q,sizeof(q));output->timestamp_us=s_replay.current.state_us;
    for(uint32_t i=0;i<3U;i++) { output->position_enu_m[i]=(float)s_replay.current.navigation.position[i];output->velocity_enu_mps[i]=(float)s_replay.current.navigation.velocity[i]; }
    /* Compatibility snapshot uses [pE,pN,pU,vE,vN,vU], explicitly world ENU. */
    for(uint32_t i=0;i<6U;i++) { for(uint32_t j=0;j<6U;j++) { output->covariance[i][j]=(float)Backend_WorldCovariance(i,j); } output->covariance_diagonal[i]=output->covariance[i][i]; }
    if(s_started) {
        uint32_t accepted[3],rejected[3];uint64_t last[3];
        if(NavigationReplay_CountsGet(&s_replay,accepted,rejected)!=NavigationSessionResult_Ok ||
           NavigationReplay_LastAcceptedGet(&s_replay,last)!=NavigationSessionResult_Ok)
        { return Backend_Fault(output,NavigationSessionResult_InvalidState); }
        output->gnss_position_update_count=accepted[0];output->gnss_velocity_update_count=accepted[1];
        output->position_reject_count=rejected[0]+s_unadmitted_rejections[0];
        output->velocity_reject_count=rejected[1]+s_unadmitted_rejections[1];
        s_diagnostics.magnetic_updates=accepted[2];s_diagnostics.last_magnetic_fusion_us=last[2];
        s_diagnostics.magnetic_rejections=rejected[2]+s_unadmitted_rejections[2];
    }
    output->initialized=1U;output->mission_running=s_active;output->gnss_origin_valid=s_frame.valid;output->baro_origin_valid=0U;
    output->health_flags|=ESTIMATOR_HEALTH_TIMING_UNQUALIFIED;
    if(SystemNavigationHealth_DegradedGet(s_replay.current.state_us)) { output->health_flags|=ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    else { output->health_flags&=~ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    if (SYSTEM_BUILD_AUGMENTED_MODEL != 2U) {
    if(!s_diagnostics.magnetic_bound || s_diagnostics.magnetic_updates==0U || s_replay.current.state_us<s_diagnostics.last_magnetic_fusion_us ||
       s_replay.current.state_us-s_diagnostics.last_magnetic_fusion_us>2000000ULL) { output->health_flags|=ESTIMATOR_HEALTH_MAGNETIC_UNAVAILABLE; }
    else { output->health_flags&=~ESTIMATOR_HEALTH_MAGNETIC_UNAVAILABLE; }
    }
    return SYSTEM_DEVICE_OK;
}

/* JY evidence is processed exactly once by this task, after epoch binding.
 * Native trusted-time stays0; a separately measured, bounded estimate can be
 * admitted under the recorded policy without claiming a hardware sample clock. */
static uint8_t Backend_MagneticQualityApply(SystemMagnetometerSample *sample,
    const NavigationInputIdentity *identity)
{
    if(SYSTEM_BUILD_AUGMENTED_MODEL!=2U) {
        SystemMagCalibrationStatus status;uint32_t mode=1U;
        NavigationMagQualityResult result=NavigationMagQualityResult_Ok;
        (void)memset(&s_mag_quality_input,0,sizeof(s_mag_quality_input));
        (void)memset(&s_mag_quality_output,0,sizeof(s_mag_quality_output));
        (void)memset(&status,0,sizeof(status));
        s_mag_quality_input.decode_us=sample->decode_timestamp_us;s_mag_quality_input.now_us=sample->processing_timestamp_us;
        s_mag_quality_input.accel_decode_us=sample->accel_decode_timestamp_us;
        s_mag_quality_input.gyro_decode_us=sample->gyro_decode_timestamp_us;
        s_mag_quality_input.sequence=sample->sequence;s_mag_quality_input.transport_epoch=sample->transport_epoch;
        s_mag_quality_input.queue_bytes=sample->decode_queue_bytes;s_mag_quality_input.decode_span_us=sample->decode_span_us;
        s_mag_quality_input.transport_valid=sample->transport_evidence_valid;s_mag_quality_input.imu_valid=sample->imu_evidence_valid;
        (void)memcpy(s_mag_quality_input.sensor_uT,sample->magnetic_field_b_uT,sizeof(s_mag_quality_input.sensor_uT));
        (void)memcpy(s_mag_quality_input.accel_mps2,sample->accel_sensor_mps2,sizeof(s_mag_quality_input.accel_mps2));
        (void)memcpy(s_mag_quality_input.gyro_radps,sample->gyro_sensor_radps,sizeof(s_mag_quality_input.gyro_radps));
        if(!s_diagnostics.magnetic_bound ||
           SystemMagCalibration_StatusGet(sample->instance_id,&status)!=SystemMagCalibrationResult_Ok ||
           status.active!=1U || status.generation!=s_mag_generation || status.physical_device_id!=s_mag_physical) {
            mode=2U;s_mag_quality_output.flags=NAVIGATION_MAG_Q_CALIBRATION;
        } else if(sample->measurement_timestamp_trusted!=0U || sample->calibration_valid!=0U ||
            (sample->valid_mask&(SYSTEM_MAG_VALID_PHYSICAL_UNIT|SYSTEM_MAG_VALID_CALIBRATED))!=SYSTEM_MAG_VALID_PHYSICAL_UNIT) {
            mode=2U;s_mag_quality_output.flags=NAVIGATION_MAG_Q_INPUT;
        }
        s_mag_quality_input.calibration_generation=status.generation;
        if(mode==1U) {
            for(uint32_t i=0U;i<3U;i++) {
                for(uint32_t j=0U;j<3U;j++) {
                    s_mag_quality_input.corrected_uT[i]+=s_mag_correction.soft_iron[i*3U+j]*
                        (sample->magnetic_field_b_uT[j]-s_mag_correction.bias_uT[j]);
                }
            }
            result=NavigationMagQuality_Process(&s_mag_quality,&s_mag_quality_config,&s_mag_quality_input,&s_mag_quality_output);
        } else {
            NavigationMagQuality_Reset(&s_mag_quality);s_mag_quality_output.sample_us=sample->sample_timestamp_us;
            s_mag_quality_output.uncertainty_us=UINT32_MAX;s_mag_quality_output.calibration_generation=status.generation;
        }
        sample->sample_timestamp_us=s_mag_quality_output.sample_us;
        sample->covariance_valid=(uint8_t)s_mag_quality_output.covariance_valid;
        (void)memcpy(sample->covariance_sensor_uT2,s_mag_quality_output.covariance_sensor_uT2,sizeof(sample->covariance_sensor_uT2));
        if(s_journal.active) { Backend_JournalResult(NavigationJournal_Quality(&s_journal,s_replay.current.state_us,identity,mode,
            sample->measurement_timestamp_trusted,result,&s_mag_quality_config,&s_mag_quality_input,&s_mag_quality_output)); }
        if(result==NavigationMagQualityResult_InvalidState) {
            s_diagnostics.magnetic_bound=0U;s_mag_quality_output.time_admitted=0U;
            s_diagnostics.last_result=NavigationSessionResult_InvalidState;
        }
        return (uint8_t)s_mag_quality_output.time_admitted;
    }
    (void)sample;(void)identity;return 0U;
}

static NavigationSessionResult Backend_MagneticBoundaryReject(const NavigationAugmentedMagneticInput *input,NavigationSessionResult result);

static void Backend_MagneticPoll(EstimatorOutputSnapshot *output)
{
    if(SYSTEM_BUILD_AUGMENTED_MODEL!=2U) {
        SystemMagnetometerSample sample;NavigationAugmentedMagneticInput input;
        if(Backend_MagneticSampleGet(&sample)!=SYSTEM_DEVICE_OK ||
           sample.receive_timestamp_us>s_replay.current.state_us || (s_mag_seen && s_mag_sequence==sample.sequence)) { return; }
        s_mag_seen=1U;s_mag_sequence=sample.sequence;memset(&input,0,sizeof(input));
        input.event.identity=s_replay.current.observation[2].identity;
        input.event.identity.source=((uint32_t)sample.physical_device_id<<8U)|sample.instance_id;
        uint8_t estimated_admission=0U;
        if(sample.observation_quality_source==1U) { estimated_admission=Backend_MagneticQualityApply(&sample,&input.event.identity); }
        input.event.sample_us=sample.sample_timestamp_us;input.event.receive_us=sample.receive_timestamp_us;
        input.event.sequence=sample.sequence;input.event.timestamp_trusted=sample.observation_quality_source==1U?estimated_admission:sample.measurement_timestamp_trusted;
        input.physical_device_id=sample.physical_device_id;input.descriptor_id=sample.descriptor_id;
        memcpy(input.sensor_uT,sample.magnetic_field_b_uT,sizeof(input.sensor_uT));
        if(sample.covariance_valid==1U) { memcpy(input.covariance_sensor_uT2,sample.covariance_sensor_uT2,sizeof(input.covariance_sensor_uT2)); }
        input.stage=((sample.valid_mask&SYSTEM_MAG_VALID_PHYSICAL_UNIT)!=0U &&
            (sample.valid_mask&SYSTEM_MAG_VALID_CALIBRATED)==0U && sample.calibration_valid==0U)?
            NavigationMagStage_SensorPhysical:NavigationMagStage_BodyCorrected;
        if(s_diagnostics.last_result==NavigationSessionResult_InvalidState) {
            output->health_flags|=ESTIMATOR_HEALTH_MAGNETIC_UNAVAILABLE;
            s_diagnostics.last_result=Backend_MagneticBoundaryReject(&input,NavigationSessionResult_InvalidState);
        } else if(sample.observation_quality_source==1U && input.event.timestamp_trusted==1U && sample.covariance_valid==0U) {
            /* Missing empirical R is a known inadmissible source field, not a
             * reason to replay the entire history before rejecting zero R. */
            s_diagnostics.last_result=Backend_MagneticBoundaryReject(&input,NavigationSessionResult_InvalidInput);
        } else { s_diagnostics.last_result=NavigationAugmented_MagneticApply(&input); }
    }
}

SystemDeviceResult SystemNavigationBackend_Predict(const SystemInertialIncrement *input,EstimatorOutputSnapshot *output)
{
    double gyro[6],accel[6],gravity[3]={0,0,-SYSTEM_AUG_GRAVITY_MPS2},previous[3];
    NavigationInputIdentity imu;uint64_t duration,start;uint8_t source;
    if(input==NULL || output==NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if(!s_active || s_replay.current.initialized!=1U) { return SYSTEM_DEVICE_NOT_READY; }
    if(!isfinite(input->dt_s) || input->dt_s<=0 || input->dt_s>0.020001f) { return Backend_Fault(output,NavigationSessionResult_InvalidInput); }
    start=input->interval_start_timestamp_us;
    if(input->timestamp_us<=start) { return Backend_Fault(output,NavigationSessionResult_InvalidInput); }
    duration=input->timestamp_us-start;
    if(duration>20000U || fabs((double)input->dt_s-(double)duration*1.0e-6)>2.0*(double)FLT_EPSILON*(double)duration*1.0e-6) { return Backend_Fault(output,NavigationSessionResult_InvalidInput); }
    if(SystemSourceSelector_ImuActiveInstanceGet(&source)!=SYSTEM_DEVICE_OK || source!=s_replay.current.imu_identity.source ||
       SystemCalibration_GenerationGet()!=s_replay.current.imu_identity.calibration || !SystemCalibration_IsReady()) { return Backend_Fault(output,NavigationSessionResult_IdentityMismatch); }
    if(input->quality_flags!=0U ||
       (s_started && (input->sequence!=s_input_sequence+1U || start!=s_replay.current.state_us))) { return Backend_Fault(output,NavigationSessionResult_InvalidInput); }
    for(uint32_t i=0;i<6U;i++) { gyro[i]=input->body_gyro_radps[i/3U][i%3U];accel[i]=input->body_accel_mps2[i/3U][i%3U]; }
    for(uint32_t i=0;i<3U;i++) { previous[i]=s_replay.current.navigation.velocity[i]; }
    if(!s_started) {
        NavigationInputIdentity observations[3];imu=s_replay.current.imu_identity;
        for(uint32_t i=0U;i<3U;i++) { observations[i]=s_replay.current.observation[i].identity; }
        s_diagnostics.last_result=NavigationReplay_Initialize(&s_replay,&s_replay_work,
            &s_replay.current.navigation,start,&imu,observations,gravity,s_density,250000U);
        if(s_diagnostics.last_result!=NavigationSessionResult_Ok) { return Backend_Fault(output,s_diagnostics.last_result); }
        Backend_JournalResult(NavigationJournal_Initial(&s_journal,&s_replay,s_origin_geodetic,
            s_mag_physical,s_mag_descriptor,s_diagnostics.magnetic_bound));SystemNavigationHealth_EpochSet(start);
    }
    imu=s_replay.current.imu_identity;s_diagnostics.last_result=NavigationReplay_Predict(&s_replay,&s_replay_work,&imu,start,input->timestamp_us,gyro,accel);
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_Predict(&s_journal,&imu,start,input->timestamp_us,gyro,accel,s_diagnostics.last_result)); }
    if(s_diagnostics.last_result!=NavigationSessionResult_Ok) { return Backend_Fault(output,s_diagnostics.last_result); }
    s_started=1U;s_input_sequence=input->sequence;output->measurement_attempt_mask=0U;
    SystemNavigationHealth_ImuQualityRecord(input->quality_flags);
    for(uint32_t i=0;i<3U;i++) { double value=(s_replay.current.navigation.velocity[i]-previous[i])/((double)duration/1000000.0);if(!isfinite(value) || fabs(value)>(double)FLT_MAX) { return Backend_Fault(output,NavigationSessionResult_NumericError); }output->acceleration_enu_mps2[i]=(float)value; }
    Backend_GnssUpdate(output);
    if(s_replay.current.initialized!=1U) { return SYSTEM_DEVICE_VERIFY_FAILED; }
    Backend_MagneticPoll(output);
    if(s_diagnostics.last_result==NavigationSessionResult_NumericError || s_diagnostics.last_result==NavigationSessionResult_InvalidState)
    { return Backend_Fault(output,s_diagnostics.last_result); }
    if(s_replay.current.initialized!=1U) { return SYSTEM_DEVICE_VERIFY_FAILED; }
    output->predict_count++;output->update_sequence++;
    return SystemNavigationBackend_SnapshotGet(output);
}

SystemDeviceResult NavigationAugmented_DiagnosticsGet(NavigationAugmentedDiagnostics *output)
{
    if(output==NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if(s_started && s_replay.current.initialized==1U) {
        uint32_t accepted[3],rejected[3];uint64_t last[3];
        if(NavigationReplay_CountsGet(&s_replay,accepted,rejected)!=NavigationSessionResult_Ok ||
           NavigationReplay_LastAcceptedGet(&s_replay,last)!=NavigationSessionResult_Ok) { return SYSTEM_DEVICE_VERIFY_FAILED; }
        s_diagnostics.magnetic_updates=accepted[2];s_diagnostics.magnetic_rejections=rejected[2]+s_unadmitted_rejections[2];
        s_diagnostics.last_magnetic_fusion_us=last[2];
    }
    s_diagnostics.initialized=s_replay.current.initialized;s_diagnostics.active=s_active;s_diagnostics.state_us=s_replay.current.state_us;
    memcpy(s_diagnostics.gyro_bias,s_replay.current.navigation.gyro_bias,sizeof(s_diagnostics.gyro_bias));
    memcpy(s_diagnostics.accel_bias,s_replay.current.navigation.accel_bias,sizeof(s_diagnostics.accel_bias));
    memcpy(s_diagnostics.installation,s_replay.current.navigation.installation,sizeof(s_diagnostics.installation));
    s_diagnostics.inclination=s_replay.current.navigation.inclination;s_diagnostics.declination=s_replay.current.navigation.declination;
    for(uint32_t i=0;i<20U;i++) { s_diagnostics.covariance_diagonal[i]=i<Backend_Dimension()?s_replay.current.navigation.covariance[i*20U+i]:0.0; }
    *output=s_diagnostics;return SYSTEM_DEVICE_OK;
}

static void Backend_MagneticObservationBuild(const NavigationAugmentedMagneticInput *input)
{
    memset(&s_incoming,0,sizeof(s_incoming));s_incoming.kind=2U;s_incoming.event=input->event;
    s_incoming.gate=SYSTEM_AUG_MAGNETIC_NIS_GATE;s_incoming.stage=input->stage;s_incoming.correction=s_mag_correction;
    memcpy(s_incoming.sensor_uT,input->sensor_uT,sizeof(s_incoming.sensor_uT));
    memcpy(s_incoming.covariance_uT2,input->covariance_sensor_uT2,sizeof(s_incoming.covariance_uT2));
}

static NavigationSessionResult Backend_MagneticBoundaryReject(const NavigationAugmentedMagneticInput *input,NavigationSessionResult reason)
{
    Backend_MagneticObservationBuild(input);s_incoming.admission=(uint32_t)reason;
    s_outcome.result=reason;s_outcome.nis=(double)NAN;s_unadmitted_rejections[2]++;s_diagnostics.last_result=reason;
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_Observe(&s_journal,s_replay.current.state_us,&s_incoming,&s_outcome)); }
    return reason;
}

NavigationSessionResult NavigationAugmented_MagneticApply(const NavigationAugmentedMagneticInput *input)
{
    if (SYSTEM_BUILD_AUGMENTED_MODEL == 2U) {
    (void)input;return NavigationSessionResult_Unsupported;
    } else {
    SystemMagCalibrationStatus status;NavigationSessionResult result;
    if(input==NULL || !s_active || !s_started || s_replay.current.initialized!=1U) { return NavigationSessionResult_InvalidState; }
    if(!s_diagnostics.magnetic_bound) { s_diagnostics.magnetic_result=NavigationAugmentedMag_UnboundCalibration;return Backend_MagneticBoundaryReject(input,NavigationSessionResult_WrongStage); }
    if(SystemMagCalibration_StatusGet((uint8_t)SYSTEM_AUG_MAGNETIC_INSTANCE,&status)!=SystemMagCalibrationResult_Ok ||
       status.active!=1U || status.generation!=s_mag_generation || status.physical_device_id!=s_mag_physical ||
       input->physical_device_id!=s_mag_physical || input->descriptor_id!=s_mag_descriptor) {
        s_diagnostics.magnetic_result=NavigationAugmentedMag_IdentityChanged;s_diagnostics.magnetic_bound=0U;
        return Backend_MagneticBoundaryReject(input,NavigationSessionResult_IdentityMismatch);
    }
    Backend_MagneticObservationBuild(input);
    result=NavigationReplay_Observe(&s_replay,&s_replay_work,&s_incoming,&s_outcome);
    if(!Backend_AdmittedResult(result)) { s_unadmitted_rejections[2]++; }
    if(s_journal.active) { Backend_JournalResult(NavigationJournal_Observe(&s_journal,s_replay.current.state_us,&s_incoming,&s_outcome)); }
    s_diagnostics.last_result=result;
    if(result==NavigationSessionResult_Ok) { s_diagnostics.magnetic_updates++;s_diagnostics.last_magnetic_fusion_us=s_replay.current.state_us;s_diagnostics.magnetic_result=NavigationAugmentedMag_Ok; }
    else { s_diagnostics.magnetic_rejections++;s_diagnostics.magnetic_result=result==NavigationSessionResult_UntrustedTime?NavigationAugmentedMag_UntrustedClock:NavigationAugmentedMag_Rejected; }
    return result;
    }
}
