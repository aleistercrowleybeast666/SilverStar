/* Host-only explicit experimental parameters. No production defaults. */
#include "navigation_eskf_recovery.h"

#include <stddef.h>
#include <string.h>

int Test_Prepare(NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    NavigationEskfConfig *filter, NavigationEskfRecoveryConfig *config,
    NavigationEskfRecoveryReceiveState *receive, NavigationEskfRecoveryReplayState *policy,
    const float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM])
{
    const NavigationEskfConfig experimental = { .gravity_mps2 = 9.80665f,
        .gyro_noise_density = 0.002f, .accel_noise_density = 0.02f,
        .gyro_bias_rw = 0.0001f, .accel_bias_rw = 0.001f,
        .nis_soft = {6.0f, 9.0f}, .nis_hard = {20.0f, 25.0f}, .maximum_r_scale = 4.0f };
    float nominal[16] = {0};
    *filter = experimental; memset(config, 0, sizeof(*config));
    config->identity = 17U; config->loss_gap_us = 1000000U;
    config->stable_span_us = 400000U; config->maximum_interval_us = 250000U;
    config->cooldown_us = 500000U; config->stable_count = 3U;
    config->reject_count = 2U; config->confirmation_count = 2U; config->maximum_attempts = 2U;
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++)
    { config->scale[i] = 2.0f; config->variance_cap[i] = 1000000.0f; }
    nominal[6] = 1.0f;
    if (NavigationEskf_Initialize(state, workspace, nominal, covariance, 1000000U, 13U, 7U) != NAV_ESKF_OK)
    { return -1; }
    return (int)NavigationEskfRecovery_Reset(receive, policy, config, 7U, 11U, 1U);
}

size_t Test_Size(uint32_t index)
{
    const size_t sizes[15] = {sizeof(NavigationEskfState), sizeof(NavigationEskfWorkspace),
        sizeof(NavigationEskfConfig), sizeof(NavigationEskfRecoveryConfig),
        sizeof(NavigationEskfRecoveryReceipt), sizeof(NavigationEskfRecoveryQualification),
        sizeof(NavigationEskfRecoveryReceiveState), sizeof(NavigationEskfRecoveryPacket),
        sizeof(NavigationEskfRecoveryEvidence), sizeof(NavigationEskfRecoveryGroup),
        sizeof(NavigationEskfRecoveryReplayState), sizeof(NavigationEskfRecoveryEvent),
        sizeof(NavigationEskfRecoveryTransaction), sizeof(NavigationEskfRecoveryOutput),
        sizeof(NavigationEskfMeasurement)};
    return index < 15U ? sizes[index] : 0U;
}

int Test_Enum(uint32_t index)
{
    const int values[19] = {NAV_ESKF_RECOVERY_COMPLETE, NAV_ESKF_RECOVERY_DUPLICATE,
        NAV_ESKF_RECOVERY_DISCONTINUITY, NAV_ESKF_RECOVERY_INELIGIBLE, NAV_ESKF_RECOVERY_EXHAUSTED,
        NAV_ESKF_RECOVERY_INVALID_ARGUMENT, NAV_ESKF_RECOVERY_NUMERIC_ERROR, NAV_ESKF_RECOVERY_MODEL_MISMATCH,
        NAV_ESKF_RECOVERY_ACTION_NONE, NAV_ESKF_RECOVERY_ACTION_PENDING,
        NAV_ESKF_RECOVERY_ACTION_SCALED, NAV_ESKF_RECOVERY_ACTION_LIMITED,
        NAV_ESKF_OK, NAV_ESKF_SOFT_WEIGHTED, NAV_ESKF_REJECTED_NIS, NAV_ESKF_INVALID_INPUT,
        NAV_ESKF_NUMERIC_ERROR, NAV_ESKF_MODEL_MISMATCH, NAV_ESKF_RECOVERY_MEASUREMENT_INVALID};
    return index < 19U ? values[index] : -1;
}
