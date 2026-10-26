#include "ss_tm_legacy.h"

#include <limits.h>
#include <math.h>
#include <string.h>

#include "silverstar_assert.h"

#define LEGACY_AIR_PI_F 3.14159265358979323846f

_Static_assert(LEGACY_AIR_FLIGHT_STATE_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "FLIGHT_STATE exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_PREFLIGHT_STATE_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "PREFLIGHT_STATE exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_CAPABILITY_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "CAPABILITY exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_PREFLIGHT_STATUS_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "PREFLIGHT_STATUS exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_SENSOR_STATUS_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "SENSOR_STATUS exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_STATUS_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "STATUS exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_CMD_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "CMD exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_ACK_LEN <= LEGACY_AIR_MAX_FRAME_LEN,
               "ACK exceeds LEGACY_AIR_MAX_FRAME_LEN");
_Static_assert(LEGACY_AIR_LIFECYCLE_FAULT <= 0x0FU,
               "lifecycle state exceeds PREFLIGHT_STATUS field");
_Static_assert(LEGACY_AIR_CALIBRATION_STATE_FAILED <= 0x0FU,
               "calibration state exceeds PREFLIGHT_STATUS field");
_Static_assert(LEGACY_AIR_CALIBRATION_MODE_SIX_FACE <= 0x0EU,
               "calibration mode exceeds PREFLIGHT_STATUS field");
_Static_assert(LEGACY_AIR_ALIGNMENT_STATE_STALE <= 0x0FU,
               "alignment state exceeds PREFLIGHT_STATUS field");
_Static_assert(LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE < 0x40U,
               "calibration face exceeds completed mask field");
_Static_assert(LEGACY_AIR_PREFLIGHT_FLAG_MASK_ALL <= 0x7FU,
               "preflight flags exceed PREFLIGHT_STATUS field");

static void LegacyAir_PutU16Le(uint8_t *buf, uint16_t value)
{
    buf[0] = (uint8_t)(value & 0xFFU);
    buf[1] = (uint8_t)((value >> 8) & 0xFFU);
}

static uint16_t LegacyAir_GetU16Le(const uint8_t *buf)
{
    return (uint16_t)(((uint16_t)buf[0]) | ((uint16_t)buf[1] << 8U));
}

static void LegacyAir_PutU32Le(uint8_t *buf, uint32_t value)
{
    buf[0] = (uint8_t)(value & 0xFFU);
    buf[1] = (uint8_t)((value >> 8) & 0xFFU);
    buf[2] = (uint8_t)((value >> 16) & 0xFFU);
    buf[3] = (uint8_t)((value >> 24) & 0xFFU);
}

static uint32_t LegacyAir_GetU32Le(const uint8_t *buf)
{
    return ((uint32_t)buf[0]) |
           ((uint32_t)buf[1] << 8U) |
           ((uint32_t)buf[2] << 16U) |
           ((uint32_t)buf[3] << 24U);
}

static void LegacyAir_PutI16Le(uint8_t *buf, int16_t value)
{
    LegacyAir_PutU16Le(buf, (uint16_t)value);
}

static void LegacyAir_PutFloatLe(uint8_t *buf, float value)
{
    uint32_t raw = 0U;

    memcpy(&raw, &value, sizeof(raw));
    LegacyAir_PutU32Le(buf, raw);
}

static uint8_t LegacyAir_CapabilityFieldsAreValid(
    const LegacyAirCapabilityPayload *capability)
{
    if (capability == NULL)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(capability, LegacyAirCapabilityPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    return (uint8_t)(
        (capability->air_profile_id == LEGACY_AIR_PROFILE_ID_CURRENT) &&
        ((capability->command_policy == LEGACY_AIR_COMMAND_POLICY_PREFLIGHT_ONLY) ||
         (capability->command_policy == LEGACY_AIR_COMMAND_POLICY_MISSION_ALLOWED)) &&
        (capability->calibration_mode_mask != 0U) &&
        ((capability->calibration_mode_mask &
          (uint8_t)(~LEGACY_AIR_CALIBRATION_MODE_MASK_ALL)) == 0U) &&
        ((capability->sensor_summary_flags &
          (uint8_t)(~LEGACY_AIR_SENSOR_SUMMARY_MASK_ALL)) == 0U) &&
        ((capability->sensor_summary_flags &
          LEGACY_AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED) != 0U) &&
        (capability->accel_full_scale_g != 0U) &&
        (capability->gyro_full_scale_dps != 0U));
}

static uint8_t LegacyAir_CalibrationModeIsValid(uint8_t mode)
{
    return (uint8_t)((mode <= LEGACY_AIR_CALIBRATION_MODE_SIX_FACE) ||
                     (mode == LEGACY_AIR_CALIBRATION_MODE_NOT_SELECTED));
}

static uint8_t LegacyAir_StatusFieldsAreValid(uint8_t status_id,
                                        uint8_t arg0,
                                        uint8_t arg1)
{
    SILVERSTAR_ASSERT(LEGACY_AIR_STATUS_BOOT <=
        LEGACY_AIR_STATUS_CALIBRATION_DIAGNOSTIC,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(LEGACY_AIR_STATUS_CALIBRATION_DIAGNOSTIC <= UINT8_MAX,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (status_id)
    {
        case LEGACY_AIR_STATUS_BOOT:
        case LEGACY_AIR_STATUS_LAUNCH:
        case LEGACY_AIR_STATUS_PARACHUTE_DEPLOY:
        case LEGACY_AIR_STATUS_LANDING:
            return 1U;

        case LEGACY_AIR_STATUS_MISSION_START:
        case LEGACY_AIR_STATUS_LOCKED:
        case LEGACY_AIR_STATUS_UNLOCKED:
            return (uint8_t)((arg0 == 0U) && (arg1 == 0U));

        case LEGACY_AIR_STATUS_GNSS_POSITION:
        case LEGACY_AIR_STATUS_SELFTEST_COMPLETE:
            return (uint8_t)((arg0 <= 1U) && (arg1 == 0U));

        case LEGACY_AIR_STATUS_ALIGNMENT:
            if (arg0 > LEGACY_AIR_ALIGNMENT_STATE_STALE) { return 0U; }
            if ((arg0 == LEGACY_AIR_ALIGNMENT_STATE_READY) ||
                (arg0 == LEGACY_AIR_ALIGNMENT_STATE_FAILED))
            {
                return 1U;
            }
            return (uint8_t)(arg1 == 0xFFU);

        case LEGACY_AIR_STATUS_CALIBRATION:
            return (uint8_t)(
                (arg0 <= LEGACY_AIR_CALIBRATION_STATE_FAILED) &&
                (LegacyAir_CalibrationModeIsValid(arg1) != 0U));

        case LEGACY_AIR_STATUS_CALIBRATION_FACE:
            return (uint8_t)(
                (arg0 <= LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE) &&
                (arg1 <= LEGACY_AIR_CALIBRATION_FACE_PASSED));

        case LEGACY_AIR_STATUS_CALIBRATION_DIAGNOSTIC:
            return (uint8_t)(
                ((arg0 <= LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE) ||
                 (arg0 == LEGACY_AIR_CALIBRATION_FACE_NOT_SELECTED)) &&
                (arg1 <= LEGACY_AIR_CALIBRATION_DIAGNOSTIC_SAMPLE_GAP));

        default:
            return 0U;
    }
}

static uint8_t LegacyAir_StartBlockReasonIsValid(uint8_t reason)
{
    SILVERSTAR_ASSERT(LEGACY_AIR_ACK_RESULT_OK <= LEGACY_AIR_ACK_RESULT_PREPARE_FAILED,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(LEGACY_AIR_ACK_RESULT_PREPARE_FAILED <= UINT8_MAX,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (reason)
    {
        case LEGACY_AIR_ACK_RESULT_OK:
        case LEGACY_AIR_ACK_RESULT_BUSY:
        case LEGACY_AIR_ACK_RESULT_LOCKED_REQUIRED:
        case LEGACY_AIR_ACK_RESULT_CAPABILITY_REQUIRED:
        case LEGACY_AIR_ACK_RESULT_CALIBRATION_REQUIRED:
        case LEGACY_AIR_ACK_RESULT_ALIGNMENT_REQUIRED:
        case LEGACY_AIR_ACK_RESULT_SYSTEM_NOT_READY:
        case LEGACY_AIR_ACK_RESULT_ATTITUDE_NOT_READY:
        case LEGACY_AIR_ACK_RESULT_ATTITUDE_INVALID:
        case LEGACY_AIR_ACK_RESULT_ATTITUDE_STALE:
        case LEGACY_AIR_ACK_RESULT_ORIGIN_FAILED:
        case LEGACY_AIR_ACK_RESULT_NAVIGATION_FAILED:
        case LEGACY_AIR_ACK_RESULT_QUEUE_FAILED:
        case LEGACY_AIR_ACK_RESULT_HOOKS_UNAVAILABLE:
        case LEGACY_AIR_ACK_RESULT_PREPARE_FAILED:
            return 1U;
        default:
            return 0U;
    }
}

static uint8_t LegacyAir_PreflightStatusFieldsAreValid(
    const LegacyAirPreflightStatusPayload *status)
{
    if (status == NULL) { return 0U; }
    return (uint8_t)(
        (status->lifecycle_state <= LEGACY_AIR_LIFECYCLE_FAULT) &&
        (status->calibration_state <= LEGACY_AIR_CALIBRATION_STATE_FAILED) &&
        (LegacyAir_CalibrationModeIsValid(status->calibration_mode) != 0U) &&
        ((status->completed_face_mask & 0xC0U) == 0U) &&
        ((status->current_face <= LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE) ||
         (status->current_face == LEGACY_AIR_CALIBRATION_FACE_NOT_SELECTED)) &&
        (status->alignment_state <= LEGACY_AIR_ALIGNMENT_STATE_STALE) &&
        ((status->flags &
          (uint8_t)(~LEGACY_AIR_PREFLIGHT_FLAG_MASK_ALL)) == 0U) &&
        (LegacyAir_StartBlockReasonIsValid(status->start_block_reason) != 0U));
}

static uint8_t LegacyAir_SensorStatusFieldsAreValid(
    const LegacyAirSensorStatusPayload *status)
{
    if ((status == NULL) ||
        (status->sensor_id == SILVERSTAR_SENSOR_ID_INVALID) ||
        (status->total == 0U) || (status->index >= status->total))
    {
        return 0U;
    }
    return (uint8_t)((status->detail_code <=
                      LEGACY_AIR_SENSOR_DETAIL_UNSUPPORTED) ||
                     (status->detail_code == LEGACY_AIR_SENSOR_DETAIL_OTHER));
}

static uint8_t LegacyAir_CommandFieldsAreValid(const uint8_t *frame)
{
    uint8_t command_id;
    uint8_t param0;
    uint8_t param1;

    SILVERSTAR_ASSERT(frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(frame[0] == LEGACY_AIR_TYPE_CMD,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    command_id = frame[2];
    param0 = frame[7];
    param1 = frame[8];
    switch (command_id)
    {
        case LEGACY_AIR_CMD_CAPABILITY_ACK:
            return (uint8_t)(param1 == LEGACY_AIR_PROFILE_ID_CURRENT);

        case LEGACY_AIR_CMD_NAV_SUBSCRIBE:
            return (uint8_t)((param0 == LEGACY_AIR_NAV_SCHEMA_VERSION) && (param1 == 0U));

        case LEGACY_AIR_CMD_CAL_START:
            return (uint8_t)((param0 <= LEGACY_AIR_CALIBRATION_MODE_SIX_FACE) &&
                             (param1 == 0U));

        case LEGACY_AIR_CMD_CAL_FACE:
            return (uint8_t)((param0 <= LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE) &&
                             (param1 == 0U));

        case LEGACY_AIR_CMD_START_MISSION:
        case LEGACY_AIR_CMD_PING:
        case LEGACY_AIR_CMD_LOCK:
        case LEGACY_AIR_CMD_UNLOCK:
        case LEGACY_AIR_CMD_CAL_STOP:
        case LEGACY_AIR_CMD_CAL_RESET:
        case LEGACY_AIR_CMD_ALIGN_START:
        case LEGACY_AIR_CMD_ALIGN_STOP:
        case LEGACY_AIR_CMD_ALIGN_RESET:
            return (uint8_t)((param0 == 0U) && (param1 == 0U));

        default:
            return 0U;
    }
}

static int16_t LegacyAir_PhysicalToI16(float value,
                                 float full_scale,
                                 uint32_t *saturation_count)
{
    float scaled = (value / full_scale) * 32768.0f;
    long rounded;

    SILVERSTAR_ASSERT_OBJECT(saturation_count, uint32_t,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (scaled > (float)INT16_MAX)
    {
        (*saturation_count)++;
        return INT16_MAX;
    }
    if (scaled < (float)INT16_MIN)
    {
        (*saturation_count)++;
        return INT16_MIN;
    }
    rounded = lroundf(scaled);
    if (rounded > INT16_MAX)
    {
        (*saturation_count)++;
        return INT16_MAX;
    }
    if (rounded < INT16_MIN)
    {
        (*saturation_count)++;
        return INT16_MIN;
    }
    return (int16_t)rounded;
}

static void LegacyAir_StatePrefixPut(uint8_t type,
                               uint8_t seq,
                               uint32_t time_ms,
                               const int16_t accel_i16[3],
                               const int16_t gyro_i16[3],
                               const int16_t quaternion_q15[4],
                               uint8_t *frame)
{
    uint8_t index;

    SILVERSTAR_ASSERT(frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(accel_i16 != NULL,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    frame[0] = type;
    frame[1] = seq;
    LegacyAir_PutU32Le(&frame[2], time_ms);
    for (index = 0U; index < 3U; index++)
    {
        LegacyAir_PutI16Le(&frame[6U + ((uint16_t)index * 2U)],
                     accel_i16[index]);
        LegacyAir_PutI16Le(&frame[12U + ((uint16_t)index * 2U)],
                     gyro_i16[index]);
    }
    for (index = 0U; index < 4U; index++)
    {
        LegacyAir_PutI16Le(&frame[18U + ((uint16_t)index * 2U)],
                     quaternion_q15[index]);
    }
}

uint8_t LegacyAir_GetExpectedFrameLength(uint8_t air_type)
{
    switch (air_type)
    {
        case LEGACY_AIR_TYPE_FLIGHT_STATE: return LEGACY_AIR_FLIGHT_STATE_LEN;
        case LEGACY_AIR_TYPE_PREFLIGHT_STATE: return LEGACY_AIR_PREFLIGHT_STATE_LEN;
        case LEGACY_AIR_TYPE_CAPABILITY: return LEGACY_AIR_CAPABILITY_LEN;
        case LEGACY_AIR_TYPE_PREFLIGHT_STATUS: return LEGACY_AIR_PREFLIGHT_STATUS_LEN;
        case LEGACY_AIR_TYPE_SENSOR_STATUS: return LEGACY_AIR_SENSOR_STATUS_LEN;
        case LEGACY_AIR_TYPE_NAV_CAPABILITY: return LEGACY_AIR_NAV_CAPABILITY_LEN;
        case LEGACY_AIR_TYPE_NAV_PREPARATION: return LEGACY_AIR_NAV_PREPARATION_LEN;
        case LEGACY_AIR_TYPE_NAV_HEALTH: return LEGACY_AIR_NAV_HEALTH_LEN;
        case LEGACY_AIR_TYPE_STATUS: return LEGACY_AIR_STATUS_LEN;
        case LEGACY_AIR_TYPE_CMD: return LEGACY_AIR_CMD_LEN;
        case LEGACY_AIR_TYPE_ACK: return LEGACY_AIR_ACK_LEN;
        default: return 0U;
    }
}

static LegacyAirParseResult LegacyAir_CapabilityFrameValidate(const uint8_t *frame)
{
    LegacyAirCapabilityPayload capability;

    SILVERSTAR_ASSERT(frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(frame[0] == LEGACY_AIR_TYPE_CAPABILITY,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    capability.air_profile_id = frame[2];
    capability.command_policy = frame[3];
    capability.calibration_mode_mask = frame[4];
    capability.sensor_summary_flags = frame[5];
    capability.accel_full_scale_g = frame[6];
    capability.gyro_full_scale_dps = LegacyAir_GetU16Le(&frame[7]);
    return (LegacyAir_CapabilityFieldsAreValid(&capability) != 0U) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

static LegacyAirParseResult LegacyAir_PreflightStatusFrameValidate(const uint8_t *frame)
{
    LegacyAirPreflightStatusPayload status;

    SILVERSTAR_ASSERT(frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(frame[0] == LEGACY_AIR_TYPE_PREFLIGHT_STATUS,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((frame[6] & 0xF0U) != 0U)
    {
        return LEGACY_AIR_PARSE_BAD_FIELD;
    }
    status.lifecycle_state = frame[2];
    status.calibration_state = frame[3] & 0x0FU;
    status.calibration_mode = (frame[3] >> 4U) & 0x0FU;
    if (status.calibration_mode == 0x0FU)
    {
        status.calibration_mode = LEGACY_AIR_CALIBRATION_MODE_NOT_SELECTED;
    }
    status.completed_face_mask = frame[4];
    status.current_face = frame[5];
    status.alignment_state = frame[6] & 0x0FU;
    status.flags = frame[7];
    status.start_block_reason = frame[8];
    return (LegacyAir_PreflightStatusFieldsAreValid(&status) != 0U) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

static LegacyAirParseResult LegacyAir_SensorStatusFrameValidate(const uint8_t *frame)
{
    LegacyAirSensorStatusPayload status;

    status.snapshot_id = frame[2];
    status.sensor_id = frame[3];
    status.instance_id = frame[4];
    status.status_flags = frame[5];
    status.detail_code = frame[6];
    status.index = frame[7];
    status.total = frame[8];
    return (LegacyAir_SensorStatusFieldsAreValid(&status) != 0U) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

static LegacyAirParseResult LegacyAir_StatusFrameValidate(const uint8_t *frame)
{
    if (LegacyAir_StatusIdIsValid(frame[2]) == 0U)
    {
        return LEGACY_AIR_PARSE_BAD_ID;
    }
    return (LegacyAir_StatusFieldsAreValid(frame[2], frame[7], frame[8]) != 0U) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

static LegacyAirParseResult LegacyAir_CommandFrameValidate(const uint8_t *frame)
{
    if (LegacyAir_CmdIdIsValid(frame[2]) == 0U)
    {
        return LEGACY_AIR_PARSE_BAD_ID;
    }
    if (LegacyAir_CmdTokenIsValid(frame[2], LegacyAir_GetU32Le(&frame[3])) == 0U)
    {
        return LEGACY_AIR_PARSE_BAD_TOKEN;
    }
    return (LegacyAir_CommandFieldsAreValid(frame) != 0U) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

static LegacyAirParseResult LegacyAir_AckFrameValidate(const uint8_t *frame)
{
    if (((LegacyAir_CmdIdIsValid(frame[3]) == 0U) &&
         (frame[4] != LEGACY_AIR_ACK_RESULT_BAD_CMD)) ||
        (LegacyAir_AckResultIsValid(frame[4]) == 0U))
    {
        return LEGACY_AIR_PARSE_BAD_FIELD;
    }
    return LEGACY_AIR_PARSE_OK;
}

static LegacyAirParseResult LegacyAir_NavigationFrameValidate(const uint8_t *frame)
{
    if (LegacyAir_GetU16Le(&frame[2]) == 0U) { return LEGACY_AIR_PARSE_BAD_FIELD; }
    if (frame[0] == LEGACY_AIR_TYPE_NAV_CAPABILITY)
    {
        return ((frame[6] == LEGACY_AIR_NAV_SCHEMA_VERSION) && (frame[7] <= 2U) &&
            ((frame[8] & (uint8_t)~LEGACY_AIR_NAV_GROUP_MASK) == 0U)) ?
            LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
    }
    if (frame[0] == LEGACY_AIR_TYPE_NAV_PREPARATION)
    {
        return ((((frame[6] | frame[7]) & (uint8_t)~LEGACY_AIR_NAV_PREPARATION_MASK) == 0U) &&
            (LegacyAir_StartBlockReasonIsValid(frame[8]) != 0U)) ?
            LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
    }
    return ((((frame[6] & 7U) <= 4U) && ((frame[6] >> 3U) <= 8U)) ||
            (((frame[6] & 7U) == 7U) && ((frame[6] >> 3U) <= 16U))) ?
        LEGACY_AIR_PARSE_OK : LEGACY_AIR_PARSE_BAD_FIELD;
}

LegacyAirParseResult LegacyAir_FrameValidate(const uint8_t *frame, uint8_t frame_len)
{
    uint8_t expected_len;

    if ((frame == NULL) || (frame_len < 2U))
    {
        return LEGACY_AIR_PARSE_BAD_PARAM;
    }
    SILVERSTAR_ASSERT(frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(frame_len <= LEGACY_AIR_MAX_FRAME_LEN,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    expected_len = LegacyAir_GetExpectedFrameLength(frame[0]);
    if (expected_len == 0U)
    {
        return LEGACY_AIR_PARSE_BAD_TYPE;
    }
    if (frame_len != expected_len)
    {
        return LEGACY_AIR_PARSE_BAD_LEN;
    }

    switch (frame[0])
    {
        case LEGACY_AIR_TYPE_CAPABILITY:
            return LegacyAir_CapabilityFrameValidate(frame);
        case LEGACY_AIR_TYPE_PREFLIGHT_STATUS:
            return LegacyAir_PreflightStatusFrameValidate(frame);
        case LEGACY_AIR_TYPE_SENSOR_STATUS:
            return LegacyAir_SensorStatusFrameValidate(frame);
        case LEGACY_AIR_TYPE_NAV_CAPABILITY:
        case LEGACY_AIR_TYPE_NAV_PREPARATION:
        case LEGACY_AIR_TYPE_NAV_HEALTH:
            return LegacyAir_NavigationFrameValidate(frame);
        case LEGACY_AIR_TYPE_STATUS:
            return LegacyAir_StatusFrameValidate(frame);
        case LEGACY_AIR_TYPE_CMD:
            return LegacyAir_CommandFrameValidate(frame);
        case LEGACY_AIR_TYPE_ACK:
            return LegacyAir_AckFrameValidate(frame);
        case LEGACY_AIR_TYPE_FLIGHT_STATE:
        case LEGACY_AIR_TYPE_PREFLIGHT_STATE:
        default:
            return LEGACY_AIR_PARSE_OK;
    }
}

LegacyAirBuildResult LegacyAir_NavigationStatusBuild(uint8_t seq, uint8_t air_type,
    const LegacyAirNavigationStatusPayload *status, uint8_t *out_frame,
    uint8_t out_size, uint8_t *out_len)
{
    if ((status == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    *out_len = 0U;
    SILVERSTAR_ASSERT_OBJECT(status, LegacyAirNavigationStatusPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if ((air_type < LEGACY_AIR_TYPE_NAV_CAPABILITY) || (air_type > LEGACY_AIR_TYPE_NAV_HEALTH))
    {
        return LEGACY_AIR_BUILD_BAD_TYPE;
    }
    if (out_size < LEGACY_AIR_NAV_CAPABILITY_LEN) { return LEGACY_AIR_BUILD_BAD_LEN; }
    out_frame[0] = air_type;
    out_frame[1] = seq;
    LegacyAir_PutU16Le(&out_frame[2], status->session);
    LegacyAir_PutU16Le(&out_frame[4], status->generation);
    (void)memcpy(&out_frame[6], status->tail, sizeof(status->tail));
    if (LegacyAir_NavigationFrameValidate(out_frame) != LEGACY_AIR_PARSE_OK)
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    *out_len = LEGACY_AIR_NAV_CAPABILITY_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirBuildResult LegacyAir_CapabilityBuild(uint8_t seq,
                                   const LegacyAirCapabilityPayload *capability,
                                   uint8_t *out_frame,
                                   uint8_t out_size,
                                   uint8_t *out_len)
{
    if ((capability == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(capability, LegacyAirCapabilityPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (LegacyAir_CapabilityFieldsAreValid(capability) == 0U)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    if (out_size < LEGACY_AIR_CAPABILITY_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    out_frame[0] = LEGACY_AIR_TYPE_CAPABILITY;
    out_frame[1] = seq;
    out_frame[2] = capability->air_profile_id;
    out_frame[3] = capability->command_policy;
    out_frame[4] = capability->calibration_mode_mask;
    out_frame[5] = capability->sensor_summary_flags;
    out_frame[6] = capability->accel_full_scale_g;
    LegacyAir_PutU16Le(&out_frame[7], capability->gyro_full_scale_dps);
    *out_len = LEGACY_AIR_CAPABILITY_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirParseResult LegacyAir_CapabilityParse(const uint8_t *frame,
                                   uint8_t frame_len,
                                   LegacyAirCapabilityPayload *capability)
{
    LegacyAirParseResult result;

    if ((frame == NULL) || (capability == NULL))
    {
        return LEGACY_AIR_PARSE_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(capability, LegacyAirCapabilityPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    result = LegacyAir_FrameValidate(frame, frame_len);
    if (result != LEGACY_AIR_PARSE_OK)
    {
        return result;
    }
    if (frame[0] != LEGACY_AIR_TYPE_CAPABILITY)
    {
        return LEGACY_AIR_PARSE_BAD_TYPE;
    }
    capability->air_profile_id = frame[2];
    capability->command_policy = frame[3];
    capability->calibration_mode_mask = frame[4];
    capability->sensor_summary_flags = frame[5];
    capability->accel_full_scale_g = frame[6];
    capability->gyro_full_scale_dps = LegacyAir_GetU16Le(&frame[7]);
    return LEGACY_AIR_PARSE_OK;
}

LegacyAirBuildResult LegacyAir_CompactV0ImuQuantize(
    const float accel_b_mps2[3],
    const float gyro_b_radps[3],
    LegacyAirCompactV0ImuQuantized *quantized)
{
    const float accel_full_scale_mps2 =
        (float)LEGACY_AIR_ACCEL_FULL_SCALE_G * LEGACY_AIR_STANDARD_GRAVITY_MPS2;
    const float gyro_full_scale_radps =
        (float)LEGACY_AIR_GYRO_FULL_SCALE_DPS * LEGACY_AIR_PI_F / 180.0f;
    uint8_t index;

    if ((accel_b_mps2 == NULL) || (gyro_b_radps == NULL) ||
        (quantized == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(quantized, LegacyAirCompactV0ImuQuantized,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    (void)memset(quantized, 0, sizeof(*quantized));
    for (index = 0U; index < 3U; index++)
    {
        if ((!isfinite(accel_b_mps2[index])) ||
            (!isfinite(gyro_b_radps[index])))
        {
            return LEGACY_AIR_BUILD_BAD_PARAM;
        }
        quantized->accel_i16[index] = LegacyAir_PhysicalToI16(
            accel_b_mps2[index], accel_full_scale_mps2,
            &quantized->saturation_count);
        quantized->gyro_i16[index] = LegacyAir_PhysicalToI16(
            gyro_b_radps[index], gyro_full_scale_radps,
            &quantized->saturation_count);
    }
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirBuildResult LegacyAir_PreflightStatusBuild(
    uint8_t seq,
    const LegacyAirPreflightStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len)
{
    uint8_t calibration_mode;

    if ((status == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(status, LegacyAirPreflightStatusPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (LegacyAir_PreflightStatusFieldsAreValid(status) == 0U)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    if (out_size < LEGACY_AIR_PREFLIGHT_STATUS_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    calibration_mode = (status->calibration_mode ==
        LEGACY_AIR_CALIBRATION_MODE_NOT_SELECTED) ? 0x0FU :
        status->calibration_mode;
    out_frame[0] = LEGACY_AIR_TYPE_PREFLIGHT_STATUS;
    out_frame[1] = seq;
    out_frame[2] = status->lifecycle_state;
    out_frame[3] = (uint8_t)(
        (status->calibration_state & 0x0FU) |
        ((calibration_mode & 0x0FU) << 4U));
    out_frame[4] = status->completed_face_mask;
    out_frame[5] = status->current_face;
    out_frame[6] = (uint8_t)(status->alignment_state & 0x0FU);
    out_frame[7] = status->flags;
    out_frame[8] = status->start_block_reason;
    *out_len = LEGACY_AIR_PREFLIGHT_STATUS_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirParseResult LegacyAir_PreflightStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    LegacyAirPreflightStatusPayload *status)
{
    LegacyAirParseResult result;

    if ((frame == NULL) || (status == NULL))
    {
        return LEGACY_AIR_PARSE_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(status, LegacyAirPreflightStatusPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    result = LegacyAir_FrameValidate(frame, frame_len);
    if (result != LEGACY_AIR_PARSE_OK) { return result; }
    if (frame[0] != LEGACY_AIR_TYPE_PREFLIGHT_STATUS)
    {
        return LEGACY_AIR_PARSE_BAD_TYPE;
    }
    status->lifecycle_state = frame[2];
    status->calibration_state = frame[3] & 0x0FU;
    status->calibration_mode = (frame[3] >> 4U) & 0x0FU;
    if (status->calibration_mode == 0x0FU)
    {
        status->calibration_mode = LEGACY_AIR_CALIBRATION_MODE_NOT_SELECTED;
    }
    status->completed_face_mask = frame[4];
    status->current_face = frame[5];
    status->alignment_state = frame[6] & 0x0FU;
    status->flags = frame[7];
    status->start_block_reason = frame[8];
    return LEGACY_AIR_PARSE_OK;
}

LegacyAirBuildResult LegacyAir_SensorStatusBuild(
    uint8_t seq,
    const LegacyAirSensorStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len)
{
    if ((status == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(status, LegacyAirSensorStatusPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (out_size < LEGACY_AIR_SENSOR_STATUS_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    if (LegacyAir_SensorStatusFieldsAreValid(status) == 0U)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    out_frame[0] = LEGACY_AIR_TYPE_SENSOR_STATUS;
    out_frame[1] = seq;
    out_frame[2] = status->snapshot_id;
    out_frame[3] = status->sensor_id;
    out_frame[4] = status->instance_id;
    out_frame[5] = status->status_flags;
    out_frame[6] = status->detail_code;
    out_frame[7] = status->index;
    out_frame[8] = status->total;
    *out_len = LEGACY_AIR_SENSOR_STATUS_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirParseResult LegacyAir_SensorStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    LegacyAirSensorStatusPayload *status)
{
    LegacyAirParseResult result;

    if ((frame == NULL) || (status == NULL))
    {
        return LEGACY_AIR_PARSE_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(status, LegacyAirSensorStatusPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    result = LegacyAir_FrameValidate(frame, frame_len);
    if (result != LEGACY_AIR_PARSE_OK) { return result; }
    if (frame[0] != LEGACY_AIR_TYPE_SENSOR_STATUS)
    {
        return LEGACY_AIR_PARSE_BAD_TYPE;
    }
    status->snapshot_id = frame[2];
    status->sensor_id = frame[3];
    status->instance_id = frame[4];
    status->status_flags = frame[5];
    status->detail_code = frame[6];
    status->index = frame[7];
    status->total = frame[8];
    return LEGACY_AIR_PARSE_OK;
}

LegacyAirBuildResult LegacyAir_PreflightStateBuild(
    uint8_t seq,
    const LegacyAirPreflightStatePayload *state,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len)
{
    if ((state == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(state, LegacyAirPreflightStatePayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (out_size < LEGACY_AIR_PREFLIGHT_STATE_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    LegacyAir_StatePrefixPut(LEGACY_AIR_TYPE_PREFLIGHT_STATE, seq, state->time_ms,
                       state->accel_i16, state->gyro_i16,
                       state->quaternion_q15, out_frame);
    *out_len = LEGACY_AIR_PREFLIGHT_STATE_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirBuildResult LegacyAir_FlightStateBuild(uint8_t seq,
                                    const LegacyAirFlightStatePayload *state,
                                    uint8_t *out_frame,
                                    uint8_t out_size,
                                    uint8_t *out_len)
{
    uint8_t index;

    if ((state == NULL) || (out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(state, LegacyAirFlightStatePayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (out_size < LEGACY_AIR_FLIGHT_STATE_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    LegacyAir_StatePrefixPut(LEGACY_AIR_TYPE_FLIGHT_STATE, seq, state->time_ms,
                       state->accel_i16, state->gyro_i16,
                       state->quaternion_q15, out_frame);
    for (index = 0U; index < 3U; index++)
    {
        LegacyAir_PutFloatLe(&out_frame[26U + ((uint16_t)index * 4U)],
                       state->velocity_enu_mps[index]);
        LegacyAir_PutFloatLe(&out_frame[38U + ((uint16_t)index * 4U)],
                       state->position_enu_m[index]);
    }
    *out_len = LEGACY_AIR_FLIGHT_STATE_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirBuildResult LegacyAir_StatusBuild(uint8_t seq,
                               uint8_t status_id,
                               uint32_t time_ms,
                               uint8_t arg0,
                               uint8_t arg1,
                               uint8_t *out_frame,
                               uint8_t out_size,
                               uint8_t *out_len)
{
    if ((out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT(out_frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(out_len != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (LegacyAir_StatusIdIsValid(status_id) == 0U)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_TYPE;
    }
    if (LegacyAir_StatusFieldsAreValid(status_id, arg0, arg1) == 0U)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    if (out_size < LEGACY_AIR_STATUS_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    out_frame[0] = LEGACY_AIR_TYPE_STATUS;
    out_frame[1] = seq;
    out_frame[2] = status_id;
    LegacyAir_PutU32Le(&out_frame[3], time_ms);
    out_frame[7] = arg0;
    out_frame[8] = arg1;
    *out_len = LEGACY_AIR_STATUS_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirBuildResult LegacyAir_AckBuild(uint8_t seq,
                            uint8_t ack_seq,
                            uint8_t ack_cmd_id,
                            uint8_t result,
                            uint32_t time_ms,
                            uint8_t *out_frame,
                            uint8_t out_size,
                            uint8_t *out_len)
{
    if ((out_frame == NULL) || (out_len == NULL))
    {
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    SILVERSTAR_ASSERT(out_frame != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(out_len != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    if (((LegacyAir_CmdIdIsValid(ack_cmd_id) == 0U) &&
         (result != LEGACY_AIR_ACK_RESULT_BAD_CMD)) ||
        (LegacyAir_AckResultIsValid(result) == 0U))
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_PARAM;
    }
    if (out_size < LEGACY_AIR_ACK_LEN)
    {
        *out_len = 0U;
        return LEGACY_AIR_BUILD_BAD_LEN;
    }
    out_frame[0] = LEGACY_AIR_TYPE_ACK;
    out_frame[1] = seq;
    out_frame[2] = ack_seq;
    out_frame[3] = ack_cmd_id;
    out_frame[4] = result;
    LegacyAir_PutU32Le(&out_frame[5], time_ms);
    *out_len = LEGACY_AIR_ACK_LEN;
    return LEGACY_AIR_BUILD_OK;
}

LegacyAirParseResult LegacyAir_CmdParse(const uint8_t *frame, uint8_t frame_len,
                            LegacyAirCmdPayload *cmd)
{
    LegacyAirParseResult validate_result;

    if ((frame == NULL) || (cmd == NULL))
    {
        return LEGACY_AIR_PARSE_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(cmd, LegacyAirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    validate_result = LegacyAir_FrameValidate(frame, frame_len);
    if (validate_result != LEGACY_AIR_PARSE_OK)
    {
        return validate_result;
    }
    if (frame[0] != LEGACY_AIR_TYPE_CMD)
    {
        return LEGACY_AIR_PARSE_BAD_TYPE;
    }
    cmd->seq = frame[1];
    cmd->cmd_id = frame[2];
    cmd->token = LegacyAir_GetU32Le(&frame[3]);
    cmd->param0 = frame[7];
    cmd->param1 = frame[8];
    return LEGACY_AIR_PARSE_OK;
}

uint8_t LegacyAir_CmdTokenIsValid(uint8_t cmd_id, uint32_t token)
{
    SILVERSTAR_ASSERT(LEGACY_AIR_CMD_START_MISSION <= LEGACY_AIR_CMD_ALIGN_RESET,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(LEGACY_AIR_CMD_ALIGN_RESET <= UINT8_MAX,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (cmd_id)
    {
        case LEGACY_AIR_CMD_START_MISSION:
            return (token == LEGACY_AIR_TOKEN_START_MISSION) ? 1U : 0U;
        case LEGACY_AIR_CMD_LOCK:
            return (token == LEGACY_AIR_TOKEN_LOCK) ? 1U : 0U;
        case LEGACY_AIR_CMD_UNLOCK:
            return (token == LEGACY_AIR_TOKEN_UNLOCK) ? 1U : 0U;
        case LEGACY_AIR_CMD_NAV_SUBSCRIBE:
            return (uint8_t)(((token & 0xFFFF0000UL) == LEGACY_AIR_TOKEN_NAV_SUBSCRIBE) &&
                ((token & 0xFFFFUL) != 0U));
        case LEGACY_AIR_CMD_CAL_START:
        case LEGACY_AIR_CMD_CAL_FACE:
        case LEGACY_AIR_CMD_CAL_STOP:
        case LEGACY_AIR_CMD_CAL_RESET:
            return (token == LEGACY_AIR_TOKEN_CALIBRATION) ? 1U : 0U;
        case LEGACY_AIR_CMD_ALIGN_START:
        case LEGACY_AIR_CMD_ALIGN_STOP:
        case LEGACY_AIR_CMD_ALIGN_RESET:
            return (token == LEGACY_AIR_TOKEN_ALIGNMENT) ? 1U : 0U;
        case LEGACY_AIR_CMD_PING:
        case LEGACY_AIR_CMD_CAPABILITY_ACK:
            return 1U;
        default:
            return 0U;
    }
}

uint8_t LegacyAir_CmdIdIsValid(uint8_t cmd_id)
{
    SILVERSTAR_ASSERT(LEGACY_AIR_CMD_START_MISSION <= LEGACY_AIR_CMD_ALIGN_RESET,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(LEGACY_AIR_CMD_ALIGN_RESET <= UINT8_MAX,
        SILVERSTAR_ASSERT_MODULE_PROTOCOL,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (cmd_id)
    {
        case LEGACY_AIR_CMD_START_MISSION:
        case LEGACY_AIR_CMD_PING:
        case LEGACY_AIR_CMD_LOCK:
        case LEGACY_AIR_CMD_UNLOCK:
        case LEGACY_AIR_CMD_CAPABILITY_ACK:
        case LEGACY_AIR_CMD_CAL_START:
        case LEGACY_AIR_CMD_NAV_SUBSCRIBE:
        case LEGACY_AIR_CMD_CAL_FACE:
        case LEGACY_AIR_CMD_CAL_STOP:
        case LEGACY_AIR_CMD_CAL_RESET:
        case LEGACY_AIR_CMD_ALIGN_START:
        case LEGACY_AIR_CMD_ALIGN_STOP:
        case LEGACY_AIR_CMD_ALIGN_RESET:
            return 1U;
        default:
            return 0U;
    }
}

uint8_t LegacyAir_StatusIdIsValid(uint8_t status_id)
{
    return (uint8_t)((status_id >= LEGACY_AIR_STATUS_BOOT) &&
                     (status_id <= LEGACY_AIR_STATUS_CALIBRATION_DIAGNOSTIC));
}

uint8_t LegacyAir_AckResultIsValid(uint8_t result)
{
    return (uint8_t)(result <= LEGACY_AIR_ACK_RESULT_PREPARE_FAILED);
}
