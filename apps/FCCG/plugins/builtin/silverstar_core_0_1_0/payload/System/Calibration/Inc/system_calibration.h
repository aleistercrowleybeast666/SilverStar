#ifndef __SYSTEM_CALIBRATION_H
#define __SYSTEM_CALIBRATION_H

#include <stdint.h>

#include "system_device_types.h"
#include "imu_six_face_calibration.h"
#include "system_inertial_types.h"

#define SYSTEM_CALIBRATION_FACE_COUNT IMU_SIX_FACE_COUNT
#define SYSTEM_CALIBRATION_FACE_MASK_ALL 0x3FU
#define SYSTEM_CALIBRATION_CAPABILITY_NONE      (1U << 0)
#define SYSTEM_CALIBRATION_CAPABILITY_ONE_FACE  (1U << 1)
#define SYSTEM_CALIBRATION_CAPABILITY_SIX_FACE  (1U << 2)
#define SYSTEM_CALIBRATION_CAPABILITY_MASK_ALL   0x07U
#define SYSTEM_CALIBRATION_CAPABILITY_PROCEDURE_MASK \
    (SYSTEM_CALIBRATION_CAPABILITY_ONE_FACE | \
     SYSTEM_CALIBRATION_CAPABILITY_SIX_FACE)

/* Standalone component tests may select both procedures explicitly. FCCG
 * force-includes the actual project selection before this header. */
#ifndef SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK
#define SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK 0U
#endif
_Static_assert((SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK &
                ~SYSTEM_CALIBRATION_CAPABILITY_PROCEDURE_MASK) == 0U,
               "Calibration build procedure mask contains unknown bits");

typedef enum
{
    SYSTEM_CALIBRATION_MODE_NONE = 0U,
    SYSTEM_CALIBRATION_MODE_ONE_FACE,
    SYSTEM_CALIBRATION_MODE_SIX_FACE,
    SYSTEM_CALIBRATION_MODE_NOT_SELECTED = 0xFFU
} SystemCalibrationMode;

typedef enum
{
    SYSTEM_CALIBRATION_STATE_IDLE = 0U,
    SYSTEM_CALIBRATION_STATE_WAIT_FACE,
    SYSTEM_CALIBRATION_STATE_COLLECTING,
    SYSTEM_CALIBRATION_STATE_CHECKING,
    SYSTEM_CALIBRATION_STATE_READY,
    SYSTEM_CALIBRATION_STATE_FAILED
} SystemCalibrationState;

typedef enum
{
    SYSTEM_CALIBRATION_FACE_X_POSITIVE = 0U,
    SYSTEM_CALIBRATION_FACE_X_NEGATIVE,
    SYSTEM_CALIBRATION_FACE_Y_POSITIVE,
    SYSTEM_CALIBRATION_FACE_Y_NEGATIVE,
    SYSTEM_CALIBRATION_FACE_Z_POSITIVE,
    SYSTEM_CALIBRATION_FACE_Z_NEGATIVE,
    SYSTEM_CALIBRATION_FACE_NONE = 0xFFU
} SystemCalibrationFace;

typedef enum
{
    SYSTEM_CALIBRATION_WAIT_NONE = 0U,
    SYSTEM_CALIBRATION_WAIT_NO_STREAM,
    SYSTEM_CALIBRATION_WAIT_GYRO_MOVING,
    SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE,
    SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION,
    SYSTEM_CALIBRATION_WAIT_VARIANCE,
    SYSTEM_CALIBRATION_WAIT_SAMPLE_GAP
} SystemCalibrationWaitReason;

typedef enum
{
    SYSTEM_CALIBRATION_FACE_RESULT_NONE = 0U,
    SYSTEM_CALIBRATION_FACE_RESULT_FAILED,
    SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE
} SystemCalibrationFaceResult;

typedef struct
{
    SystemCalibrationMode mode;
    float accel_bias_mps2[3];
    float accel_scale[3];
    float gyro_bias_radps[3];
    float gyro_scale[3];
    uint8_t ready;
} SystemCalibrationImuCorrection;

typedef struct
{
    ImuSixFaceMeasurements six_face_measurements;
    SystemCalibrationImuCorrection correction;
    uint32_t samples;
    uint32_t reject_count;
    uint32_t retry_count;
    uint32_t start_sequence;
    uint32_t state_sequence;
    uint32_t face_event_sequence;
    uint32_t diagnostic_sequence;
    SystemCalibrationMode mode;
    SystemCalibrationState state;
    SystemCalibrationFace current_face;
    SystemCalibrationFace last_face;
    SystemCalibrationFace diagnostic_face;
    SystemCalibrationFaceResult last_face_result;
    SystemCalibrationWaitReason wait_reason;
    SystemCalibrationWaitReason diagnostic_reason;
    uint8_t completed_face_mask;
    uint8_t ready;
} SystemCalibrationStatus;

void SystemCalibration_Init(void);
void SystemCalibration_Process(void);
void SystemCalibration_ImuSampleProcess(const SystemInertialSample *sample);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemCalibration_Start(
    SystemCalibrationMode mode);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemCalibration_FaceCollect(
    SystemCalibrationFace face);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemCalibration_Stop(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemCalibration_Reset(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemCalibration_StatusGet(
    SystemCalibrationStatus *status);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
SystemCalibration_ImuCorrectionApply(
    const float raw_accel_b_mps2[3],
    const float raw_gyro_b_radps[3],
    const SystemCalibrationImuCorrection *correction,
    float corrected_accel_b_mps2[3],
    float corrected_gyro_b_radps[3]);
uint8_t SystemCalibration_CapabilityMaskGet(void);
uint8_t SystemCalibration_IsReady(void);
uint32_t SystemCalibration_GenerationGet(void);
const char *SystemCalibration_ModeText(SystemCalibrationMode mode);
const char *SystemCalibration_StateText(SystemCalibrationState state);
const char *SystemCalibration_FaceText(SystemCalibrationFace face);
const char *SystemCalibration_WaitReasonText(
    SystemCalibrationWaitReason reason);
const char *SystemCalibration_FaceResultText(
    SystemCalibrationFaceResult result);

#endif /* __SYSTEM_CALIBRATION_H */
