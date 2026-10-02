#include <math.h>
#include <stdio.h>
#include <string.h>
#include "ins_task.h"
#include "ins_mechanization.h"
#include "system_imu_if.h"
#include "system_calibration.h"
#include "system_estimator_diagnostics.h"
#include "system_navigation_health.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "silverstar_assert.h"

#undef SYSTEM_FUSION_ALGORITHM
#define SYSTEM_FUSION_ALGORITHM TEST_FUSION
typedef SystemImuSample InsImuSample;
static union { InsInertialContext inertial; InsMechanizationContext pure_ins; } s_navigation_input;
static InsOutputSnapshot s_output, s_published_output;
static SystemInsDiagnostics s_diagnostics;
static FlightLogPureInsRecord s_record;
static unsigned int s_predictions, s_logs, s_correction_failure;
static uint8_t s_mission_running = 1U, s_mission_attitude_frozen = 1U, s_input_fault_latched;
static uint32_t s_quality_latch;
static uint32_t InsTask_IrqLock(void) { return 0U; }
static void InsTask_IrqUnlock(uint32_t lock) { (void)lock; }
SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{ memset(status, 0, sizeof(*status)); status->ready=1U; return SYSTEM_DEVICE_OK; }
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{ memset(snapshot, 0, sizeof(*snapshot)); snapshot->initialized=1U;
  snapshot->mission_running=1U; snapshot->predict_count=1U; return 1U; }
void SystemInsDiagnostics_Publish(const SystemInsDiagnostics *snapshot) { s_diagnostics=*snapshot; }
void SystemNavigationHealth_ImuQualityRecord(uint32_t flags) { s_quality_latch |= flags & 0x72U; }
LoggerBusResult LoggerBus_PureInsPush(uint64_t timestamp, uint32_t flags,
                                    const FlightLogPureInsRecord *record)
{ (void)timestamp; (void)flags; s_logs++; s_record=*record; return LOGGER_BUS_RESULT_OK; }
static uint8_t InsTask_SampleCorrect(const InsImuSample *source, InsAlgorithmSample *sample)
{
    memset(sample,0,sizeof(*sample)); sample->timestamp_us=source->sample_timestamp_us;
    memcpy(sample->accel_b_mps2,source->accel_b_mps2,sizeof(sample->accel_b_mps2));
    memcpy(sample->gyro_b_radps,source->gyro_b_radps,sizeof(sample->gyro_b_radps));
    sample->valid_flags=INS_ALGORITHM_VALID_ACCEL|INS_ALGORITHM_VALID_GYRO;
    return s_correction_failure == 0U;
}
static void InsTask_BodyPairBuild(const InsAlgorithmSample *sample) { (void)sample; }

/* REAL_FUNCTIONS: inserted from the generated application, not reimplemented. */

static int Test_Rejection(unsigned int fault)
{
    const float q[4]={1.0f,0.0f,0.0f,0.0f};
    InsImuSample sample={0};
    memset(&s_navigation_input,0,sizeof(s_navigation_input));
    memset(&s_output,0,sizeof(s_output)); memset(&s_record,0,sizeof(s_record));
    s_predictions=0U; s_logs=0U; s_input_fault_latched=0U; s_quality_latch=0U; s_correction_failure=0U;
    s_output.q_nb[0]=1.0f; s_output.velocity_n_mps[0]=2.0f; s_output.position_n_m[0]=3.0f;
    s_output.timestamp_us=999000ULL; s_output.update_seq=7U; s_output.ins_valid=1U;
    if (TEST_FUSION == SYSTEM_FUSION_NONE)
    { InsMechanization_Init(&s_navigation_input.pure_ins,9.78f);
      if (!InsMechanization_ResetNavigationWithAttitude(&s_navigation_input.pure_ins,q)) return 1; }
    sample.accel_b_mps2[2]=9.78f;
    sample.sample_timestamp_us=1000000ULL;
    if (fault==0U) sample.gyro_b_radps[0]=NAN;
    if (fault==1U) sample.accel_b_mps2[0]=INFINITY;
    if (fault==2U) sample.quality_flags=SYSTEM_IMU_QUALITY_CLIPPED;
    if (fault==3U) s_correction_failure=1U;
    InsTask_Propagate(&sample);
    if (s_predictions || !s_input_fault_latched || !s_quality_latch || s_published_output.ins_valid ||
        s_published_output.timestamp_us!=999000ULL || s_published_output.update_seq!=7U ||
        s_published_output.velocity_n_mps[0]!=2.0f || s_published_output.position_n_m[0]!=3.0f ||
        !(s_published_output.health_flags & INS_HEALTH_INVALID_SAMPLE) ||
        s_diagnostics.position_valid || s_diagnostics.velocity_valid || s_diagnostics.quaternion_valid)
        return 1;
    if (TEST_FUSION==SYSTEM_FUSION_NONE && (s_logs!=1U || s_record.ins_valid ||
        !(s_record.health_flags & INS_HEALTH_INVALID_SAMPLE))) return 1;
    if (TEST_FUSION!=SYSTEM_FUSION_NONE && s_logs) return 1;
    sample.gyro_b_radps[0]=0.0f; sample.accel_b_mps2[0]=0.0f;
    sample.quality_flags=0U; s_correction_failure=0U;
    for (unsigned int i=1U;i<15U;i++)
    { sample.sample_timestamp_us=1000000ULL+5000ULL*i; InsTask_Propagate(&sample); }
    return !s_predictions || s_published_output.ins_valid || !s_input_fault_latched ||
        s_diagnostics.position_valid || s_diagnostics.velocity_valid;
}

int main(void)
{
    unsigned int failures=0U;
    for (unsigned int fault=0U;fault<4U;fault++) failures+=(unsigned int)Test_Rejection(fault);
    printf("actual dispatch/publication: fusion=%d cases=4 failures=%u\n",TEST_FUSION,failures);
    return failures!=0U;
}
