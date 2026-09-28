#ifndef __ATTITUDE_PREFLIGHT_H
#define __ATTITUDE_PREFLIGHT_H

#include <stdint.h>

typedef enum
{
    ATTITUDE_PREFLIGHT_RESULT_OK = 0,
    ATTITUDE_PREFLIGHT_RESULT_BAD_PARAM,
    ATTITUDE_PREFLIGHT_RESULT_INVALID,
    ATTITUDE_PREFLIGHT_RESULT_STALE,
    ATTITUDE_PREFLIGHT_RESULT_FROZEN
} AttitudePreflightResult;

typedef struct
{
    float quaternion_wxyz[4];
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint8_t valid;
} AttitudePreflightSample;

typedef struct
{
    AttitudePreflightSample latest;
    AttitudePreflightSample mission;
    uint8_t mission_frozen;
} AttitudePreflightContext;

void AttitudePreflight_Init(AttitudePreflightContext *context);
AttitudePreflightResult AttitudePreflight_LatestUpdate(
    AttitudePreflightContext *context,
    const AttitudePreflightSample *sample);
AttitudePreflightResult AttitudePreflight_LatestCheck(
    const AttitudePreflightContext *context,
    uint64_t now_us,
    uint64_t maximum_age_us);
AttitudePreflightResult AttitudePreflight_MissionFreeze(
    AttitudePreflightContext *context,
    uint64_t now_us,
    uint64_t maximum_age_us);
void AttitudePreflight_MissionUnfreeze(AttitudePreflightContext *context);
uint8_t AttitudePreflight_LatestGet(
    const AttitudePreflightContext *context,
    AttitudePreflightSample *sample);
uint8_t AttitudePreflight_MissionGet(
    const AttitudePreflightContext *context,
    AttitudePreflightSample *sample);

#endif /* __ATTITUDE_PREFLIGHT_H */
