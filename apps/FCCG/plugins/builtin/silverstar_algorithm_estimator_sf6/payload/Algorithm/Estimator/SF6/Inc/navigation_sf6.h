#ifndef __NAVIGATION_SF6_H
#define __NAVIGATION_SF6_H

#include <stdint.h>

#define NAV_SF6_HISTORY_CAPACITY 256U
#define NAV_SF6_EVENT_CAPACITY 256U
#define NAV_SF6_HISTORY_US 600000ULL
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
    NAV_SF6_FULL
} NavigationSf6Result;

/* State order and gain order are vE, vN, vU, pE, pN, pU. No covariance. */
typedef struct
{
    uint64_t timestamp_us;
    float state[6];
    float delta_velocity[3]; /* Increment leading to this boundary. */
    float dt_s; /* Preserve the admitted integration interval during replay. */
} NavigationSf6Sample;

typedef struct
{
    uint64_t measurement_us;
    float observation[2];
    uint8_t group;
} NavigationSf6Event;

typedef struct
{
    NavigationSf6Sample history[NAV_SF6_HISTORY_CAPACITY];
    NavigationSf6Event events[NAV_SF6_EVENT_CAPACITY];
    float base_state[6]; /* Before observations at the oldest boundary. */
    float gain[6];
    uint64_t last_measurement_us[NAV_SF6_GROUP_COUNT];
    uint64_t last_receive_us[NAV_SF6_GROUP_COUNT];
    uint32_t last_sequence[NAV_SF6_GROUP_COUNT];
    uint16_t first;
    uint16_t count;
    uint16_t event_count;
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
