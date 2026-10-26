#include "ss_tm_protocol.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "silverstar_assert.h"

#define SS_TM_VERSION 1U
#define SS_TM_HEADER_SIZE 8U
#define SS_TM_PROFILE_MASK 0x80U
#define SS_TM_POSITION_TYPE 0x18U
#define SS_TM_HEALTH_TYPE 0x19U
#define SS_TM_POSITION_LENGTH 28U
#define SS_TM_HEALTH_LENGTH 16U
#define SS_TM_HEALTH_MASK 0x07FFU
#define SS_TM_POSITION_MASK 0x3FU

static uint32_t s_boot_session;
static uint32_t s_event_id;
static uint16_t s_sequence;
static uint8_t s_tm_profile;
static uint64_t s_monotonic_us;

static void SsTm_Put(uint8_t *out, uint64_t value, uint8_t width)
{
    uint8_t index;
    SILVERSTAR_ASSERT(out != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT((width > 0U) && (width <= 8U), SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U; index < width; index++) { out[index] = (uint8_t)(value >> (8U * index)); }
}

static uint64_t SsTm_Get(const uint8_t *data, uint8_t width)
{
    uint64_t value = 0ULL;
    uint8_t index;
    SILVERSTAR_ASSERT(data != NULL, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT((width > 0U) && (width <= 8U), SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (index = 0U; index < width; index++) { value |= ((uint64_t)data[index]) << (8U * index); }
    return value;
}

SsTmSessionResult SsTm_SessionSet(uint8_t profile, uint32_t boot_session)
{
    if ((profile > 1U) || (boot_session == 0U)) { return SS_TM_SESSION_INVALID; }
    if ((s_boot_session != boot_session) || (s_tm_profile != profile))
    { s_sequence = 0U; s_event_id = 0U; }
    s_boot_session = boot_session;
    s_tm_profile = profile;
    return SS_TM_SESSION_OK;
}

void SsTm_TimeSet(uint64_t monotonic_us) { s_monotonic_us = monotonic_us; }
uint16_t SsTm_FrameSequenceGet(const uint8_t *frame) { return (uint16_t)SsTm_Get(&frame[2], 2U); }
uint8_t SsTm_FrameTypeGet(const uint8_t *frame) { return frame[1] & 0x7FU; }

uint32_t SsTm_EventIdNext(void)
{
    if (s_event_id == UINT32_MAX) { return 0U; }
    s_event_id++;
    return s_event_id;
}

static AirBuildResult SsTm_HeaderBuild(uint8_t type, uint8_t size, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    if ((out == NULL) || (length == NULL) || (s_boot_session == 0U)) { return AIR_BUILD_BAD_PARAM; }
    *length = 0U;
    if ((size < SS_TM_HEADER_SIZE) || (size > AIR_MAX_FRAME_LEN) || (capacity < size)) { return AIR_BUILD_BAD_LEN; }
    SILVERSTAR_ASSERT(s_tm_profile <= 1U, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(type < SS_TM_PROFILE_MASK, SILVERSTAR_ASSERT_MODULE_PROTOCOL, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    out[0] = SS_TM_VERSION;
    out[1] = (uint8_t)(type | (uint8_t)(s_tm_profile << 7U));
    SsTm_Put(&out[2], s_sequence, 2U);
    s_sequence++;
    SsTm_Put(&out[4], s_boot_session, 4U);
    *length = size;
    return AIR_BUILD_OK;
}

AirBuildResult SsTm_SequenceRefresh(uint8_t *frame, uint8_t length)
{
    uint8_t size = 0U;
    uint8_t type;
    if ((frame == NULL) || (length < SS_TM_HEADER_SIZE)) { return AIR_BUILD_BAD_PARAM; }
    if (Air_FrameValidate(frame, length) != AIR_PARSE_OK) { return AIR_BUILD_BAD_PARAM; }
    type = frame[1] & 0x7FU;
    return SsTm_HeaderBuild(type, length, frame, length, &size);
}

uint8_t Air_GetExpectedFrameLength(uint8_t type)
{
    switch (type)
    {
        case AIR_TYPE_FLIGHT_STATE: return AIR_FLIGHT_STATE_LEN;
        case AIR_TYPE_PREFLIGHT_STATE: return AIR_PREFLIGHT_STATE_LEN;
        case AIR_TYPE_CAPABILITY: return AIR_CAPABILITY_LEN;
        case AIR_TYPE_PREFLIGHT_STATUS: return AIR_PREFLIGHT_STATUS_LEN;
        case AIR_TYPE_SENSOR_STATUS: return AIR_SENSOR_STATUS_LEN;
        case AIR_TYPE_NAV_CAPABILITY: return AIR_NAV_CAPABILITY_LEN;
        case AIR_TYPE_NAV_PREPARATION: return AIR_NAV_PREPARATION_LEN;
        case AIR_TYPE_NAV_HEALTH: return AIR_NAV_HEALTH_LEN;
        case AIR_TYPE_STATUS: return AIR_STATUS_LEN;
        case AIR_TYPE_ACK: return AIR_ACK_LEN;
        case AIR_TYPE_CMD: return AIR_CMD_LEN;
        case SS_TM_POSITION_TYPE: return SS_TM_POSITION_LENGTH;
        case SS_TM_HEALTH_TYPE: return SS_TM_HEALTH_LENGTH;
        default: return 0U;
    }
}

static AirBuildResult SsTm_Wrap(const uint8_t *legacy, uint8_t size, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t new_size;
    AirBuildResult result;
    if ((legacy == NULL) || (size < 2U) || (size > LEGACY_AIR_MAX_FRAME_LEN)) { return AIR_BUILD_BAD_PARAM; }
    new_size = Air_GetExpectedFrameLength(legacy[0]);
    result = SsTm_HeaderBuild(legacy[0], new_size, out, capacity, length);
    if (result != AIR_BUILD_OK) { return result; }
    (void)memcpy(&out[SS_TM_HEADER_SIZE], &legacy[2], (size_t)size - 2U);
    if (legacy[0] == AIR_TYPE_CAPABILITY)
    { out[15] = 1U; SsTm_Put(&out[16], s_monotonic_us, 8U); }
    return AIR_BUILD_OK;
}

static AirParseResult SsTm_PositionValidate(const uint8_t *frame)
{
    int32_t latitude = (int32_t)(uint32_t)SsTm_Get(&frame[8], 4U);
    int32_t longitude = (int32_t)(uint32_t)SsTm_Get(&frame[12], 4U);
    int32_t height = (int32_t)(uint32_t)SsTm_Get(&frame[16], 4U);
    uint8_t flags = frame[26];
    if ((flags & (uint8_t)~SS_TM_POSITION_MASK) != 0U) { return AIR_PARSE_BAD_FIELD; }
    if ((flags & 1U) != 0U)
    {
        if ((latitude < -900000000L) || (latitude > 900000000L) ||
            (longitude < -1800000000L) || (longitude > 1800000000L)) { return AIR_PARSE_BAD_FIELD; }
    }
    else if ((latitude != INT32_MIN) || (longitude != INT32_MIN)) { return AIR_PARSE_BAD_FIELD; }
    if ((((flags & 2U) != 0U) && (height == INT32_MIN)) ||
        (((flags & 2U) == 0U) && (height != INT32_MIN))) { return AIR_PARSE_BAD_FIELD; }
    if ((((flags & 16U) != 0U) && (((flags & 1U) == 0U) || ((flags & 4U) != 0U))) ||
        (((flags & 4U) != 0U) && ((flags & 1U) == 0U))) { return AIR_PARSE_BAD_FIELD; }
    return AIR_PARSE_OK;
}

static AirParseResult SsTm_HealthValidate(const uint8_t *frame)
{
    uint16_t known = (uint16_t)SsTm_Get(&frame[12], 2U);
    uint16_t fault = (uint16_t)SsTm_Get(&frame[14], 2U);
    if ((((known | fault) & (uint16_t)~SS_TM_HEALTH_MASK) != 0U) || ((fault & (uint16_t)~known) != 0U))
    { return AIR_PARSE_BAD_FIELD; }
    if ((SsTm_Get(&frame[8], 2U) == UINT16_MAX) && (SsTm_Get(&frame[10], 2U) != UINT16_MAX))
    { return AIR_PARSE_BAD_FIELD; }
    return AIR_PARSE_OK;
}

static AirParseResult SsTm_LegacyBodyValidate(const uint8_t *frame, uint8_t type)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = LegacyAir_GetExpectedFrameLength(type);
    if ((size < 2U) || (size > sizeof(legacy))) { return AIR_PARSE_BAD_TYPE; }
    legacy[0] = type; legacy[1] = 0U;
    (void)memcpy(&legacy[2], &frame[8], (size_t)size - 2U);
    if ((type == AIR_TYPE_CMD) && (legacy[2] == AIR_CMD_CAPABILITY_ACK)) { legacy[8] = 0U; }
    if (type == AIR_TYPE_CAPABILITY)
    {
        if ((frame[15] != 1U) || (frame[9] != (uint8_t)(s_tm_profile + 1U))) { return AIR_PARSE_BAD_FIELD; }
    }
    return LegacyAir_FrameValidate(legacy, size);
}

AirParseResult Air_FrameValidate(const uint8_t *frame, uint8_t frame_len)
{
    uint8_t type;
    if ((frame == NULL) || (frame_len < SS_TM_HEADER_SIZE) || (frame_len > AIR_MAX_FRAME_LEN)) { return AIR_PARSE_BAD_LEN; }
    if ((frame[0] != SS_TM_VERSION) || ((frame[1] >> 7U) != s_tm_profile) ||
        (SsTm_Get(&frame[4], 4U) != s_boot_session) || (s_boot_session == 0U)) { return AIR_PARSE_BAD_FIELD; }
    type = frame[1] & 0x7FU;
    if (Air_GetExpectedFrameLength(type) == 0U) { return AIR_PARSE_BAD_TYPE; }
    if (frame_len != Air_GetExpectedFrameLength(type)) { return AIR_PARSE_BAD_LEN; }
    if (type == SS_TM_POSITION_TYPE) { return SsTm_PositionValidate(frame); }
    if (type == SS_TM_HEALTH_TYPE) { return SsTm_HealthValidate(frame); }
    if (type == AIR_TYPE_STATUS)
    { return ((SsTm_Get(&frame[8], 4U) != 0U) && (SsTm_Get(&frame[20], 2U) != 0U)) ? AIR_PARSE_OK : AIR_PARSE_BAD_FIELD; }
    if (type == AIR_TYPE_ACK)
    { return (Air_AckResultIsValid(frame[11]) != 0U) ? AIR_PARSE_OK : AIR_PARSE_BAD_FIELD; }
    return SsTm_LegacyBodyValidate(frame, type);
}

AirParseResult Air_CmdParse(const uint8_t *frame, uint8_t frame_len, AirCmdPayload *cmd)
{
    AirParseResult result;
    if (cmd == NULL) { return AIR_PARSE_BAD_PARAM; }
    result = Air_FrameValidate(frame, frame_len);
    if (result != AIR_PARSE_OK) { return result; }
    if (SsTm_FrameTypeGet(frame) != AIR_TYPE_CMD) { return AIR_PARSE_BAD_TYPE; }
    cmd->seq = SsTm_FrameSequenceGet(frame); cmd->cmd_id = frame[8];
    cmd->token = (uint32_t)SsTm_Get(&frame[9], 4U); cmd->param0 = frame[13]; cmd->param1 = frame[14];
    return AIR_PARSE_OK;
}

AirBuildResult Air_AckBuild(uint16_t seq, uint16_t ack_seq, uint8_t command, uint8_t result_code,
    uint32_t time_ms, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    AirBuildResult result;
    (void)seq;
    if ((Air_AckResultIsValid(result_code) == 0U) ||
        ((Air_CmdIdIsValid(command) == 0U) && (result_code != AIR_ACK_RESULT_BAD_CMD))) { return AIR_BUILD_BAD_PARAM; }
    result = SsTm_HeaderBuild(AIR_TYPE_ACK, AIR_ACK_LEN, out, capacity, length);
    if (result != AIR_BUILD_OK) { return result; }
    SsTm_Put(&out[8], ack_seq, 2U); out[10] = command; out[11] = result_code;
    SsTm_Put(&out[12], time_ms, 4U);
    return AIR_BUILD_OK;
}

AirBuildResult SsTm_EventBuild(const SsTmEvent *event, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    AirBuildResult result;
    if ((event == NULL) || (event->event_id == 0U) || (event->event_code == 0U)) { return AIR_BUILD_BAD_PARAM; }
    result = SsTm_HeaderBuild(AIR_TYPE_STATUS, AIR_STATUS_LEN, out, capacity, length);
    if (result != AIR_BUILD_OK) { return result; }
    SsTm_Put(&out[8], event->event_id, 4U); SsTm_Put(&out[12], event->occurred_us, 8U);
    SsTm_Put(&out[20], event->event_code, 2U); SsTm_Put(&out[22], event->stage_id, 4U);
    SsTm_Put(&out[26], event->instance_id, 2U); SsTm_Put(&out[28], event->transaction_id, 2U);
    out[30] = event->arg0; out[31] = event->arg1;
    return AIR_BUILD_OK;
}

AirBuildResult Air_StatusBuild(uint16_t seq, uint8_t status_id, uint32_t time_ms,
    uint8_t arg0, uint8_t arg1, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    SsTmEvent event = {0};
    (void)seq; (void)time_ms;
    event.event_id = SsTm_EventIdNext(); event.occurred_us = s_monotonic_us;
    event.event_code = status_id; event.arg0 = arg0; event.arg1 = arg1;
    return SsTm_EventBuild(&event, out, capacity, length);
}

AirBuildResult SsTm_PositionBuild(int32_t latitude, int32_t longitude, int32_t height, uint32_t age_ms,
    uint16_t accuracy_cm, uint8_t flags, uint8_t satellites, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    AirBuildResult result = SsTm_HeaderBuild(SS_TM_POSITION_TYPE, SS_TM_POSITION_LENGTH, out, capacity, length);
    if (result != AIR_BUILD_OK) { return result; }
    SsTm_Put(&out[8], (uint32_t)latitude, 4U); SsTm_Put(&out[12], (uint32_t)longitude, 4U);
    SsTm_Put(&out[16], (uint32_t)height, 4U); SsTm_Put(&out[20], age_ms, 4U);
    SsTm_Put(&out[24], accuracy_cm, 2U); out[26] = flags; out[27] = satellites;
    if (SsTm_PositionValidate(out) != AIR_PARSE_OK) { *length = 0U; return AIR_BUILD_BAD_PARAM; }
    return AIR_BUILD_OK;
}

AirBuildResult SsTm_HealthBuild(uint16_t battery_mv, uint16_t age_ds, uint16_t known, uint16_t fault,
    uint8_t *out, uint8_t capacity, uint8_t *length)
{
    AirBuildResult result = SsTm_HeaderBuild(SS_TM_HEALTH_TYPE, SS_TM_HEALTH_LENGTH, out, capacity, length);
    if (result != AIR_BUILD_OK) { return result; }
    SsTm_Put(&out[8], battery_mv, 2U); SsTm_Put(&out[10], age_ds, 2U);
    SsTm_Put(&out[12], known, 2U); SsTm_Put(&out[14], fault, 2U);
    if (SsTm_HealthValidate(out) != AIR_PARSE_OK) { *length = 0U; return AIR_BUILD_BAD_PARAM; }
    return AIR_BUILD_OK;
}

AirBuildResult Air_CapabilityBuild(uint16_t seq, const AirCapabilityPayload *value, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    if ((value == NULL) || (value->command_policy != (uint8_t)(s_tm_profile + 1U)))
    { return AIR_BUILD_BAD_PARAM; }
    result = LegacyAir_CapabilityBuild(0U, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirBuildResult Air_PreflightStatusBuild(uint16_t seq, const AirPreflightStatusPayload *value, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    result = LegacyAir_PreflightStatusBuild(0U, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirBuildResult Air_SensorStatusBuild(uint16_t seq, const AirSensorStatusPayload *value, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    result = LegacyAir_SensorStatusBuild(0U, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirBuildResult Air_PreflightStateBuild(uint16_t seq, const AirPreflightStatePayload *value, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    result = LegacyAir_PreflightStateBuild(0U, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirBuildResult Air_FlightStateBuild(uint16_t seq, const AirFlightStatePayload *value, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    result = LegacyAir_FlightStateBuild(0U, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirBuildResult Air_NavigationStatusBuild(uint16_t seq, uint8_t type, const AirNavigationStatusPayload *value,
    uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t size = 0U;
    AirBuildResult result;
    (void)seq;
    result = LegacyAir_NavigationStatusBuild(0U, type, value, legacy, sizeof(legacy), &size);
    if (result != AIR_BUILD_OK) { return result; }
    return SsTm_Wrap(legacy, size, out, capacity, length);
}

AirParseResult Air_CapabilityParse(const uint8_t *frame, uint8_t size, AirCapabilityPayload *value)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t old_size = LEGACY_AIR_CAPABILITY_LEN;
    AirParseResult result = Air_FrameValidate(frame, size);
    if (result != AIR_PARSE_OK) { return result; }
    legacy[0] = SsTm_FrameTypeGet(frame); legacy[1] = 0U;
    (void)memcpy(&legacy[2], &frame[8], (size_t)old_size - 2U);
    return LegacyAir_CapabilityParse(legacy, old_size, value);
}

AirParseResult Air_PreflightStatusParse(const uint8_t *frame, uint8_t size, AirPreflightStatusPayload *value)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t old_size = LEGACY_AIR_PREFLIGHT_STATUS_LEN;
    AirParseResult result = Air_FrameValidate(frame, size);
    if (result != AIR_PARSE_OK) { return result; }
    legacy[0] = SsTm_FrameTypeGet(frame); legacy[1] = 0U;
    (void)memcpy(&legacy[2], &frame[8], (size_t)old_size - 2U);
    return LegacyAir_PreflightStatusParse(legacy, old_size, value);
}

AirParseResult Air_SensorStatusParse(const uint8_t *frame, uint8_t size, AirSensorStatusPayload *value)
{
    uint8_t legacy[LEGACY_AIR_MAX_FRAME_LEN];
    uint8_t old_size = LEGACY_AIR_SENSOR_STATUS_LEN;
    AirParseResult result = Air_FrameValidate(frame, size);
    if (result != AIR_PARSE_OK) { return result; }
    legacy[0] = SsTm_FrameTypeGet(frame); legacy[1] = 0U;
    (void)memcpy(&legacy[2], &frame[8], (size_t)old_size - 2U);
    return LegacyAir_SensorStatusParse(legacy, old_size, value);
}

AirBuildResult Air_CompactV0ImuQuantize(const float accel_b_mps2[3], const float gyro_b_radps[3], AirCompactV0ImuQuantized *quantized) { return LegacyAir_CompactV0ImuQuantize(accel_b_mps2, gyro_b_radps, quantized); }

uint8_t Air_CmdTokenIsValid(uint8_t cmd_id, uint32_t token) { return LegacyAir_CmdTokenIsValid(cmd_id, token); }

uint8_t Air_CmdIdIsValid(uint8_t cmd_id) { return LegacyAir_CmdIdIsValid(cmd_id); }

uint8_t Air_StatusIdIsValid(uint8_t status_id) { return LegacyAir_StatusIdIsValid(status_id); }

uint8_t Air_AckResultIsValid(uint8_t result) { return LegacyAir_AckResultIsValid(result); }
