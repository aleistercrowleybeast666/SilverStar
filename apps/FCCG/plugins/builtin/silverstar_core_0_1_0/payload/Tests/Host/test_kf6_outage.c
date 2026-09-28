#include <math.h>
#include <stdio.h>
#include <string.h>
#include "navigation_kf.h"
#include "system_estimator_profile.h"

/* Deterministic float32 acceptance vectors: same recipe is replayed by FLP. */
int main(void)
{
    unsigned int scenario, step, axis, group;
    for (scenario = 0U; scenario < 10U; scenario++)
    {
        NavigationKfContext kf;
        NavigationKfGnssEpoch epoch;
        const float pv[3] = {1.0f, 1.0f, 1.0f};
        const float vv[3] = {0.04f, 0.04f, 0.04f};
        NavigationKf_Init(&kf);
        (void)memset(&epoch, 0, sizeof(epoch));
        for (axis = 0U; axis < 3U; axis++)
        {
            epoch.position_std_m[axis] = 1.0f;
            epoch.velocity_std_mps[axis] = 0.2f;
        }
        epoch.timestamp_us = 1000000ULL;
        epoch.valid_group_mask = 15U;
        NavigationKf_GnssEpochTrack(&kf, &epoch);
        if (scenario != 2U && scenario != 8U)
        {
            kf.state[0] = -30.0f;
            kf.state[2] = -30.0f;
            kf.state[3] = -30.0f;
            kf.state[5] = -30.0f;
        }
        for (step = 0U; step < 64U; step++)
        {
            NavigationKfGnssSeparatedUpdateResult pr, vr;
            uint64_t gap = (scenario == 1U) ? 100000ULL :
                           ((scenario == 2U || scenario == 3U || scenario == 7U) ? 500000ULL : 40000ULL);
            epoch.timestamp_us = 1000000ULL + gap + (uint64_t)step * 40000ULL;
            epoch.valid_group_mask = 15U;
            if ((scenario == 4U || scenario == 6U) && step < 12U)
            { epoch.valid_group_mask = 7U; }
            if (scenario == 5U && step < 12U) { epoch.valid_group_mask = 3U; }
            if (scenario == 6U && step >= 20U && step < 32U)
            { epoch.valid_group_mask = 7U; }
            if (scenario == 7U && step == 2U) { epoch.timestamp_us = 0ULL; }
            if (scenario == 7U && step == 4U) { epoch.timestamp_us -= 40000ULL; }
            if (scenario == 7U && step == 6U) { epoch.timestamp_us = 1000000ULL; }
            if (scenario == 9U && step < 12U) { epoch.velocity_std_mps[2] = NAN; }
            else { epoch.velocity_std_mps[2] = 0.2f; }
            if (scenario == 8U)
            {
                float delta[3] = {0.012f, -0.006f, 0.009f};
                (void)NavigationKf_Predict(&kf, delta, 0.04f);
                (void)NavigationKf_UpdateBaroAltitude(&kf, 0.2f, 4.0f);
            }
            NavigationKf_GnssEpochTrack(&kf, &epoch);
            (void)NavigationKf_UpdateGnssPositionSeparated(&kf, epoch.position_enu_m, pv, &pr);
            NavigationKf_GnssGroupResultProcess(&kf, NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL, pr.horizontal_result);
            NavigationKf_GnssGroupResultProcess(&kf, NAV_KF_GNSS_GROUP_POSITION_VERTICAL, pr.vertical_result);
            if ((epoch.valid_group_mask & 4U) != 0U)
            {
                (void)NavigationKf_UpdateGnssVelocitySeparated(&kf, epoch.velocity_enu_mps, vv,
                    (uint8_t)((epoch.valid_group_mask & 8U) != 0U), &vr);
                NavigationKf_GnssGroupResultProcess(&kf, NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL, vr.horizontal_result);
                if ((epoch.valid_group_mask & 8U) != 0U)
                { NavigationKf_GnssGroupResultProcess(&kf, NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL, vr.vertical_result); }
            }
            (void)printf("%u %u", scenario, step);
            for (axis = 0U; axis < 6U; axis++) { (void)printf(" %.9g", (double)kf.state[axis]); }
            for (axis = 0U; axis < 36U; axis++)
            { (void)printf(" %.9g", (double)(&kf.covariance[0][0])[axis]); }
            for (group = 0U; group < 4U; group++)
            {
                NavigationKfGnssReacquireGroupState *state = &kf.gnss_reacquisition.group[group];
                (void)printf(" %u %lu %lu %lu", state->outage,
                    (unsigned long)state->inflation_attempt_count,
                    (unsigned long)state->reject_streak, (unsigned long)state->consistent_count);
            }
            (void)printf("\n");
        }
    }
    return 0;
}
