#include "control_research.h"
#include "estimator_task.h"
#include "system_inertial.h"
#include "system_calibration.h"
#include "system_source_selector.h"
#include "system_lifecycle.h"
#include "system_time.h"
#include <stddef.h>
#include <string.h>
#include <math.h>

static ControlResearchResult ControlResearch_ImuRead(ControlResearchInput *input)
{
    SystemInertialSample sample;
    SystemCalibrationImuCorrection correction;
    float accel[3], gyro[3];
    uint32_t generation = SystemCalibration_GenerationGet();
    if ((SystemInertial_LatestGet(&sample) != SYSTEM_DEVICE_OK) ||
        (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK) || (correction.ready != 1U))
    { return ControlResearchResult_Unavailable; }
    if (((sample.valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)) !=
        (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)) || (sample.quality_flags != 0U) ||
        (sample.canonical_source_valid != 1U)) { return ControlResearchResult_InvalidInput; }
    if (SystemCalibration_ImuCorrectionApply(sample.accel_b_mps2, sample.gyro_b_radps,
        &correction, accel, gyro) != SYSTEM_DEVICE_OK) { return ControlResearchResult_InvalidInput; }
    if ((generation == 0U) || (generation != SystemCalibration_GenerationGet()))
    { return ControlResearchResult_SourceChanged; }
    input->imu_us = sample.sample_timestamp_us;
    input->imu_sequence = sample.sequence;
    input->rate_radps = gyro[1];
    input->imu_provenance.calibration_generation = generation;
    input->imu_provenance.source_instance = sample.canonical_source_instance;
    input->imu_provenance.sensor_epoch = SystemInertialSample_EpochGet(&sample);
    input->imu_provenance.valid = 1U;
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearch_InputRead(ControlResearchInput *input)
{
    EstimatorOutputSnapshot navigation;
    SystemImuEpochToken epoch = {0};
    uint8_t source = 0U;
    if (input == NULL) { return ControlResearchResult_InvalidInput; }
    (void)memset(input, 0, sizeof(*input));
    if ((SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U) &&
        (SystemImuEpoch_StartReserve(&epoch) != SYSTEM_DEVICE_OK)) { return ControlResearchResult_Unavailable; }
    if ((Estimator_GetLatestSnapshot(&navigation) == 0U) ||
        (navigation.initialized != 1U) || (navigation.mission_running != 1U) ||
        (navigation.health_flags != ESTIMATOR_HEALTH_NONE) || (navigation.attitude_provenance.valid != 1U))
    { return ControlResearchResult_Unavailable; }
    input->navigation_us = navigation.timestamp_us;
    input->navigation_sequence = navigation.update_sequence;
    input->navigation_provenance = navigation.attitude_provenance;
    (void)memcpy(input->q_nb, navigation.q_nb, sizeof(input->q_nb));
    ControlResearchResult result = ControlResearch_ImuRead(input);
    if (result != ControlResearchResult_Ok) { return result; }
    if ((SystemSourceSelector_ImuActiveInstanceGet(&source) != SYSTEM_DEVICE_OK) ||
        (source != input->imu_provenance.source_instance) ||
        (SystemCalibration_GenerationGet() != input->imu_provenance.calibration_generation))
    { return ControlResearchResult_SourceChanged; }
    if ((SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U) &&
        ((SystemImuEpoch_StartIsCurrent(&epoch) == 0U) ||
         (epoch.epoch != input->imu_provenance.sensor_epoch) ||
         (epoch.calibration_generation != input->imu_provenance.calibration_generation)))
    { return ControlResearchResult_SourceChanged; }
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearch_RuntimeProcess(void)
{
    ControlResearchInput input = {0};
    SystemMissionControlWindowResult window = SystemMissionProcess_ControlWindowGet();
    ControlResearchResult result = ControlResearchResult_Unavailable;
    if (window == SystemMissionControlWindowResult_Active) { result = ControlResearch_InputRead(&input); }
    return ControlResearch_Process(SystemTime_GetMonotonicUs(), window, result, &input);
}

ControlResearchResult ControlResearch_PublicationCheck(const SystemNavigationProvenance *provenance,
    uint64_t navigation_us, uint32_t navigation_sequence)
{
    SystemInertialSample current;
    if ((provenance == NULL) ||
        (EstimatorTask_ControlProvenanceCheck(provenance, navigation_us, navigation_sequence) != SYSTEM_DEVICE_OK))
    { return ControlResearchResult_Unavailable; }
    if ((SystemInertial_LatestGet(&current) != SYSTEM_DEVICE_OK) || (current.canonical_source_valid != 1U) ||
        (current.canonical_source_instance != provenance->source_instance) ||
        (SystemInertialSample_EpochGet(&current) != provenance->sensor_epoch) ||
        (SystemCalibration_GenerationGet() != provenance->calibration_generation) ||
        (SystemCalibration_IsReady() == 0U)) { return ControlResearchResult_SourceChanged; }
    uint64_t now_us = SystemTime_GetMonotonicUs();
    if ((current.sample_timestamp_us == 0U) || (current.sample_timestamp_us > now_us) ||
        (now_us - current.sample_timestamp_us > CONTROL_RESEARCH_INPUT_AGE_US) ||
        ((current.valid_mask & SYSTEM_INERTIAL_VALID_GYRO) == 0U) || (current.quality_flags != 0U) ||
        !isfinite(current.gyro_b_radps[1])) { return ControlResearchResult_Stale; }
    if ((SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U) &&
        ((SystemImuEpoch_IsQualified() == 0U) || (SystemImuEpoch_SampleIsCurrent(
            SystemInertialSample_SourceGet(&current), provenance->sensor_epoch) == 0U)))
    { return ControlResearchResult_SourceChanged; }
    return ControlResearchResult_Ok;
}
