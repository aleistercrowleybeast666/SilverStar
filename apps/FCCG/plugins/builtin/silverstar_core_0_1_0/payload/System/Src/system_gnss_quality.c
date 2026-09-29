#include "system_gnss_quality.h"

#include <math.h>
#include <stddef.h>

#include "silverstar_assert.h"
#include "system_user_config.h"

static uint8_t SystemGnssQuality_FieldSupported(
    const SystemGnssSample *sample,
    uint32_t field)
{
    return (uint8_t)((sample->supported_fields & field) != 0U);
}

static uint8_t SystemGnssQuality_FieldValid(const SystemGnssSample *sample,
                                             uint32_t field)
{
    return (uint8_t)((sample->valid_fields & field) != 0U);
}

static void SystemGnssQuality_OptionalFieldCheck(
    const SystemGnssSample *sample,
    uint32_t field,
    uint32_t reason,
    uint32_t *reject_mask,
    uint8_t *blocking,
    uint8_t *quality_degraded)
{
    if (SystemGnssQuality_FieldSupported(sample, field) == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED;
        *quality_degraded = 1U;
    }
    else if (SystemGnssQuality_FieldValid(sample, field) == 0U)
    {
        *reject_mask |= reason | SYSTEM_GNSS_REJECT_FIELD_INVALID;
        *blocking = 1U;
    }
}

static uint8_t SystemGnssQuality_BasicFixCheck(
    const SystemGnssSample *sample,
    uint32_t *reject_mask,
    uint8_t *quality_degraded)
{
    uint8_t blocking = 0U;

    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (sample->online == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_OFFLINE;
        blocking = 1U;
    }
    if (SystemGnssQuality_FieldSupported(
            sample, SYSTEM_GNSS_FIELD_FIX_TYPE) == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_NO_FIX |
                        SYSTEM_GNSS_REJECT_FIX_TYPE |
                        SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED;
        blocking = 1U;
    }
    else if (SystemGnssQuality_FieldValid(
                 sample, SYSTEM_GNSS_FIELD_FIX_TYPE) == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_NO_FIX |
                        SYSTEM_GNSS_REJECT_FIX_TYPE |
                        SYSTEM_GNSS_REJECT_FIELD_INVALID;
        blocking = 1U;
    }
    else if ((sample->fix_type != 2U) && (sample->fix_type != 3U) &&
             (sample->fix_type != 4U))
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_NO_FIX |
                        SYSTEM_GNSS_REJECT_FIX_TYPE;
        blocking = 1U;
    }

    if (SystemGnssQuality_FieldSupported(
            sample, SYSTEM_GNSS_FIELD_FIX_OK) == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED | SYSTEM_GNSS_REJECT_FIX_FLAG;
        *quality_degraded = 1U;
        blocking = 1U;
    }
    else if (SystemGnssQuality_FieldValid(
                 sample, SYSTEM_GNSS_FIELD_FIX_OK) == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_FIX_FLAG |
                        SYSTEM_GNSS_REJECT_FIELD_INVALID;
        blocking = 1U;
    }
    else if (sample->fix_ok == 0U)
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_FIX_FLAG;
        blocking = 1U;
    }
    return blocking;
}

static uint8_t SystemGnssQuality_SatelliteCheck(
    SystemGnssSample *sample,
    uint32_t *reject_mask)
{
    uint8_t blocking = 0U;

    SILVERSTAR_ASSERT(sample != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(reject_mask != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SystemGnssQuality_OptionalFieldCheck(sample,
        SYSTEM_GNSS_FIELD_SATELLITE_COUNT, SYSTEM_GNSS_REJECT_SATELLITES,
        reject_mask, &blocking, &sample->quality_degraded);
    if ((SystemGnssQuality_FieldSupported(sample,
             SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U) &&
        (SystemGnssQuality_FieldValid(sample,
             SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U) &&
        (sample->satellite_count < SYSTEM_GNSS_MIN_SATELLITES))
    {
        *reject_mask |= SYSTEM_GNSS_REJECT_SATELLITES;
        sample->quality_degraded = 1U;
    }
    /* numSV is quality evidence, never physical validity by itself. */
    if (blocking != 0U) { sample->quality_degraded = 1U; }
    return 0U;
}

static uint8_t SystemGnssQuality_AccuracyCheck(
    SystemGnssSample *sample,
    uint32_t field,
    uint32_t reason,
    float value,
    float maximum,
    uint32_t *reject_mask)
{
    uint8_t blocking = 0U;

    SILVERSTAR_ASSERT(sample != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(reject_mask != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SystemGnssQuality_OptionalFieldCheck(sample, field, reason, reject_mask,
        &blocking, &sample->quality_degraded);
    if ((SystemGnssQuality_FieldSupported(sample, field) != 0U) &&
        (SystemGnssQuality_FieldValid(sample, field) != 0U) &&
        (!isfinite(value) || (value < 0.0f)))
    {
        *reject_mask |= reason;
        blocking = 1U;
    }
    else if ((SystemGnssQuality_FieldValid(sample, field) != 0U) && (value > maximum))
    {
        *reject_mask |= reason;
        sample->quality_degraded = 1U; /* Reported finite sigma already increases R. */
    }
    return blocking;
}

static uint8_t SystemGnssQuality_RequiredFieldCheck(
    const SystemGnssSample *sample, uint32_t field, uint32_t *reason)
{
    if (SystemGnssQuality_FieldSupported(sample, field) == 0U)
    { *reason |= SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED; return 1U; }
    if (SystemGnssQuality_FieldValid(sample, field) == 0U)
    { *reason |= SYSTEM_GNSS_REJECT_FIELD_INVALID; return 1U; }
    return 0U;
}

static uint8_t SystemGnssQuality_GroupEvaluate(
    SystemGnssSample *sample, uint8_t group, uint8_t common_blocking)
{
    static const uint32_t fields[SYSTEM_GNSS_QUALITY_GROUP_COUNT] = {
        SYSTEM_GNSS_FIELD_POSITION, SYSTEM_GNSS_FIELD_HEIGHT,
        SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL, SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL};
    uint32_t *reason = &sample->group_reject_mask[group];
    uint8_t blocking = common_blocking;
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(group < SYSTEM_GNSS_QUALITY_GROUP_COUNT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    blocking |= SystemGnssQuality_RequiredFieldCheck(sample, fields[group], reason);
    if (group == SYSTEM_GNSS_QUALITY_POSITION_HORIZONTAL)
    {
        blocking |= SystemGnssQuality_AccuracyCheck(sample,
            SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY, SYSTEM_GNSS_REJECT_HACC,
            sample->horizontal_accuracy_m, SYSTEM_GNSS_MAX_HORIZONTAL_ACCURACY_M, reason);
        if ((sample->latitude_e7 < -900000000) || (sample->latitude_e7 > 900000000) ||
            (sample->longitude_e7 < -1800000000) || (sample->longitude_e7 > 1800000000))
        { *reason |= SYSTEM_GNSS_REJECT_FIELD_INVALID; blocking = 1U; }
    }
    else if (group == SYSTEM_GNSS_QUALITY_POSITION_VERTICAL)
    {
        blocking |= SystemGnssQuality_AccuracyCheck(sample,
            SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY, SYSTEM_GNSS_REJECT_VACC,
            sample->vertical_accuracy_m, SYSTEM_GNSS_MAX_VERTICAL_ACCURACY_M, reason);
    }
    else
    {
        blocking |= SystemGnssQuality_AccuracyCheck(sample,
            SYSTEM_GNSS_FIELD_SPEED_ACCURACY, SYSTEM_GNSS_REJECT_SACC,
            sample->speed_accuracy_mps, SYSTEM_GNSS_MAX_SPEED_ACCURACY_MPS, reason);
        if ((group == SYSTEM_GNSS_QUALITY_VELOCITY_HORIZONTAL) ?
            (!isfinite(sample->velocity_enu_mps[0]) || !isfinite(sample->velocity_enu_mps[1])) :
            !isfinite(sample->velocity_enu_mps[2]))
        { *reason |= SYSTEM_GNSS_REJECT_FIELD_INVALID; blocking = 1U; }
    }
    if ((group == SYSTEM_GNSS_QUALITY_POSITION_VERTICAL) &&
        (sample->fix_type == 2U))
    { *reason |= SYSTEM_GNSS_REJECT_FIX_TYPE; blocking = 1U; }
    return (uint8_t)(blocking == 0U);
}

SystemDeviceResult SystemGnssQuality_Evaluate(SystemGnssSample *sample,
                                               uint64_t now_us)
{
    uint32_t common_reason = 0U;
    uint8_t common_blocking;
    uint8_t group;
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    sample->quality_degraded = 0U;
    sample->valid_group_mask = 0U;
    sample->velocity_valid_mask = 0U;
    sample->physical_valid_group_mask = 0U;
    sample->quality_degraded_group_mask = 0U;
    common_blocking = SystemGnssQuality_BasicFixCheck(
        sample, &common_reason, &sample->quality_degraded);
    common_blocking |= SystemGnssQuality_SatelliteCheck(sample, &common_reason);
    /* Liveness/freshness is receive time; a trusted delayed sample is not a link outage. */
    if ((sample->receive_timestamp_us == 0U) || (sample->receive_timestamp_us > now_us) ||
        ((now_us - sample->receive_timestamp_us) >
         ((uint64_t)SYSTEM_GNSS_MAX_SAMPLE_AGE_MS * 1000ULL)))
    { common_reason |= SYSTEM_GNSS_REJECT_STALE; common_blocking = 1U; }
    for (group = 0U; group < SYSTEM_GNSS_QUALITY_GROUP_COUNT; group++)
    {
        sample->group_reject_mask[group] = common_reason;
        if (SystemGnssQuality_GroupEvaluate(sample, group, common_blocking) != 0U)
        { sample->valid_group_mask |= (uint8_t)(1U << group); }
        if (sample->group_reject_mask[group] != 0U)
        { sample->quality_degraded_group_mask |= (uint8_t)(1U << group); }
    }
    sample->physical_valid_group_mask = sample->valid_group_mask;
    sample->position_reject_mask = sample->group_reject_mask[0] | sample->group_reject_mask[1];
    sample->velocity_reject_mask = sample->group_reject_mask[2] | sample->group_reject_mask[3];
    /* Preserve the strict pre-START origin gate and aggregate status contract. */
    sample->position_usable = (uint8_t)(((sample->valid_group_mask & 3U) == 3U) &&
        ((sample->position_reject_mask & (SYSTEM_GNSS_REJECT_SATELLITES | SYSTEM_GNSS_REJECT_HACC | SYSTEM_GNSS_REJECT_VACC)) == 0U));
    if ((sample->valid_group_mask & 4U) != 0U)
    { sample->velocity_valid_mask |= SYSTEM_GNSS_VEL_VALID_E | SYSTEM_GNSS_VEL_VALID_N; }
    if ((sample->valid_group_mask & 8U) != 0U)
    { sample->velocity_valid_mask |= SYSTEM_GNSS_VEL_VALID_U; }
    return SYSTEM_DEVICE_OK;
}
