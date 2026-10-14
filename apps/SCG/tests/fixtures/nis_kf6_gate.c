/* Host-only gate/invalid-input evidence; never part of target firmware. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "navigation_kf.h"

static NavigationKfContext s_filter;

static void Test_FilterPrepare(void)
{
    float covariance[6][6] = {{0}};
    const float soft[3] = {6.0f, 6.0f, 6.0f};
    const float hard[3] = {8.0f, 8.0f, 8.0f};
    unsigned int i;
    for (i = 0U; i < 6U; i++) { covariance[i][i] = 1.0f; }
    NavigationKf_Init(&s_filter);
    assert(NavigationKf_ResetWithCovariance(&s_filter, &covariance[0][0]) != 0U);
    NavigationKf_SetBaroStd(&s_filter, 1.0f);
    NavigationKf_SetNisThresholds(&s_filter, soft, hard, 4.0f);
}

int main(void)
{
    NavigationKfUpdateResult equality, soft, outlier, invalid, position, velocity;
    const float observation[3] = {1.0f, 1.0f, 1.0f};
    const float variance[3] = {1.0f, 1.0f, 1.0f};
    const float reserved_soft[3] = {6.0f, 6.0f, 0.001f};
    const float reserved_hard[3] = {8.0f, 8.0f, 0.002f};
    float before[6][6];
    Test_FilterPrepare();
    memcpy(before, s_filter.covariance, sizeof(before));
    equality = NavigationKf_UpdateBaroAltitude(&s_filter, 4.0f, 1.0f);
    if (equality == NAV_KF_UPDATE_REJECTED_NIS)
    { assert(memcmp(before, s_filter.covariance, sizeof(before)) == 0); }
    Test_FilterPrepare();
    soft = NavigationKf_UpdateBaroAltitude(&s_filter, sqrtf(14.0f), 1.0f);
    Test_FilterPrepare();
    outlier = NavigationKf_UpdateBaroAltitude(&s_filter, 20.0f, 1.0f);
    Test_FilterPrepare();
    memcpy(before, s_filter.covariance, sizeof(before));
    invalid = NavigationKf_UpdateBaroAltitude(&s_filter, NAN, 1.0f);
    assert(invalid == NAV_KF_UPDATE_REJECTED_INVALID);
    assert(memcmp(before, s_filter.covariance, sizeof(before)) == 0);
    /* A tight reserved 3D threshold must not affect the real 2+1 updates. */
    Test_FilterPrepare();
    NavigationKf_SetNisThresholds(&s_filter, reserved_soft, reserved_hard, 4.0f);
    position = NavigationKf_UpdateGnssPosition(&s_filter, observation, variance);
    Test_FilterPrepare();
    NavigationKf_SetNisThresholds(&s_filter, reserved_soft, reserved_hard, 4.0f);
    velocity = NavigationKf_UpdateGnssVelocity3D(&s_filter, observation, variance);
    /* Diagnostic output only; printf failure cannot change a filter result. */
    (void)printf("%u %u %u %u %u %u\n", (unsigned)equality, (unsigned)soft,
                 (unsigned)outlier, (unsigned)invalid,
                 (unsigned)position, (unsigned)velocity);
    return 0;
}
