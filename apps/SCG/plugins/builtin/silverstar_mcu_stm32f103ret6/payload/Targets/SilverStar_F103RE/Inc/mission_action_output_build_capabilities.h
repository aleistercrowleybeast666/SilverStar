#ifndef __MISSION_ACTION_OUTPUT_BUILD_CAPABILITIES_H
#define __MISSION_ACTION_OUTPUT_BUILD_CAPABILITIES_H

/*
 * FCCG generates the selected-Device values before this target header is
 * included.  The zero fallbacks keep a composition with no mission-action
 * output honest and buildable; a Board must not manufacture Device support.
 */
#ifndef MISSION_ACTION_OUTPUT_BUILD_START_ACTION_AVAILABLE
#define MISSION_ACTION_OUTPUT_BUILD_START_ACTION_AVAILABLE        0U
#endif

#ifndef MISSION_ACTION_OUTPUT_BUILD_PARACHUTE_DEPLOY_AVAILABLE
#define MISSION_ACTION_OUTPUT_BUILD_PARACHUTE_DEPLOY_AVAILABLE    0U
#endif

#endif /* __MISSION_ACTION_OUTPUT_BUILD_CAPABILITIES_H */
