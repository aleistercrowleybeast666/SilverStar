#ifndef __NAVIGATION_SF6_H
#define __NAVIGATION_SF6_H

#include <stdint.h>

#define NAV_SF6_ALGORITHM_REVISION 2U
#define NAV_SF6_MAX_MEASUREMENT_AGE_US 500000ULL
#define NAV_SF6_MAX_DT_S 0.02f
#define NAV_SF6_GROUP_COUNT 5U

typedef enum
{
    NAV_SF6_OK = 0,
    NAV_SF6_INVALID_ARGUMENT,
    NAV_SF6_NOT_READY,
    NAV_SF6_STALE,
    NAV_SF6_DUPLICATE,
    NAV_SF6_NUMERIC_ERROR,
    NAV_SF6_FULL /* Reserved revision-1 wire value; revision 2 has no queue. */
} NavigationSf6Result;

/* State order and gain order are vE, vN, vU, pE, pN, pU. No covariance. */
typedef struct
{
    uint64_t timestamp_us;
    float state[6];
    float delta_velocity[3]; /* Latest admitted prediction increment. */
    float dt_s; /* Latest admitted integration interval. */
} NavigationSf6Sample;

/* Revision 2 applies each admitted observation to the present state. There is
 * no history, delayed observation queue, rewind, or event replay. */
typedef struct
{
    NavigationSf6Sample latest;
    float gain[6];
    uint64_t epoch_us;
    uint64_t last_measurement_us[NAV_SF6_GROUP_COUNT];
    uint64_t last_receive_us[NAV_SF6_GROUP_COUNT];
    uint32_t last_sequence[NAV_SF6_GROUP_COUNT];
    uint8_t seen[NAV_SF6_GROUP_COUNT];
    uint8_t initialized;
} NavigationSf6Context;

typedef struct
{
    uint64_t measurement_us;
    uint64_t receive_us;
    uint32_t sequence;
    uint8_t group; /* position EN/U, velocity EN/U, barometer U. */
    float observation[2];
} NavigationSf6Measurement;

void NavigationSf6_Reset(NavigationSf6Context *context);
NavigationSf6Result NavigationSf6_Initialize(NavigationSf6Context *context,
    const float gain[6], const float velocity[3], uint64_t timestamp_us);
NavigationSf6Result NavigationSf6_Predict(NavigationSf6Context *context,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s);
NavigationSf6Result NavigationSf6_Update(NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint64_t *boundary_us);
NavigationSf6Result NavigationSf6_SnapshotGet(const NavigationSf6Context *context,
    NavigationSf6Sample *snapshot);

#endif /* __NAVIGATION_SF6_H */
