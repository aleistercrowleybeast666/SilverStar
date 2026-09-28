#ifndef __MISSION_ACTION_OUTPUT_CONFIG_H
#define __MISSION_ACTION_OUTPUT_CONFIG_H

/* Output service channels are 1-based: 1=P_CONTROL1, 2=P_CONTROL2. */
#define MISSION_ACTION_START_OUTPUT_CHANNEL  1U
#define MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL 2U

/*
 * Millisecond test defaults. No historical pulse duration exists in the old
 * PWROUT implementation; these values require actuator-specific bench review.
 */
#define MISSION_ACTION_START_PULSE_MS  1000U
#define MISSION_ACTION_DEPLOY_PULSE_MS 1000U

#if (MISSION_ACTION_START_OUTPUT_CHANNEL == 0U) || \
    (MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL == 0U) || \
    (MISSION_ACTION_START_OUTPUT_CHANNEL == \
     MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL)
#error "Mission action output channels must be distinct, non-zero channels"
#endif

#if (MISSION_ACTION_START_PULSE_MS == 0U) || \
    (MISSION_ACTION_DEPLOY_PULSE_MS == 0U)
#error "Mission action pulse durations must be non-zero"
#endif

#endif /* __MISSION_ACTION_OUTPUT_CONFIG_H */
