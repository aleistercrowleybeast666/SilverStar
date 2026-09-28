#ifndef __ATTITUDE_FRAME_H
#define __ATTITUDE_FRAME_H

#include <stdint.h>

typedef enum
{
    ATTITUDE_YAW_RESULT_OK = 0,
    ATTITUDE_YAW_RESULT_BAD_PARAM,
    ATTITUDE_YAW_RESULT_INVALID_QUATERNION,
    ATTITUDE_YAW_RESULT_SINGULAR
} AttitudeYawResult;

typedef struct
{
    float q_nr[4];
    float q_nb[4];
    float q_previous[4];
    uint32_t alignment_failure_count;
    uint8_t alignment_valid;
    uint8_t output_valid;
} AttitudeFrameContext;

void Attitude_QuaternionMultiply(const float lhs[4],
                                 const float rhs[4],
                                 float out[4]);
uint8_t Attitude_QuaternionNormalize(float q[4]);
void Attitude_QuaternionConjugate(const float q[4], float out[4]);
float Attitude_QuaternionDot(const float a[4], const float b[4]);
uint8_t Attitude_RotationVectorToQuaternion(const float delta_theta[3],
                                            float delta_q[4]);
uint8_t Attitude_PropagateQuaternionBodyIncrement(
    const float q_nb_start[4],
    const float delta_theta_b[3],
    float q_nb_end[4]);
void Attitude_RotateVector(const float q_nb[4],
                           const float vector_b[3],
                           float vector_n[3]);
uint8_t Attitude_RotationMatrixToQuaternionWxyz(
    const float matrix[3][3],
    float q[4]);
AttitudeYawResult Attitude_YawEnuFromQuaternion(
    const float q_nb[4],
    float *yaw_rad);

uint8_t AttitudeFrame_RawSensorToReference(
    const float q_raw_sr[4],
    float q_rs[4]);
uint8_t AttitudeFrame_ComputeBodyToReference(
    const float q_raw_sr[4],
    float q_rb[4]);
uint8_t AttitudeFrame_SixAxisReferenceToNavigationCompute(
    const float q_nb_absolute[4],
    const float q_rb_alignment[4],
    float q_nr[4]);

void AttitudeFrame_Init(AttitudeFrameContext *context);
uint8_t AttitudeFrame_SixAxisAlignmentApply(
    AttitudeFrameContext *context,
    const float q_nr[4],
    const float q_rb_alignment[4],
    const float q_nb_absolute[4]);
uint8_t AttitudeFrame_SixAxisTransform(AttitudeFrameContext *context,
                                       const float q_raw_sr[4],
                                       float q_nb[4]);
uint8_t AttitudeFrame_NineAxisTransform(AttitudeFrameContext *context,
                                        const float q_raw[4],
                                        float q_nb[4]);

#endif /* __ATTITUDE_FRAME_H */
