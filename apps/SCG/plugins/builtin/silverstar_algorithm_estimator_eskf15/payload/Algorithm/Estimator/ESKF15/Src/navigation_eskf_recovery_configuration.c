/* All SYSTEM_ESKF_GNSS_RECOVERY_* values come from project_algorithm_parameters.h.
 * Missing bindings are compiler errors; no firmware/offline alternate defaults. */
#include "navigation_eskf_recovery_configuration.h"
#include <float.h>
#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(float) == sizeof(uint32_t) && FLT_RADIX == 2 &&
    FLT_MANT_DIG == 24 && FLT_MAX_EXP == 128, "Recovery wire requires IEEE binary32");
_Static_assert(SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0 || SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 1,
    "Recovery enabled must be an actual boolean integer");
_Static_assert(SYSTEM_ESKF_GNSS_RECOVERY_LOSS_GAP_MS >= 0 &&
    SYSTEM_ESKF_GNSS_RECOVERY_LOSS_GAP_MS <= INT32_MAX &&
    SYSTEM_ESKF_GNSS_RECOVERY_STABLE_SPAN_MS >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_STABLE_SPAN_MS <= INT32_MAX &&
    SYSTEM_ESKF_GNSS_RECOVERY_COOLDOWN_MS >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_COOLDOWN_MS <= INT32_MAX,
    "Recovery durations must fit nonnegative generated int32 milliseconds");
_Static_assert(SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_INTERVAL_MS >= 0 &&
    SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_INTERVAL_MS <= 500 &&
    SYSTEM_ESKF_GNSS_RECOVERY_CLOCK_JITTER_MS >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_CLOCK_JITTER_MS <= 500,
    "Recovery receipt intervals exceed the existing receive-age contract");
_Static_assert(SYSTEM_ESKF_GNSS_RECOVERY_STABLE_COUNT >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_STABLE_COUNT <= UINT8_MAX &&
    SYSTEM_ESKF_GNSS_RECOVERY_REJECT_COUNT >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_REJECT_COUNT <= UINT8_MAX &&
    SYSTEM_ESKF_GNSS_RECOVERY_CONFIRMATION_COUNT >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_CONFIRMATION_COUNT <= UINT8_MAX &&
    SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_ATTEMPTS >= 0 && SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_ATTEMPTS <= UINT8_MAX,
    "Recovery counts must fit their generated wire and state representation");

static const NavigationEskfRecoveryConfiguration s_configuration = {
    .policy = {
        .loss_gap_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_LOSS_GAP_MS * 1000ULL,
        .stable_span_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_STABLE_SPAN_MS * 1000ULL,
        .maximum_interval_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_INTERVAL_MS * 1000ULL,
        .cooldown_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_COOLDOWN_MS * 1000ULL,
        .identity = (uint32_t)SYSTEM_ESKF_GNSS_RECOVERY_CONFIGURATION_ID,
        .stable_count = (uint8_t)SYSTEM_ESKF_GNSS_RECOVERY_STABLE_COUNT,
        .reject_count = (uint8_t)SYSTEM_ESKF_GNSS_RECOVERY_REJECT_COUNT,
        .confirmation_count = (uint8_t)SYSTEM_ESKF_GNSS_RECOVERY_CONFIRMATION_COUNT,
        .maximum_attempts = (uint8_t)SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_ATTEMPTS,
        .scale = {SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE, SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE,
            SYSTEM_ESKF_GNSS_RECOVERY_UNIFORM_SCALE},
        .variance_cap = {SYSTEM_ESKF_GNSS_RECOVERY_CAP_POSITION_E, SYSTEM_ESKF_GNSS_RECOVERY_CAP_POSITION_N,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_POSITION_U, SYSTEM_ESKF_GNSS_RECOVERY_CAP_VELOCITY_E,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_VELOCITY_N, SYSTEM_ESKF_GNSS_RECOVERY_CAP_VELOCITY_U,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_THETA_X, SYSTEM_ESKF_GNSS_RECOVERY_CAP_THETA_Y,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_THETA_Z, SYSTEM_ESKF_GNSS_RECOVERY_CAP_GYRO_BIAS_X,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_GYRO_BIAS_Y, SYSTEM_ESKF_GNSS_RECOVERY_CAP_GYRO_BIAS_Z,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_ACCEL_BIAS_X, SYSTEM_ESKF_GNSS_RECOVERY_CAP_ACCEL_BIAS_Y,
            SYSTEM_ESKF_GNSS_RECOVERY_CAP_ACCEL_BIAS_Z}},
    .qualifier = {
        .maximum_interval_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_MAXIMUM_INTERVAL_MS * 1000ULL,
        .clock_jitter_us = (uint64_t)SYSTEM_ESKF_GNSS_RECOVERY_CLOCK_JITTER_MS * 1000ULL,
        .horizontal_acceleration_limit_mps2 = SYSTEM_ESKF_GNSS_RECOVERY_HORIZONTAL_ACCELERATION_LIMIT_MPS2,
        .vertical_acceleration_limit_mps2 = SYSTEM_ESKF_GNSS_RECOVERY_VERTICAL_ACCELERATION_LIMIT_MPS2,
        .closure_sigma = SYSTEM_ESKF_GNSS_RECOVERY_CLOSURE_SIGMA},
    .enabled = (uint8_t)SYSTEM_ESKF_GNSS_RECOVERY_ENABLED
};

const NavigationEskfRecoveryConfiguration *NavigationEskfRecoveryConfiguration_Get(void)
{ return &s_configuration; }

/* memcpy returns its already validated destination, not a fallible operation.
 * Explicitly discard that value; the bit copy avoids aliasing/type punning. */
static void Configuration_U32Put(uint8_t output[NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE],
    uint16_t offset, uint32_t value)
{
    for (uint8_t byte = 0U; byte < 4U; byte++)
    { output[offset + byte] = (uint8_t)(value >> (8U * byte)); }
}

static void Configuration_F32Put(uint8_t output[NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE],
    uint16_t offset, float value)
{
    uint32_t bits;
    (void)memcpy(&bits, &value, sizeof(bits));
    Configuration_U32Put(output, offset, bits);
}

NavigationEskfRecoveryConfigurationResult NavigationEskfRecoveryConfiguration_Encode(
    uint8_t *output, uint16_t capacity)
{
    uintptr_t destination = (uintptr_t)output, source = (uintptr_t)&s_configuration;
    uint8_t overlap = (uint8_t)((destination <= source) ?
        (source - destination < NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE) :
        (destination - source < sizeof(s_configuration)));
    if ((output == NULL) || (capacity < NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE) || overlap)
    { return NAV_ESKF_RECOVERY_CONFIGURATION_INVALID_ARGUMENT; }
    Configuration_U32Put(output, 0U, s_configuration.enabled);
    Configuration_U32Put(output, 4U, (uint32_t)(s_configuration.policy.loss_gap_us / 1000ULL));
    Configuration_U32Put(output, 8U, (uint32_t)(s_configuration.policy.stable_span_us / 1000ULL));
    Configuration_U32Put(output, 12U, (uint32_t)(s_configuration.policy.maximum_interval_us / 1000ULL));
    Configuration_U32Put(output, 16U, (uint32_t)(s_configuration.policy.cooldown_us / 1000ULL));
    output[20] = s_configuration.policy.stable_count; output[21] = s_configuration.policy.reject_count;
    output[22] = s_configuration.policy.confirmation_count; output[23] = s_configuration.policy.maximum_attempts;
    Configuration_F32Put(output, 24U, s_configuration.policy.scale[0]);
    for (uint16_t index = 0U; index < NAV_ESKF_DIM; index++)
    { Configuration_F32Put(output, (uint16_t)(28U + 4U * index), s_configuration.policy.variance_cap[index]); }
    Configuration_U32Put(output, 88U, (uint32_t)(s_configuration.qualifier.clock_jitter_us / 1000ULL));
    Configuration_F32Put(output, 92U, s_configuration.qualifier.horizontal_acceleration_limit_mps2);
    Configuration_F32Put(output, 96U, s_configuration.qualifier.vertical_acceleration_limit_mps2);
    Configuration_F32Put(output, 100U, s_configuration.qualifier.closure_sigma);
    return NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE;
}

static uint32_t Configuration_Crc32(const uint8_t input[NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE])
{
    uint32_t crc = UINT32_MAX;
    for (uint16_t index = 0U; index < NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE; index++)
    {
        crc ^= input[index];
        for (uint8_t bit = 0U; bit < 8U; bit++)
        { crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320U : 0U); }
    }
    crc = ~crc;
    return crc ? crc : UINT32_MAX;
}

NavigationEskfRecoveryConfigurationResult NavigationEskfRecoveryConfiguration_Validate(void)
{
    uint8_t wire[NAV_ESKF_RECOVERY_CONFIGURATION_WIRE_SIZE];
    if (s_configuration.enabled &&
        ((NavigationEskfRecovery_ConfigValidate(&s_configuration.policy) != NAV_ESKF_RECOVERY_COMPLETE) ||
         (NavigationEskfRecoveryQualifier_ConfigValidate(&s_configuration.qualifier) != NAV_ESKF_QUALIFIER_COMPLETE)))
    { return NAV_ESKF_RECOVERY_CONFIGURATION_INVALID_POLICY; }
    if (NavigationEskfRecoveryConfiguration_Encode(wire, sizeof(wire)) != NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE)
    { return NAV_ESKF_RECOVERY_CONFIGURATION_INVALID_ARGUMENT; }
    return (Configuration_Crc32(wire) == s_configuration.policy.identity) ?
        NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE : NAV_ESKF_RECOVERY_CONFIGURATION_IDENTITY_MISMATCH;
}
