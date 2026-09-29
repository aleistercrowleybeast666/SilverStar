#ifndef __SYSTEM_GNSS_IF_H
#define __SYSTEM_GNSS_IF_H

#include "system_device_types.h"

#define SYSTEM_GNSS_VEL_VALID_E (1U << 0)
#define SYSTEM_GNSS_VEL_VALID_N (1U << 1)
#define SYSTEM_GNSS_VEL_VALID_U (1U << 2)

#define SYSTEM_GNSS_FIELD_FIX_TYPE            (1UL << 0)
#define SYSTEM_GNSS_FIELD_FIX_OK              (1UL << 1)
#define SYSTEM_GNSS_FIELD_SATELLITE_COUNT     (1UL << 2)
#define SYSTEM_GNSS_FIELD_POSITION            (1UL << 3)
#define SYSTEM_GNSS_FIELD_HEIGHT              (1UL << 4)
#define SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY (1UL << 5)
#define SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY   (1UL << 6)
#define SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL (1UL << 7)
#define SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL   (1UL << 8)
#define SYSTEM_GNSS_FIELD_SPEED_ACCURACY      (1UL << 9)

#define SYSTEM_GNSS_REJECT_OFFLINE           (1UL << 0)
#define SYSTEM_GNSS_REJECT_NO_FIX            (1UL << 1)
#define SYSTEM_GNSS_REJECT_FIX_FLAG          (1UL << 2)
#define SYSTEM_GNSS_REJECT_FIX_TYPE          (1UL << 3)
#define SYSTEM_GNSS_REJECT_SATELLITES         (1UL << 4)
#define SYSTEM_GNSS_REJECT_HACC               (1UL << 5)
#define SYSTEM_GNSS_REJECT_VACC               (1UL << 6)
#define SYSTEM_GNSS_REJECT_SACC               (1UL << 7)
#define SYSTEM_GNSS_REJECT_STALE              (1UL << 8)
#define SYSTEM_GNSS_REJECT_FIELD_INVALID      (1UL << 9)
#define SYSTEM_GNSS_REJECT_FIELD_UNSUPPORTED  (1UL << 10)

#define SYSTEM_GNSS_CAP_POSITION          (1UL << 0)
#define SYSTEM_GNSS_CAP_VELOCITY_2D       (1UL << 1)
#define SYSTEM_GNSS_CAP_VELOCITY_3D       (1UL << 2)
#define SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT  (1UL << 3)
#define SYSTEM_GNSS_CAP_MSL_HEIGHT        (1UL << 4)
#define SYSTEM_GNSS_CAP_TIME              (1UL << 5)
#define SYSTEM_GNSS_CAP_ACCURACY_FIELDS   (1UL << 6)
#define SYSTEM_GNSS_CAP_CONFIG_NAV_RATE   (1UL << 7)
#define SYSTEM_GNSS_CAP_DYNAMIC_MODEL     (1UL << 8)
#define SYSTEM_GNSS_CAP_SATELLITE_DIAGNOSTICS (1UL << 9)
#define SYSTEM_GNSS_CAP_RF_DIAGNOSTICS        (1UL << 10)
#define SYSTEM_GNSS_CAP_READ_ONLY             (1UL << 11)

#define SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS       (1UL << 0)
#define SYSTEM_GNSS_SAT_DIAG_FIELD_CNO          (1UL << 1)
#define SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY      (1UL << 2)

#define SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA       (1UL << 0)
#define SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING       (1UL << 1)
#define SYSTEM_GNSS_RF_DIAG_FIELD_NOISE          (1UL << 2)
#define SYSTEM_GNSS_RF_DIAG_FIELD_AGC            (1UL << 3)

#define SYSTEM_GNSS_CONSTELLATION_GPS      (1UL << 0)
#define SYSTEM_GNSS_CONSTELLATION_BDS      (1UL << 1)
#define SYSTEM_GNSS_CONSTELLATION_GALILEO  (1UL << 2)
#define SYSTEM_GNSS_CONSTELLATION_GLONASS  (1UL << 3)

#define SYSTEM_GNSS_CFG_NAVIGATION_RATE (1UL << 0)
#define SYSTEM_GNSS_CFG_CONSTELLATIONS   (1UL << 1)
#define SYSTEM_GNSS_CFG_DYNAMIC_MODEL    (1UL << 2)
#define SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL  (1UL << 3)
#define SYSTEM_GNSS_CFG_ENABLED_MESSAGES (1UL << 4)

#define SYSTEM_GNSS_HW_CONFIG_VALID_BAUD           (1UL << 0)
#define SYSTEM_GNSS_HW_CONFIG_VALID_RATE           (1UL << 1)
#define SYSTEM_GNSS_HW_CONFIG_VALID_DYNAMIC        (1UL << 2)
#define SYSTEM_GNSS_HW_CONFIG_VALID_CONSTELLATIONS (1UL << 3)
#define SYSTEM_GNSS_HW_CONFIG_VALID_PROTOCOL_IN    (1UL << 4)
#define SYSTEM_GNSS_HW_CONFIG_VALID_PROTOCOL_OUT   (1UL << 5)
#define SYSTEM_GNSS_HW_CONFIG_VALID_NAV_PVT        (1UL << 6)

/* Generic enabled-message mask used by SystemGnssConfig. */
#define SYSTEM_GNSS_MESSAGE_NAV_PVT        (1UL << 0)

typedef enum
{
    SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE = 0,
    SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G,
    SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G
} SystemGnssDynamicModel;

typedef enum
{
    SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX = 0,
    SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA,
    SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA
} SystemGnssOutputProtocol;

typedef enum
{
    SYSTEM_GNSS_QUALITY_POSITION_HORIZONTAL = 0U,
    SYSTEM_GNSS_QUALITY_POSITION_VERTICAL,
    SYSTEM_GNSS_QUALITY_VELOCITY_HORIZONTAL,
    SYSTEM_GNSS_QUALITY_VELOCITY_VERTICAL,
    SYSTEM_GNSS_QUALITY_GROUP_COUNT
} SystemGnssQualityGroup;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    /* sample_timestamp_us is already on MCU monotonic axis when trusted. */
    uint8_t measurement_timestamp_trusted;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t position_reject_mask;
    uint32_t velocity_reject_mask;
    uint32_t group_reject_mask[SYSTEM_GNSS_QUALITY_GROUP_COUNT];
    uint8_t valid_group_mask;
    uint8_t physical_valid_group_mask;
    uint8_t quality_degraded_group_mask;
    int32_t latitude_e7;
    int32_t longitude_e7;
    int32_t ellipsoid_height_mm;
    int32_t msl_height_mm;
    float velocity_enu_mps[3];
    float velocity_variance_m2ps2[3];
    float horizontal_accuracy_m;
    float vertical_accuracy_m;
    float speed_accuracy_mps;
    uint8_t velocity_valid_mask;
    uint8_t fix_type;
    uint8_t fix_ok;
    uint8_t satellite_count;
    uint8_t position_usable;
    uint8_t course_usable;
    uint8_t online;
    uint8_t quality_degraded;
} SystemGnssSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t navigation_rate_hz;
    uint32_t constellation_mask;
    SystemGnssDynamicModel dynamic_model;
    SystemGnssOutputProtocol output_protocol;
    uint32_t enabled_message_mask;
} SystemGnssConfig;

typedef enum
{
    SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK = 0,
    SYSTEM_GNSS_CONFIG_READ_NAK,
    SYSTEM_GNSS_CONFIG_READ_TX_ERROR,
    SYSTEM_GNSS_CONFIG_READ_CHECKSUM_ERROR,
    SYSTEM_GNSS_CONFIG_READ_MALFORMED_RESPONSE,
    SYSTEM_GNSS_CONFIG_READ_TIMEOUT,
    SYSTEM_GNSS_CONFIG_READ_NOT_READY,
    SYSTEM_GNSS_CONFIG_READ_IO_ERROR
} SystemGnssConfigReadResult;

typedef enum
{
    SYSTEM_GNSS_TRANSACTION_DETAIL_NONE = 0,
    SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK,
    SYSTEM_GNSS_TRANSACTION_DETAIL_NAK,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BUSY,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_VERSION,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LAYER,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_POSITION,
    SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LENGTH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_KEY_MISMATCH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_VALUE_LENGTH_MISMATCH,
    SYSTEM_GNSS_TRANSACTION_DETAIL_COUNT_OVERFLOW,
    SYSTEM_GNSS_TRANSACTION_DETAIL_CHECKSUM_ERROR,
    SYSTEM_GNSS_TRANSACTION_DETAIL_TX_ERROR,
    SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT,
    SYSTEM_GNSS_TRANSACTION_DETAIL_NOT_READY,
    SYSTEM_GNSS_TRANSACTION_DETAIL_RX_DISCONTINUITY
} SystemGnssTransactionDetail;

typedef enum
{
    SYSTEM_GNSS_CONFIG_READ_GROUP_NONE = 0,
    SYSTEM_GNSS_CONFIG_READ_GROUP_UART,
    SYSTEM_GNSS_CONFIG_READ_GROUP_PROTOCOL,
    SYSTEM_GNSS_CONFIG_READ_GROUP_NAV_PVT,
    SYSTEM_GNSS_CONFIG_READ_GROUP_RATE,
    SYSTEM_GNSS_CONFIG_READ_GROUP_DYNAMIC_MODEL,
    SYSTEM_GNSS_CONFIG_READ_GROUP_SIGNALS
} SystemGnssConfigReadGroup;

typedef struct
{
    uint32_t valid_mask;
    uint32_t baudrate;
    uint32_t constellation_mask;
    uint32_t elapsed_ms;
    uint16_t navigation_rate_hz;
    SystemGnssDynamicModel dynamic_model;
    SystemGnssOutputProtocol output_protocol;
    uint8_t protocol_in;
    uint8_t nav_pvt_rate;
    uint8_t nav_pvt_known;
    SystemGnssConfigReadResult read_result;
    SystemGnssConfigReadGroup failed_group;
    uint32_t failed_key;
    uint16_t response_length;
    uint8_t nak_class;
    uint8_t nak_id;
    uint32_t transaction_id;
    uint32_t unsupported_mask;
    SystemGnssTransactionDetail detailed_result;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t received_class;
    uint8_t received_id;
    uint8_t response_version;
} SystemGnssHardwareConfig;

typedef enum
{
    SYSTEM_GNSS_CONFIG_STAGE_NONE = 0,
    SYSTEM_GNSS_CONFIG_STAGE_UART,
    SYSTEM_GNSS_CONFIG_STAGE_UART_SETTLE,
    SYSTEM_GNSS_CONFIG_STAGE_PROTOCOL,
    SYSTEM_GNSS_CONFIG_STAGE_NAV_PVT,
    SYSTEM_GNSS_CONFIG_STAGE_RATE,
    SYSTEM_GNSS_CONFIG_STAGE_DYNAMIC_MODEL,
    SYSTEM_GNSS_CONFIG_STAGE_SIGNALS,
    SYSTEM_GNSS_CONFIG_STAGE_PVT_RECOVERY,
    SYSTEM_GNSS_CONFIG_STAGE_VERIFY
} SystemGnssConfigStage;

typedef struct
{
    SystemDeviceResult uart_baudrate_result;
    SystemDeviceResult uart_settle_result;
    SystemDeviceResult protocol_result;
    SystemDeviceResult nav_pvt_result;
    SystemDeviceResult rate_result;
    SystemDeviceResult dynamic_model_result;
    SystemDeviceResult signals_result;
    SystemDeviceResult pvt_recovery_result;
    SystemDeviceResult verify_result;
    SystemGnssConfigStage failed_stage;
    uint32_t baseline_pvt_sequence;
    uint32_t recovered_pvt_sequence;
    uint64_t signal_complete_timestamp_us;
    uint8_t ack_result;
    uint8_t write_layers;
    SystemGnssConfigReadResult verify_read_result;
    SystemGnssConfigReadGroup verify_failed_group;
    uint32_t verify_failed_key;
    uint32_t verify_valid_mask;
    uint16_t verify_response_length;
    uint8_t verify_nak_class;
    uint8_t verify_nak_id;
    SystemGnssTransactionDetail verify_detailed_result;
    uint8_t verify_expected_class;
    uint8_t verify_expected_id;
    uint8_t verify_received_class;
    uint8_t verify_received_id;
    uint8_t verify_response_version;
} SystemGnssConfigTransactionReport;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint8_t satellite_count;
    uint8_t used_count;
    uint8_t average_cno_dbhz;
    uint8_t maximum_cno_dbhz;
    uint8_t average_quality;
    uint8_t fresh;
    SystemGnssConfigReadResult read_result;
    SystemGnssTransactionDetail detailed_result;
    uint32_t transaction_id;
    uint16_t response_length;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t received_class;
    uint8_t received_id;
    uint8_t expected_ck_a;
    uint8_t expected_ck_b;
    uint8_t received_ck_a;
    uint8_t received_ck_b;
} SystemGnssSatelliteDiagnostics;

typedef struct
{
    uint32_t ubx_frame_count;
    uint32_t ubx_checksum_error_count;
    uint32_t nmea_sentence_count;
    uint32_t nmea_checksum_ok_count;
    uint32_t nmea_checksum_error_count;
    uint32_t unknown_byte_count;
    uint32_t parser_resync_count;
} SystemGnssIoDetail;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint16_t noise_per_ms;
    uint16_t agc_count;
    uint8_t rf_block_count;
    uint8_t antenna_status;
    uint8_t antenna_power;
    uint8_t jamming_state;
    uint8_t cw_suppression;
    /* Compatibility alias for cw_suppression; not a jamming-state enum. */
    uint8_t jamming_indicator;
    uint8_t fresh;
    SystemGnssConfigReadResult read_result;
    SystemGnssTransactionDetail detailed_result;
    uint32_t transaction_id;
    uint16_t response_length;
} SystemGnssRfDiagnostics;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t time_of_week_ms;
    int32_t nanosecond;
    uint32_t time_accuracy_ns;
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
    uint8_t date_valid;
    uint8_t time_valid;
    uint8_t fully_resolved;
} SystemGnssTime;

#define SYSTEM_GNSS_NOISE_VALID_HORIZONTAL_POSITION_STD_FLOOR (1UL << 0)
#define SYSTEM_GNSS_NOISE_VALID_VERTICAL_POSITION_STD_FLOOR   (1UL << 1)
#define SYSTEM_GNSS_NOISE_VALID_VELOCITY_STD_FLOOR            (1UL << 2)

typedef struct
{
    float recommended_horizontal_position_std_floor_m;
    float recommended_vertical_position_std_floor_m;
    float recommended_velocity_std_floor_mps;
    uint32_t valid_mask;
} SystemGnssNoiseCharacteristics;

const char *SystemGnss_NameGet(void);
SystemDeviceResult SystemGnss_Init(void);
SystemDeviceResult SystemGnss_Start(void);
SystemDeviceResult SystemGnss_Stop(void);
SystemDeviceResult SystemGnss_RuntimeOwnerActivate(void);
void SystemGnss_Process(void);
SystemDeviceResult SystemGnss_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemGnss_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_IoDetailGet(SystemGnssIoDetail *detail);
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample);
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time);
SystemDeviceResult SystemGnss_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemGnss_ConfigApply(const SystemGnssConfig *config,
                                          SystemDeviceConfigReport *report);
SystemDeviceResult SystemGnss_ConfigVerify(const SystemGnssConfig *config,
                                           SystemDeviceConfigReport *report);
SystemDeviceResult SystemGnss_EffectiveConfigGet(SystemGnssConfig *config);
SystemDeviceResult SystemGnss_NoiseCharacteristicsGet(
    SystemGnssNoiseCharacteristics *noise);
SystemDeviceResult SystemGnss_HardwareConfigRead(
    SystemGnssHardwareConfig *config);
SystemDeviceResult SystemGnss_LastConfigReportGet(
    SystemGnssConfigTransactionReport *report);
SystemDeviceResult SystemGnss_SatelliteDiagnosticsRead(
    SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_LatestSatelliteDiagnosticsGet(
    SystemGnssSatelliteDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_RfDiagnosticsRead(
    SystemGnssRfDiagnostics *diagnostics);
SystemDeviceResult SystemGnss_LatestRfDiagnosticsGet(
    SystemGnssRfDiagnostics *diagnostics);

#endif /* __SYSTEM_GNSS_IF_H */
