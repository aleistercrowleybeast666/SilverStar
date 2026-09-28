#ifndef __NAVIGATION_ESKF_H
#define __NAVIGATION_ESKF_H

#include <stdint.h>

#define NAV_ESKF_DIM 15U
#define NAV_ESKF_AXES 3U
#define NAV_ESKF_OBSERVATIONS 2U
#define NAV_ESKF_REVISION 1U
#define NAV_ESKF_MAX_DT_S 0.02f
#define NAV_ESKF_MAX_INJECTION_RAD 0.35f
#define NAV_ESKF_MAX_GYRO_BIAS_RADPS 1.0f
#define NAV_ESKF_MAX_ACCEL_BIAS_MPS2 5.0f

typedef enum
{
    NAV_ESKF_OK = 0,
    NAV_ESKF_SOFT_WEIGHTED,
    NAV_ESKF_REJECTED_NIS,
    NAV_ESKF_INVALID_INPUT,
    NAV_ESKF_NUMERIC_ERROR,
    NAV_ESKF_MODEL_MISMATCH
} NavigationEskfResult;

typedef struct
{
    float gravity_mps2;
    /* Continuous amplitude densities, squared once to form spectral density. */
    float gyro_noise_density;
    float accel_noise_density;
    float gyro_bias_rw;
    float accel_bias_rw;
    float nis_soft[2];
    float nis_hard[2];
    float maximum_r_scale;
} NavigationEskfConfig;

typedef struct
{
    float position[3];
    float velocity[3];
    float quaternion[4]; /* Hamilton wxyz, q_nb, right local error. */
    float gyro_bias[3];
    float accel_bias[3];
    float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM];
    uint64_t timestamp_us;
    uint32_t source;
    uint32_t generation;
    uint8_t initialized;
} NavigationEskfState;

typedef struct
{
    float gyro_radps[2][3];
    float accel_mps2[2][3];
    float dt_s;
    uint64_t start_us;
    uint64_t end_us;
    uint32_t source;
    uint32_t generation;
    uint32_t quality_flags;
} NavigationEskfBodyInput;

typedef struct
{
    uint8_t group; /* Pos EN, Pos U, Vel EN, Vel U, Baro U. */
    uint8_t physically_valid;
    float observation[2];
    float variance[2]; /* quality/consistency already applied, not sigma. */
    float lever_arm_b_m[3];
    float angular_rate_b_radps[3]; /* calibrated, prior to residual bg. */
} NavigationEskfMeasurement;

typedef struct
{
    float nis;
    float r_scale;
    float innovation[2];
    float effective_variance[2];
    float gain_norm;
    uint8_t dimension;
    NavigationEskfResult result;
} NavigationEskfOutcome;

/* Caller owned, CPU-only, single task. Never allocate on a task stack or in DMA RAM. */
typedef struct
{
    float f[NAV_ESKF_DIM][NAV_ESKF_DIM];
    float transition[NAV_ESKF_DIM][NAV_ESKF_DIM];
    float temporary[NAV_ESKF_DIM][NAV_ESKF_DIM];
    float candidate_p[NAV_ESKF_DIM][NAV_ESKF_DIM];
    float candidate_x[16];
    float correction[NAV_ESKF_DIM];
    float h[2][NAV_ESKF_DIM];
    float gain[NAV_ESKF_DIM][2];
    float innovation_covariance[2][2];
} NavigationEskfWorkspace;

NavigationEskfResult NavigationEskf_Initialize(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const float nominal[16], const float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM],
    uint64_t timestamp_us, uint32_t source, uint32_t generation);
NavigationEskfResult NavigationEskf_Predict(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfBodyInput *input);
NavigationEskfResult NavigationEskf_Update(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfMeasurement *measurement,
    NavigationEskfOutcome *outcome);
NavigationEskfResult NavigationEskf_ConfigValidate(const NavigationEskfConfig *config);

#endif /* __NAVIGATION_ESKF_H */
