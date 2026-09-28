#ifndef __FLIGHT_DEPLOYMENT_H
#define __FLIGHT_DEPLOYMENT_H

#include <stdint.h>

#include "system_configuration_types.h"

typedef enum
{
    FLIGHT_DEPLOYMENT_INIT_OK = 0,
    FLIGHT_DEPLOYMENT_INIT_INVALID_ARGUMENT,
    FLIGHT_DEPLOYMENT_INIT_INVALID_CONFIG
} FlightDeploymentInitResult;

typedef enum
{
    FLIGHT_DEPLOYMENT_AXIS_OK = 0,
    FLIGHT_DEPLOYMENT_AXIS_INVALID_ARGUMENT,
    FLIGHT_DEPLOYMENT_AXIS_INVALID_QUATERNION
} FlightDeploymentAxisResult;

typedef enum
{
    FLIGHT_DEPLOYMENT_CONDITION_INVALID = 0,
    FLIGHT_DEPLOYMENT_CONDITION_NOT_MET,
    FLIGHT_DEPLOYMENT_CONDITION_MET
} FlightDeploymentConditionResult;

typedef struct
{
    SystemDeployTriggerMask trigger_mask;
    SystemBodyAxis rocket_longitudinal_axis;
    SystemTiltReference tilt_reference;
    float tilt_threshold_deg;
    float apogee_vertical_velocity_threshold_mps;
    uint32_t delay_ms;
} FlightDeploymentConfig;

typedef struct
{
    FlightDeploymentConfig config;
    float tilt_cos_threshold;
    uint8_t initialized;
} FlightDeploymentContext;

typedef struct
{
    uint32_t mission_time_ms;
    float q_nb[4];
    float velocity_enu_mps[3];
    float initial_rocket_axis_n[3];
    uint8_t attitude_valid;
    uint8_t velocity_valid;
    uint8_t initial_rocket_axis_valid;
} FlightDeploymentInput;

typedef struct
{
    SystemDeployTriggerMask matched_mask;
    float tilt_angle_deg;
    float vertical_velocity_mps;
} FlightDeploymentEvaluation;

FlightDeploymentInitResult FlightDeployment_ContextInit(
    FlightDeploymentContext *context,
    const FlightDeploymentConfig *config);
FlightDeploymentAxisResult FlightDeployment_RocketAxisGet(
    const FlightDeploymentContext *context,
    const float q_nb[4],
    float axis_n[3]);
FlightDeploymentConditionResult FlightDeployment_ConditionEvaluate(
    const FlightDeploymentContext *context,
    const FlightDeploymentInput *input,
    FlightDeploymentEvaluation *evaluation);

#endif /* __FLIGHT_DEPLOYMENT_H */
