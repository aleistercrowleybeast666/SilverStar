#ifndef __NAVIGATION_REPLAY_H
#define __NAVIGATION_REPLAY_H
#include "navigation_session.h"

/* Fixed mathematical input contract, not a qualified target scheduling profile.
 * All objects are disjoint, static caller-owned, and accessed by one owner. */
#define NAVIGATION_REPLAY_BODY_CAPACITY 64U
#define NAVIGATION_REPLAY_OBSERVATION_CAPACITY 64U
#define NAVIGATION_REPLAY_REVISION 1U

typedef struct {
    uint64_t start_us,end_us;
    double gyro[6],force[6];
} NavigationReplayBody;

typedef struct {
    NavigationInputEvent event;
    uint32_t kind; /* 0 position, 1 velocity, 2 native physical magnetic */
    uint32_t admission; /* 0 normal; recorded boundary refusal: 1 invalid, 2 identity, 9 unbound stage */
    double gate;
    double measured[3],covariance[9];
    float sensor_uT[3],covariance_uT2[9];
    NavigationMagCorrection correction;
    NavigationMagStage stage;
} NavigationReplayObservation;

typedef struct {
    NavigationSessionResult result;
    double nis;
} NavigationReplayOutcome;

typedef struct {
    NavigationSession anchor,current;
    NavigationReplayBody bodies[NAVIGATION_REPLAY_BODY_CAPACITY];
    NavigationReplayObservation observations[NAVIGATION_REPLAY_OBSERVATION_CAPACITY];
    NavigationReplayOutcome outcomes[NAVIGATION_REPLAY_OBSERVATION_CAPACITY];
    double gravity[3],density[12];
    uint64_t maximum_delay_us;
    uint32_t body_count,observation_count;
    uint32_t retired_accepted[3],retired_rejected[3];
    uint64_t retired_last_accepted_us[3];
} NavigationReplay;

typedef struct {
    NavigationSessionWorkspace session;
    NavigationSession trial,next_anchor;
    NavigationReplayOutcome outcomes[NAVIGATION_REPLAY_OBSERVATION_CAPACITY+1U];
    uint32_t operations;
} NavigationReplayWorkspace;

NavigationSessionResult NavigationReplay_Initialize(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationState *initial,uint64_t origin_us,
    const NavigationInputIdentity *imu,const NavigationInputIdentity observations[3],
    const double gravity[3],const double density[12],uint64_t maximum_delay_us);
NavigationSessionResult NavigationReplay_Predict(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationInputIdentity *imu,
    uint64_t start_us,uint64_t end_us,const double gyro[6],const double force[6]);
NavigationSessionResult NavigationReplay_Observe(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationReplayObservation *observation,
    NavigationReplayOutcome *outcome);
/* Count actual recomputed decisions; delayed insertion can change later gates. */
NavigationSessionResult NavigationReplay_CountsGet(const NavigationReplay *replay,
    uint32_t accepted[3],uint32_t rejected[3]);
NavigationSessionResult NavigationReplay_LastAcceptedGet(const NavigationReplay *replay,uint64_t sample_us[3]);
#endif
