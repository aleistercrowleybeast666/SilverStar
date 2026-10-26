#ifndef __SS_TM_LEGACY_H
#define __SS_TM_LEGACY_H

#include <stdint.h>

#include "silverstar_sensor_id.h"

#define LEGACY_AIR_PROTOCOL_COMPATIBILITY_TAG     "AIR-NCRC"
#define LEGACY_AIR_PROTOCOL_APPLICATION_CRC_SIZE  0U

#define LEGACY_AIR_STANDARD_GRAVITY_MPS2          9.80665f
#define LEGACY_AIR_ACCEL_FULL_SCALE_G             16U
#define LEGACY_AIR_GYRO_FULL_SCALE_DPS            2000U

#define LEGACY_AIR_MAX_FRAME_LEN                 50U
#define LEGACY_AIR_FLIGHT_STATE_LEN              50U
#define LEGACY_AIR_PREFLIGHT_STATE_LEN           26U
#define LEGACY_AIR_CAPABILITY_LEN                 9U
#define LEGACY_AIR_PREFLIGHT_STATUS_LEN            9U
#define LEGACY_AIR_SENSOR_STATUS_LEN               9U
#define LEGACY_AIR_NAV_CAPABILITY_LEN              9U
#define LEGACY_AIR_NAV_PREPARATION_LEN             9U
#define LEGACY_AIR_NAV_HEALTH_LEN                  9U
#define LEGACY_AIR_NAV_SCHEMA_VERSION             1U
#define LEGACY_AIR_NAV_PREPARATION_MASK            0x7FU
#define LEGACY_AIR_NAV_GROUP_MASK                  0x1FU
#define LEGACY_AIR_STATUS_LEN                     9U
#define LEGACY_AIR_CMD_LEN                        9U
#define LEGACY_AIR_ACK_LEN                        9U

#define LEGACY_AIR_TOKEN_START_MISSION           0xA55A3CC3UL
#define LEGACY_AIR_TOKEN_LOCK                    0xC33CA55AUL
#define LEGACY_AIR_TOKEN_UNLOCK                  0x55AA6996UL
#define LEGACY_AIR_TOKEN_CALIBRATION             0x43414C30UL
#define LEGACY_AIR_TOKEN_ALIGNMENT               0x414C4947UL
#define LEGACY_AIR_TOKEN_NAV_SUBSCRIBE           0x4E560000UL

#define LEGACY_AIR_CALIBRATION_MODE_MASK_NONE       (1U << 0)
#define LEGACY_AIR_CALIBRATION_MODE_MASK_ONE_FACE   (1U << 1)
#define LEGACY_AIR_CALIBRATION_MODE_MASK_SIX_FACE   (1U << 2)
#define LEGACY_AIR_CALIBRATION_MODE_MASK_ALL         0x07U

#define LEGACY_AIR_SENSOR_SUMMARY_IMU_PRESENT        (1U << 0)
#define LEGACY_AIR_SENSOR_SUMMARY_GNSS_PRESENT       (1U << 1)
#define LEGACY_AIR_SENSOR_SUMMARY_AUX_SENSOR_PRESENT (1U << 2)
#define LEGACY_AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED (1U << 3)
#define LEGACY_AIR_SENSOR_SUMMARY_MASK_ALL             0x0FU

#define LEGACY_AIR_SENSOR_STATUS_REGISTERED          (1U << 0)
#define LEGACY_AIR_SENSOR_STATUS_INITIALIZED         (1U << 1)
#define LEGACY_AIR_SENSOR_STATUS_ONLINE              (1U << 2)
#define LEGACY_AIR_SENSOR_STATUS_HEALTHY             (1U << 3)
#define LEGACY_AIR_SENSOR_STATUS_DATA_VALID          (1U << 4)
#define LEGACY_AIR_SENSOR_STATUS_CALIBRATION_OK      (1U << 5)
#define LEGACY_AIR_SENSOR_STATUS_ALIGNMENT_USED     (1U << 6)
#define LEGACY_AIR_SENSOR_STATUS_REQUIRED_FOR_START (1U << 7)

#define LEGACY_AIR_PREFLIGHT_FLAG_SYSTEM_READY       (1U << 0)
#define LEGACY_AIR_PREFLIGHT_FLAG_START_UNLOCKED     (1U << 1)
#define LEGACY_AIR_PREFLIGHT_FLAG_SELFTEST_PASSED    (1U << 2)
#define LEGACY_AIR_PREFLIGHT_FLAG_GNSS_USABLE        (1U << 3)
#define LEGACY_AIR_PREFLIGHT_FLAG_CAPABILITY_ACKED   (1U << 4)
#define LEGACY_AIR_PREFLIGHT_FLAG_CALIBRATION_READY  (1U << 5)
#define LEGACY_AIR_PREFLIGHT_FLAG_ALIGNMENT_READY    (1U << 6)
#define LEGACY_AIR_PREFLIGHT_FLAG_MASK_ALL            0x7FU

typedef enum
{
    LEGACY_AIR_PROFILE_COMPACT_V0 = 0U
} LegacyAirProfileId;

#define LEGACY_AIR_PROFILE_ID_CURRENT ((uint8_t)LEGACY_AIR_PROFILE_COMPACT_V0)

typedef enum
{
    LEGACY_AIR_TYPE_FLIGHT_STATE   = 0x10U,
    LEGACY_AIR_TYPE_PREFLIGHT_STATE = 0x11U,
    LEGACY_AIR_TYPE_CAPABILITY     = 0x12U,
    LEGACY_AIR_TYPE_PREFLIGHT_STATUS = 0x13U,
    LEGACY_AIR_TYPE_SENSOR_STATUS  = 0x14U,
    LEGACY_AIR_TYPE_NAV_CAPABILITY = 0x15U,
    LEGACY_AIR_TYPE_NAV_PREPARATION = 0x16U,
    LEGACY_AIR_TYPE_NAV_HEALTH = 0x17U,
    LEGACY_AIR_TYPE_STATUS         = 0x20U,
    LEGACY_AIR_TYPE_CMD            = 0x30U,
    LEGACY_AIR_TYPE_ACK            = 0x40U
} LegacyAirType;

typedef enum
{
    LEGACY_AIR_COMMAND_POLICY_PREFLIGHT_ONLY = 1U,
    LEGACY_AIR_COMMAND_POLICY_MISSION_ALLOWED = 2U
} LegacyAirCommandPolicy;

typedef enum
{
    LEGACY_AIR_LIFECYCLE_BOOT = 0U,
    LEGACY_AIR_LIFECYCLE_SELF_TEST,
    LEGACY_AIR_LIFECYCLE_PREFLIGHT,
    LEGACY_AIR_LIFECYCLE_READY,
    LEGACY_AIR_LIFECYCLE_FLIGHT,
    LEGACY_AIR_LIFECYCLE_RECOVERY,
    LEGACY_AIR_LIFECYCLE_LANDED,
    LEGACY_AIR_LIFECYCLE_POSTFLIGHT,
    LEGACY_AIR_LIFECYCLE_FAULT
} LegacyAirLifecycleState;

typedef enum
{
    LEGACY_AIR_STATUS_BOOT              = 0x01U,
    LEGACY_AIR_STATUS_SELFTEST_COMPLETE = 0x02U,
    LEGACY_AIR_STATUS_MISSION_START     = 0x03U,
    LEGACY_AIR_STATUS_LAUNCH            = 0x04U,
    LEGACY_AIR_STATUS_PARACHUTE_DEPLOY  = 0x05U,
    LEGACY_AIR_STATUS_LANDING           = 0x06U,
    LEGACY_AIR_STATUS_LOCKED            = 0x07U,
    LEGACY_AIR_STATUS_UNLOCKED          = 0x08U,
    LEGACY_AIR_STATUS_GNSS_POSITION     = 0x09U,
    LEGACY_AIR_STATUS_ALIGNMENT         = 0x0AU,
    LEGACY_AIR_STATUS_CALIBRATION       = 0x0BU,
    LEGACY_AIR_STATUS_CALIBRATION_FACE  = 0x0CU,
    LEGACY_AIR_STATUS_CALIBRATION_DIAGNOSTIC = 0x0DU
} LegacyAirStatusId;

typedef enum
{
    LEGACY_AIR_ALIGNMENT_STATE_IDLE = 0U,
    LEGACY_AIR_ALIGNMENT_STATE_COLLECTING,
    LEGACY_AIR_ALIGNMENT_STATE_CHECKING,
    LEGACY_AIR_ALIGNMENT_STATE_READY,
    LEGACY_AIR_ALIGNMENT_STATE_FAILED,
    LEGACY_AIR_ALIGNMENT_STATE_STALE
} LegacyAirAlignmentState;

typedef enum
{
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_NONE = 0U,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_NO_STREAM,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_ACCEL_MAGNITUDE,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_GRAVITY_DIRECTION,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_VARIANCE,
    LEGACY_AIR_CALIBRATION_DIAGNOSTIC_SAMPLE_GAP
} LegacyAirCalibrationDiagnosticReason;

typedef enum
{
    LEGACY_AIR_SENSOR_DETAIL_NONE = 0x00U,
    LEGACY_AIR_SENSOR_DETAIL_NOT_REGISTERED = 0x01U,
    LEGACY_AIR_SENSOR_DETAIL_INIT_FAILED = 0x02U,
    LEGACY_AIR_SENSOR_DETAIL_OFFLINE = 0x03U,
    LEGACY_AIR_SENSOR_DETAIL_UNHEALTHY = 0x04U,
    LEGACY_AIR_SENSOR_DETAIL_NO_VALID_DATA = 0x05U,
    LEGACY_AIR_SENSOR_DETAIL_CALIBRATION_REQUIRED = 0x06U,
    LEGACY_AIR_SENSOR_DETAIL_ALIGNMENT_INPUT_INVALID = 0x07U,
    LEGACY_AIR_SENSOR_DETAIL_IO_ERROR = 0x08U,
    LEGACY_AIR_SENSOR_DETAIL_CONFIG_ERROR = 0x09U,
    LEGACY_AIR_SENSOR_DETAIL_UNSUPPORTED = 0x0AU,
    LEGACY_AIR_SENSOR_DETAIL_OTHER = 0xFFU
} LegacyAirSensorDetailCode;

typedef enum
{
    LEGACY_AIR_CALIBRATION_STATE_IDLE = 0U,
    LEGACY_AIR_CALIBRATION_STATE_WAIT_FACE,
    LEGACY_AIR_CALIBRATION_STATE_COLLECTING,
    LEGACY_AIR_CALIBRATION_STATE_CHECKING,
    LEGACY_AIR_CALIBRATION_STATE_READY,
    LEGACY_AIR_CALIBRATION_STATE_FAILED
} LegacyAirCalibrationState;

typedef enum
{
    LEGACY_AIR_CALIBRATION_MODE_NONE = 0U,
    LEGACY_AIR_CALIBRATION_MODE_ONE_FACE,
    LEGACY_AIR_CALIBRATION_MODE_SIX_FACE,
    LEGACY_AIR_CALIBRATION_MODE_NOT_SELECTED = 0xFFU
} LegacyAirCalibrationMode;

typedef enum
{
    LEGACY_AIR_CALIBRATION_FACE_X_POSITIVE = 0U,
    LEGACY_AIR_CALIBRATION_FACE_X_NEGATIVE,
    LEGACY_AIR_CALIBRATION_FACE_Y_POSITIVE,
    LEGACY_AIR_CALIBRATION_FACE_Y_NEGATIVE,
    LEGACY_AIR_CALIBRATION_FACE_Z_POSITIVE,
    LEGACY_AIR_CALIBRATION_FACE_Z_NEGATIVE,
    LEGACY_AIR_CALIBRATION_FACE_NOT_SELECTED = 0xFFU
} LegacyAirCalibrationFace;

typedef enum
{
    LEGACY_AIR_CALIBRATION_FACE_FAILED = 0U,
    LEGACY_AIR_CALIBRATION_FACE_PASSED = 1U
} LegacyAirCalibrationFaceResult;

typedef enum
{
    LEGACY_AIR_CMD_START_MISSION      = 0x01U,
    LEGACY_AIR_CMD_PING               = 0x02U,
    LEGACY_AIR_CMD_LOCK               = 0x03U,
    LEGACY_AIR_CMD_UNLOCK             = 0x04U,
    LEGACY_AIR_CMD_CAPABILITY_ACK     = 0x05U,
    LEGACY_AIR_CMD_CAL_START          = 0x07U,
    LEGACY_AIR_CMD_CAL_FACE           = 0x08U,
    LEGACY_AIR_CMD_CAL_STOP           = 0x09U,
    LEGACY_AIR_CMD_CAL_RESET          = 0x0AU,
    LEGACY_AIR_CMD_ALIGN_START        = 0x0BU,
    LEGACY_AIR_CMD_ALIGN_STOP         = 0x0CU,
    LEGACY_AIR_CMD_ALIGN_RESET        = 0x0DU,
    LEGACY_AIR_CMD_NAV_SUBSCRIBE      = 0x0EU
} LegacyAirCmdId;

typedef enum
{
    LEGACY_AIR_ACK_RESULT_OK                   = 0x00U,
    LEGACY_AIR_ACK_RESULT_BAD_LEN              = 0x01U,
    LEGACY_AIR_ACK_RESULT_BAD_CMD              = 0x02U,
    LEGACY_AIR_ACK_RESULT_BAD_TOKEN            = 0x03U,
    LEGACY_AIR_ACK_RESULT_BUSY                 = 0x04U,
    LEGACY_AIR_ACK_RESULT_REJECTED             = 0x05U,
    LEGACY_AIR_ACK_RESULT_BAD_STATE            = 0x06U,
    LEGACY_AIR_ACK_RESULT_LOCKED_REQUIRED      = 0x07U,
    LEGACY_AIR_ACK_RESULT_ALREADY_LOCKED       = 0x08U,
    LEGACY_AIR_ACK_RESULT_ALREADY_UNLOCKED     = 0x09U,
    LEGACY_AIR_ACK_RESULT_CAPABILITY_REQUIRED  = 0x0AU,
    LEGACY_AIR_ACK_RESULT_CALIBRATION_REQUIRED = 0x0BU,
    LEGACY_AIR_ACK_RESULT_ALIGNMENT_REQUIRED   = 0x0CU,
    LEGACY_AIR_ACK_RESULT_SYSTEM_NOT_READY     = 0x0DU,
    LEGACY_AIR_ACK_RESULT_ATTITUDE_NOT_READY   = 0x0EU,
    LEGACY_AIR_ACK_RESULT_ATTITUDE_INVALID     = 0x0FU,
    LEGACY_AIR_ACK_RESULT_ATTITUDE_STALE       = 0x10U,
    LEGACY_AIR_ACK_RESULT_ORIGIN_FAILED        = 0x11U,
    LEGACY_AIR_ACK_RESULT_NAVIGATION_FAILED    = 0x12U,
    LEGACY_AIR_ACK_RESULT_QUEUE_FAILED         = 0x13U,
    LEGACY_AIR_ACK_RESULT_BAD_PARAM            = 0x14U,
    LEGACY_AIR_ACK_RESULT_HOOKS_UNAVAILABLE    = 0x15U,
    LEGACY_AIR_ACK_RESULT_PREPARE_FAILED       = 0x16U
} LegacyAirAckResult;

typedef enum
{
    LEGACY_AIR_BUILD_OK = 0U,
    LEGACY_AIR_BUILD_BAD_PARAM,
    LEGACY_AIR_BUILD_BAD_LEN,
    LEGACY_AIR_BUILD_BAD_TYPE
} LegacyAirBuildResult;

typedef enum
{
    LEGACY_AIR_PARSE_OK = 0U,
    LEGACY_AIR_PARSE_BAD_PARAM,
    LEGACY_AIR_PARSE_BAD_LEN,
    LEGACY_AIR_PARSE_BAD_TYPE,
    LEGACY_AIR_PARSE_BAD_ID,
    LEGACY_AIR_PARSE_BAD_TOKEN,
    LEGACY_AIR_PARSE_BAD_FIELD
} LegacyAirParseResult;

typedef struct
{
    uint8_t air_profile_id;
    uint8_t command_policy;
    uint8_t calibration_mode_mask;
    uint8_t sensor_summary_flags;
    uint8_t accel_full_scale_g;
    uint16_t gyro_full_scale_dps;
} LegacyAirCapabilityPayload;

typedef struct
{
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    uint32_t saturation_count;
} LegacyAirCompactV0ImuQuantized;

typedef struct
{
    uint8_t lifecycle_state;
    uint8_t calibration_state;
    uint8_t calibration_mode;
    uint8_t completed_face_mask;
    uint8_t current_face;
    uint8_t alignment_state;
    uint8_t flags;
    uint8_t start_block_reason;
} LegacyAirPreflightStatusPayload;

typedef struct
{
    uint8_t snapshot_id;
    uint8_t sensor_id;
    uint8_t instance_id;
    uint8_t status_flags;
    uint8_t detail_code;
    uint8_t index;
    uint8_t total;
} LegacyAirSensorStatusPayload;

/* Atomic schema-1 status: session/generation common; type owns all tail bytes. */
typedef struct
{
    uint16_t session;
    uint16_t generation;
    uint8_t tail[3];
} LegacyAirNavigationStatusPayload;

LegacyAirBuildResult LegacyAir_NavigationStatusBuild(uint8_t seq, uint8_t air_type,
    const LegacyAirNavigationStatusPayload *status, uint8_t *out_frame,
    uint8_t out_size, uint8_t *out_len);

typedef struct
{
    uint32_t time_ms;
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    int16_t quaternion_q15[4];
} LegacyAirPreflightStatePayload;

typedef struct
{
    uint32_t time_ms;
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    int16_t quaternion_q15[4];
    float velocity_enu_mps[3];
    float position_enu_m[3];
} LegacyAirFlightStatePayload;

typedef struct
{
    uint8_t seq;
    uint8_t cmd_id;
    uint32_t token;
    uint8_t param0;
    uint8_t param1;
} LegacyAirCmdPayload;

uint8_t LegacyAir_GetExpectedFrameLength(uint8_t air_type);
LegacyAirParseResult LegacyAir_FrameValidate(const uint8_t *frame, uint8_t frame_len);

LegacyAirBuildResult LegacyAir_CapabilityBuild(uint8_t seq,
                                   const LegacyAirCapabilityPayload *capability,
                                   uint8_t *out_frame,
                                   uint8_t out_size,
                                   uint8_t *out_len);
LegacyAirParseResult LegacyAir_CapabilityParse(const uint8_t *frame,
                                   uint8_t frame_len,
                                   LegacyAirCapabilityPayload *capability);

LegacyAirBuildResult LegacyAir_CompactV0ImuQuantize(
    const float accel_b_mps2[3],
    const float gyro_b_radps[3],
    LegacyAirCompactV0ImuQuantized *quantized);

LegacyAirBuildResult LegacyAir_PreflightStatusBuild(
    uint8_t seq,
    const LegacyAirPreflightStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);
LegacyAirParseResult LegacyAir_PreflightStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    LegacyAirPreflightStatusPayload *status);

LegacyAirBuildResult LegacyAir_SensorStatusBuild(
    uint8_t seq,
    const LegacyAirSensorStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);
LegacyAirParseResult LegacyAir_SensorStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    LegacyAirSensorStatusPayload *status);

LegacyAirBuildResult LegacyAir_PreflightStateBuild(
    uint8_t seq,
    const LegacyAirPreflightStatePayload *state,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);

LegacyAirBuildResult LegacyAir_FlightStateBuild(uint8_t seq,
                                    const LegacyAirFlightStatePayload *state,
                                    uint8_t *out_frame,
                                    uint8_t out_size,
                                    uint8_t *out_len);

LegacyAirBuildResult LegacyAir_StatusBuild(uint8_t seq,
                               uint8_t status_id,
                               uint32_t time_ms,
                               uint8_t arg0,
                               uint8_t arg1,
                               uint8_t *out_frame,
                               uint8_t out_size,
                               uint8_t *out_len);

LegacyAirBuildResult LegacyAir_AckBuild(uint8_t seq,
                            uint8_t ack_seq,
                            uint8_t ack_cmd_id,
                            uint8_t result,
                            uint32_t time_ms,
                            uint8_t *out_frame,
                            uint8_t out_size,
                            uint8_t *out_len);

LegacyAirParseResult LegacyAir_CmdParse(const uint8_t *frame, uint8_t frame_len,
                            LegacyAirCmdPayload *cmd);
uint8_t LegacyAir_CmdTokenIsValid(uint8_t cmd_id, uint32_t token);
uint8_t LegacyAir_CmdIdIsValid(uint8_t cmd_id);
uint8_t LegacyAir_StatusIdIsValid(uint8_t status_id);
uint8_t LegacyAir_AckResultIsValid(uint8_t result);

#endif /* __SS_TM_LEGACY_H */
