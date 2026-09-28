#ifndef __AIR_PROTOCOL_H
#define __AIR_PROTOCOL_H

#include <stdint.h>

#include "silverstar_sensor_id.h"

#define AIR_PROTOCOL_COMPATIBILITY_TAG     "AIR-NCRC"
#define AIR_PROTOCOL_APPLICATION_CRC_SIZE  0U

#define AIR_STANDARD_GRAVITY_MPS2          9.80665f
#define AIR_ACCEL_FULL_SCALE_G             16U
#define AIR_GYRO_FULL_SCALE_DPS            2000U

#define AIR_MAX_FRAME_LEN                 50U
#define AIR_FLIGHT_STATE_LEN              50U
#define AIR_PREFLIGHT_STATE_LEN           26U
#define AIR_CAPABILITY_LEN                 9U
#define AIR_PREFLIGHT_STATUS_LEN            9U
#define AIR_SENSOR_STATUS_LEN               9U
#define AIR_NAV_CAPABILITY_LEN              9U
#define AIR_NAV_PREPARATION_LEN             9U
#define AIR_NAV_HEALTH_LEN                  9U
#define AIR_NAV_SCHEMA_VERSION             1U
#define AIR_NAV_PREPARATION_MASK            0x7FU
#define AIR_NAV_GROUP_MASK                  0x1FU
#define AIR_STATUS_LEN                     9U
#define AIR_CMD_LEN                        9U
#define AIR_ACK_LEN                        9U

#define AIR_TOKEN_START_MISSION           0xA55A3CC3UL
#define AIR_TOKEN_LOCK                    0xC33CA55AUL
#define AIR_TOKEN_UNLOCK                  0x55AA6996UL
#define AIR_TOKEN_CALIBRATION             0x43414C30UL
#define AIR_TOKEN_ALIGNMENT               0x414C4947UL
#define AIR_TOKEN_NAV_SUBSCRIBE           0x4E560000UL

#define AIR_CALIBRATION_MODE_MASK_NONE       (1U << 0)
#define AIR_CALIBRATION_MODE_MASK_ONE_FACE   (1U << 1)
#define AIR_CALIBRATION_MODE_MASK_SIX_FACE   (1U << 2)
#define AIR_CALIBRATION_MODE_MASK_ALL         0x07U

#define AIR_SENSOR_SUMMARY_IMU_PRESENT        (1U << 0)
#define AIR_SENSOR_SUMMARY_GNSS_PRESENT       (1U << 1)
#define AIR_SENSOR_SUMMARY_AUX_SENSOR_PRESENT (1U << 2)
#define AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED (1U << 3)
#define AIR_SENSOR_SUMMARY_MASK_ALL             0x0FU

#define AIR_SENSOR_STATUS_REGISTERED          (1U << 0)
#define AIR_SENSOR_STATUS_INITIALIZED         (1U << 1)
#define AIR_SENSOR_STATUS_ONLINE              (1U << 2)
#define AIR_SENSOR_STATUS_HEALTHY             (1U << 3)
#define AIR_SENSOR_STATUS_DATA_VALID          (1U << 4)
#define AIR_SENSOR_STATUS_CALIBRATION_OK      (1U << 5)
#define AIR_SENSOR_STATUS_ALIGNMENT_USED     (1U << 6)
#define AIR_SENSOR_STATUS_REQUIRED_FOR_START (1U << 7)

#define AIR_PREFLIGHT_FLAG_SYSTEM_READY       (1U << 0)
#define AIR_PREFLIGHT_FLAG_START_UNLOCKED     (1U << 1)
#define AIR_PREFLIGHT_FLAG_SELFTEST_PASSED    (1U << 2)
#define AIR_PREFLIGHT_FLAG_GNSS_USABLE        (1U << 3)
#define AIR_PREFLIGHT_FLAG_CAPABILITY_ACKED   (1U << 4)
#define AIR_PREFLIGHT_FLAG_CALIBRATION_READY  (1U << 5)
#define AIR_PREFLIGHT_FLAG_ALIGNMENT_READY    (1U << 6)
#define AIR_PREFLIGHT_FLAG_MASK_ALL            0x7FU

typedef enum
{
    AIR_PROFILE_COMPACT_V0 = 0U
} AirProfileId;

#define AIR_PROFILE_ID_CURRENT ((uint8_t)AIR_PROFILE_COMPACT_V0)

typedef enum
{
    AIR_TYPE_FLIGHT_STATE   = 0x10U,
    AIR_TYPE_PREFLIGHT_STATE = 0x11U,
    AIR_TYPE_CAPABILITY     = 0x12U,
    AIR_TYPE_PREFLIGHT_STATUS = 0x13U,
    AIR_TYPE_SENSOR_STATUS  = 0x14U,
    AIR_TYPE_NAV_CAPABILITY = 0x15U,
    AIR_TYPE_NAV_PREPARATION = 0x16U,
    AIR_TYPE_NAV_HEALTH = 0x17U,
    AIR_TYPE_STATUS         = 0x20U,
    AIR_TYPE_CMD            = 0x30U,
    AIR_TYPE_ACK            = 0x40U
} AirType;

typedef enum
{
    AIR_COMMAND_POLICY_PREFLIGHT_ONLY = 1U,
    AIR_COMMAND_POLICY_MISSION_ALLOWED = 2U
} AirCommandPolicy;

typedef enum
{
    AIR_LIFECYCLE_BOOT = 0U,
    AIR_LIFECYCLE_SELF_TEST,
    AIR_LIFECYCLE_PREFLIGHT,
    AIR_LIFECYCLE_READY,
    AIR_LIFECYCLE_FLIGHT,
    AIR_LIFECYCLE_RECOVERY,
    AIR_LIFECYCLE_LANDED,
    AIR_LIFECYCLE_POSTFLIGHT,
    AIR_LIFECYCLE_FAULT
} AirLifecycleState;

typedef enum
{
    AIR_STATUS_BOOT              = 0x01U,
    AIR_STATUS_SELFTEST_COMPLETE = 0x02U,
    AIR_STATUS_MISSION_START     = 0x03U,
    AIR_STATUS_LAUNCH            = 0x04U,
    AIR_STATUS_PARACHUTE_DEPLOY  = 0x05U,
    AIR_STATUS_LANDING           = 0x06U,
    AIR_STATUS_LOCKED            = 0x07U,
    AIR_STATUS_UNLOCKED          = 0x08U,
    AIR_STATUS_GNSS_POSITION     = 0x09U,
    AIR_STATUS_ALIGNMENT         = 0x0AU,
    AIR_STATUS_CALIBRATION       = 0x0BU,
    AIR_STATUS_CALIBRATION_FACE  = 0x0CU,
    AIR_STATUS_CALIBRATION_DIAGNOSTIC = 0x0DU
} AirStatusId;

typedef enum
{
    AIR_ALIGNMENT_STATE_IDLE = 0U,
    AIR_ALIGNMENT_STATE_COLLECTING,
    AIR_ALIGNMENT_STATE_CHECKING,
    AIR_ALIGNMENT_STATE_READY,
    AIR_ALIGNMENT_STATE_FAILED,
    AIR_ALIGNMENT_STATE_STALE
} AirAlignmentState;

typedef enum
{
    AIR_CALIBRATION_DIAGNOSTIC_NONE = 0U,
    AIR_CALIBRATION_DIAGNOSTIC_NO_STREAM,
    AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING,
    AIR_CALIBRATION_DIAGNOSTIC_ACCEL_MAGNITUDE,
    AIR_CALIBRATION_DIAGNOSTIC_GRAVITY_DIRECTION,
    AIR_CALIBRATION_DIAGNOSTIC_VARIANCE,
    AIR_CALIBRATION_DIAGNOSTIC_SAMPLE_GAP
} AirCalibrationDiagnosticReason;

typedef enum
{
    AIR_SENSOR_DETAIL_NONE = 0x00U,
    AIR_SENSOR_DETAIL_NOT_REGISTERED = 0x01U,
    AIR_SENSOR_DETAIL_INIT_FAILED = 0x02U,
    AIR_SENSOR_DETAIL_OFFLINE = 0x03U,
    AIR_SENSOR_DETAIL_UNHEALTHY = 0x04U,
    AIR_SENSOR_DETAIL_NO_VALID_DATA = 0x05U,
    AIR_SENSOR_DETAIL_CALIBRATION_REQUIRED = 0x06U,
    AIR_SENSOR_DETAIL_ALIGNMENT_INPUT_INVALID = 0x07U,
    AIR_SENSOR_DETAIL_IO_ERROR = 0x08U,
    AIR_SENSOR_DETAIL_CONFIG_ERROR = 0x09U,
    AIR_SENSOR_DETAIL_UNSUPPORTED = 0x0AU,
    AIR_SENSOR_DETAIL_OTHER = 0xFFU
} AirSensorDetailCode;

typedef enum
{
    AIR_CALIBRATION_STATE_IDLE = 0U,
    AIR_CALIBRATION_STATE_WAIT_FACE,
    AIR_CALIBRATION_STATE_COLLECTING,
    AIR_CALIBRATION_STATE_CHECKING,
    AIR_CALIBRATION_STATE_READY,
    AIR_CALIBRATION_STATE_FAILED
} AirCalibrationState;

typedef enum
{
    AIR_CALIBRATION_MODE_NONE = 0U,
    AIR_CALIBRATION_MODE_ONE_FACE,
    AIR_CALIBRATION_MODE_SIX_FACE,
    AIR_CALIBRATION_MODE_NOT_SELECTED = 0xFFU
} AirCalibrationMode;

typedef enum
{
    AIR_CALIBRATION_FACE_X_POSITIVE = 0U,
    AIR_CALIBRATION_FACE_X_NEGATIVE,
    AIR_CALIBRATION_FACE_Y_POSITIVE,
    AIR_CALIBRATION_FACE_Y_NEGATIVE,
    AIR_CALIBRATION_FACE_Z_POSITIVE,
    AIR_CALIBRATION_FACE_Z_NEGATIVE,
    AIR_CALIBRATION_FACE_NOT_SELECTED = 0xFFU
} AirCalibrationFace;

typedef enum
{
    AIR_CALIBRATION_FACE_FAILED = 0U,
    AIR_CALIBRATION_FACE_PASSED = 1U
} AirCalibrationFaceResult;

typedef enum
{
    AIR_CMD_START_MISSION      = 0x01U,
    AIR_CMD_PING               = 0x02U,
    AIR_CMD_LOCK               = 0x03U,
    AIR_CMD_UNLOCK             = 0x04U,
    AIR_CMD_CAPABILITY_ACK     = 0x05U,
    AIR_CMD_CAL_START          = 0x07U,
    AIR_CMD_CAL_FACE           = 0x08U,
    AIR_CMD_CAL_STOP           = 0x09U,
    AIR_CMD_CAL_RESET          = 0x0AU,
    AIR_CMD_ALIGN_START        = 0x0BU,
    AIR_CMD_ALIGN_STOP         = 0x0CU,
    AIR_CMD_ALIGN_RESET        = 0x0DU,
    AIR_CMD_NAV_SUBSCRIBE      = 0x0EU
} AirCmdId;

typedef enum
{
    AIR_ACK_RESULT_OK                   = 0x00U,
    AIR_ACK_RESULT_BAD_LEN              = 0x01U,
    AIR_ACK_RESULT_BAD_CMD              = 0x02U,
    AIR_ACK_RESULT_BAD_TOKEN            = 0x03U,
    AIR_ACK_RESULT_BUSY                 = 0x04U,
    AIR_ACK_RESULT_REJECTED             = 0x05U,
    AIR_ACK_RESULT_BAD_STATE            = 0x06U,
    AIR_ACK_RESULT_LOCKED_REQUIRED      = 0x07U,
    AIR_ACK_RESULT_ALREADY_LOCKED       = 0x08U,
    AIR_ACK_RESULT_ALREADY_UNLOCKED     = 0x09U,
    AIR_ACK_RESULT_CAPABILITY_REQUIRED  = 0x0AU,
    AIR_ACK_RESULT_CALIBRATION_REQUIRED = 0x0BU,
    AIR_ACK_RESULT_ALIGNMENT_REQUIRED   = 0x0CU,
    AIR_ACK_RESULT_SYSTEM_NOT_READY     = 0x0DU,
    AIR_ACK_RESULT_ATTITUDE_NOT_READY   = 0x0EU,
    AIR_ACK_RESULT_ATTITUDE_INVALID     = 0x0FU,
    AIR_ACK_RESULT_ATTITUDE_STALE       = 0x10U,
    AIR_ACK_RESULT_ORIGIN_FAILED        = 0x11U,
    AIR_ACK_RESULT_NAVIGATION_FAILED    = 0x12U,
    AIR_ACK_RESULT_QUEUE_FAILED         = 0x13U,
    AIR_ACK_RESULT_BAD_PARAM            = 0x14U,
    AIR_ACK_RESULT_HOOKS_UNAVAILABLE    = 0x15U,
    AIR_ACK_RESULT_PREPARE_FAILED       = 0x16U
} AirAckResult;

typedef enum
{
    AIR_BUILD_OK = 0U,
    AIR_BUILD_BAD_PARAM,
    AIR_BUILD_BAD_LEN,
    AIR_BUILD_BAD_TYPE
} AirBuildResult;

typedef enum
{
    AIR_PARSE_OK = 0U,
    AIR_PARSE_BAD_PARAM,
    AIR_PARSE_BAD_LEN,
    AIR_PARSE_BAD_TYPE,
    AIR_PARSE_BAD_ID,
    AIR_PARSE_BAD_TOKEN,
    AIR_PARSE_BAD_FIELD
} AirParseResult;

typedef struct
{
    uint8_t air_profile_id;
    uint8_t command_policy;
    uint8_t calibration_mode_mask;
    uint8_t sensor_summary_flags;
    uint8_t accel_full_scale_g;
    uint16_t gyro_full_scale_dps;
} AirCapabilityPayload;

typedef struct
{
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    uint32_t saturation_count;
} AirCompactV0ImuQuantized;

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
} AirPreflightStatusPayload;

typedef struct
{
    uint8_t snapshot_id;
    uint8_t sensor_id;
    uint8_t instance_id;
    uint8_t status_flags;
    uint8_t detail_code;
    uint8_t index;
    uint8_t total;
} AirSensorStatusPayload;

/* Atomic schema-1 status: session/generation common; type owns all tail bytes. */
typedef struct
{
    uint16_t session;
    uint16_t generation;
    uint8_t tail[3];
} AirNavigationStatusPayload;

AirBuildResult Air_NavigationStatusBuild(uint8_t seq, uint8_t air_type,
    const AirNavigationStatusPayload *status, uint8_t *out_frame,
    uint8_t out_size, uint8_t *out_len);

typedef struct
{
    uint32_t time_ms;
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    int16_t quaternion_q15[4];
} AirPreflightStatePayload;

typedef struct
{
    uint32_t time_ms;
    int16_t accel_i16[3];
    int16_t gyro_i16[3];
    int16_t quaternion_q15[4];
    float velocity_enu_mps[3];
    float position_enu_m[3];
} AirFlightStatePayload;

typedef struct
{
    uint8_t seq;
    uint8_t cmd_id;
    uint32_t token;
    uint8_t param0;
    uint8_t param1;
} AirCmdPayload;

uint8_t Air_GetExpectedFrameLength(uint8_t air_type);
AirParseResult Air_FrameValidate(const uint8_t *frame, uint8_t frame_len);

AirBuildResult Air_CapabilityBuild(uint8_t seq,
                                   const AirCapabilityPayload *capability,
                                   uint8_t *out_frame,
                                   uint8_t out_size,
                                   uint8_t *out_len);
AirParseResult Air_CapabilityParse(const uint8_t *frame,
                                   uint8_t frame_len,
                                   AirCapabilityPayload *capability);

AirBuildResult Air_CompactV0ImuQuantize(
    const float accel_b_mps2[3],
    const float gyro_b_radps[3],
    AirCompactV0ImuQuantized *quantized);

AirBuildResult Air_PreflightStatusBuild(
    uint8_t seq,
    const AirPreflightStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);
AirParseResult Air_PreflightStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    AirPreflightStatusPayload *status);

AirBuildResult Air_SensorStatusBuild(
    uint8_t seq,
    const AirSensorStatusPayload *status,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);
AirParseResult Air_SensorStatusParse(
    const uint8_t *frame,
    uint8_t frame_len,
    AirSensorStatusPayload *status);

AirBuildResult Air_PreflightStateBuild(
    uint8_t seq,
    const AirPreflightStatePayload *state,
    uint8_t *out_frame,
    uint8_t out_size,
    uint8_t *out_len);

AirBuildResult Air_FlightStateBuild(uint8_t seq,
                                    const AirFlightStatePayload *state,
                                    uint8_t *out_frame,
                                    uint8_t out_size,
                                    uint8_t *out_len);

AirBuildResult Air_StatusBuild(uint8_t seq,
                               uint8_t status_id,
                               uint32_t time_ms,
                               uint8_t arg0,
                               uint8_t arg1,
                               uint8_t *out_frame,
                               uint8_t out_size,
                               uint8_t *out_len);

AirBuildResult Air_AckBuild(uint8_t seq,
                            uint8_t ack_seq,
                            uint8_t ack_cmd_id,
                            uint8_t result,
                            uint32_t time_ms,
                            uint8_t *out_frame,
                            uint8_t out_size,
                            uint8_t *out_len);

AirParseResult Air_CmdParse(const uint8_t *frame, uint8_t frame_len,
                            AirCmdPayload *cmd);
uint8_t Air_CmdTokenIsValid(uint8_t cmd_id, uint32_t token);
uint8_t Air_CmdIdIsValid(uint8_t cmd_id);
uint8_t Air_StatusIdIsValid(uint8_t status_id);
uint8_t Air_AckResultIsValid(uint8_t result);

#endif /* __AIR_PROTOCOL_H */
