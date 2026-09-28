#ifndef __NEO_M9N_DEVICE_H
#define __NEO_M9N_DEVICE_H

#include <stdint.h>

typedef struct
{
    uint32_t iTOW;
    uint16_t year;
    uint16_t pDOP;
    uint8_t month;
    uint8_t day;
    uint8_t hour;
    uint8_t min;
    uint8_t sec;
    uint8_t validDate;
    uint8_t validTime;
    uint32_t lastUpdate_ms;
    uint64_t lastUpdate_us;
    uint32_t pvtSequence;
    uint8_t online;
    uint8_t fixType;
    uint8_t gnssFixOK;
    uint8_t numSV;
    uint8_t hasValidFix;
    uint8_t positionUsable;
    uint8_t velocityUsable;
    uint8_t courseUsable;
    int32_t lon;       /* 1e-7 deg */
    int32_t lat;       /* 1e-7 deg */
    int32_t height;    /* mm, ellipsoid */
    int32_t hMSL;      /* mm */
    uint32_t hAcc;     /* mm */
    uint32_t vAcc;     /* mm */
    int32_t velN;      /* mm/s */
    int32_t velE;      /* mm/s */
    int32_t velD;      /* mm/s */
    int32_t gSpeed;    /* mm/s */
    int32_t headMot;   /* 1e-5 deg */
    uint32_t sAcc;     /* mm/s */
    uint32_t headAcc;  /* 1e-5 deg */
} GnssNeoM9nData;

typedef enum
{
    GnssNeoM9nAckNone = 0,
    GnssNeoM9nAckAck,
    GnssNeoM9nAckNak
} GnssNeoM9nAckState;

typedef enum
{
    GnssNeoM9nPersistNone = 0,
    GnssNeoM9nPersistRam,
    GnssNeoM9nPersistBbr,
    GnssNeoM9nPersistFlash,
    GnssNeoM9nPersistAll
} GnssNeoM9nPersistTarget;

typedef enum
{
    GnssProtocolDetectedNone = 0,
    GnssProtocolDetectedUbx,
    GnssProtocolDetectedNmea,
    GnssProtocolDetectedUbxNmea,
    GnssProtocolDetectedUnknown
} GnssProtocolDetected;

typedef enum
{
    GnssOutputProtocolNmeaOnly = 0,
    GnssOutputProtocolUbxOnly,
    GnssOutputProtocolUbxNmea
} GnssOutputProtocol;

#define GNSS_CONFIG_VALID_BAUD           (1U << 0)
#define GNSS_CONFIG_VALID_RATE           (1U << 1)
#define GNSS_CONFIG_VALID_DYNAMIC        (1U << 2)
#define GNSS_CONFIG_VALID_CONSTELLATIONS (1U << 3)
#define GNSS_CONFIG_VALID_PROTOCOL_IN    (1U << 4)
#define GNSS_CONFIG_VALID_PROTOCOL_OUT   (1U << 5)
#define GNSS_CONFIG_VALID_NAV_PVT        (1U << 6)
#define GNSS_CONFIG_VALID_ALL            0x7FU

typedef struct
{
    uint32_t baudrate;
    uint8_t rate_hz;
    uint8_t dynamic_model;
    uint32_t constellations_mask;
    uint8_t protocol_in;
    uint8_t protocol_out;
    uint8_t nav_pvt_rate;
    uint8_t nav_pvt_known;
    uint8_t save_cache_count;
    uint8_t baud_cached;
    uint16_t valid_mask;
    GnssNeoM9nPersistTarget read_layer;
    GnssNeoM9nPersistTarget last_write_layers;
    GnssNeoM9nAckState last_ack;
} GnssNeoM9nConfigSnapshot;

typedef struct
{
    uint8_t initialized;
    uint32_t uart_baudrate;
    uint8_t stream_seen;
    GnssProtocolDetected detected;
    uint8_t ubx_seen;
    uint8_t nmea_seen;
    uint8_t unknown_seen;
    uint8_t pvt_seen;
    uint32_t last_rx_ms;
    uint32_t last_ubx_ms;
    uint32_t last_nmea_ms;
    uint32_t last_unknown_ms;
    uint32_t rx_bytes;
    uint32_t ubx_frames;
    uint32_t ubx_pvt_count;
    uint32_t ubx_ack_count;
    uint32_t ubx_nak_count;
    uint32_t ubx_checksum_error_count;
    uint32_t nmea_sentence_count;
    uint32_t nmea_checksum_ok_count;
    uint32_t nmea_checksum_error_count;
    char last_nmea_type[8];
    uint32_t unknown_bytes;
    uint32_t process_limit_count;
} GnssNeoM9nStatusSnapshot;

#define GNSS_CONSTELLATION_GPS      (1UL << 0)
#define GNSS_CONSTELLATION_GALILEO  (1UL << 1)
#define GNSS_CONSTELLATION_BDS      (1UL << 2)
#define GNSS_CONSTELLATION_GLONASS  (1UL << 3)
#define GNSS_CONSTELLATION_QZSS     (1UL << 4)
#define GNSS_CONSTELLATION_SBAS     (1UL << 5)

typedef enum
{
    GnssNeoM9n_InitOk = 0,
    GnssNeoM9n_InitUartError
} GnssNeoM9nInitResult;

typedef enum
{
    GnssNeoM9nIdentifyOk = 0,
    GnssNeoM9nIdentifyWrongModel,
    GnssNeoM9nIdentifyTimeout,
    GnssNeoM9nIdentifyIoError
} GnssNeoM9nIdentifyResult;

GnssNeoM9nIdentifyResult GnssNeoM9n_Identify(uint8_t instance);

typedef enum
{
    GnssNeoM9nProbeStartResult_Ok = 0,
    GnssNeoM9nProbeStartResult_NotReady,
    GnssNeoM9nProbeStartResult_IoError
} GnssNeoM9nProbeStartResult;

typedef enum
{
    GnssNeoM9nProbePollResult_Pending = 0,
    GnssNeoM9nProbePollResult_Identified,
    GnssNeoM9nProbePollResult_WrongModel,
    GnssNeoM9nProbePollResult_NotReady
} GnssNeoM9nProbePollResult;

GnssNeoM9nProbeStartResult GnssNeoM9n_ProbeStart(
    uint8_t instance, uint32_t baudrate);
GnssNeoM9nProbePollResult GnssNeoM9n_ProbePoll(uint8_t instance);

typedef enum
{
    GnssNeoM9n_UpdateOk = 0,
    GnssNeoM9n_UpdateNoData
} GnssNeoM9nUpdateResult;

typedef enum
{
    GnssNeoM9nAsyncStartOk = 0,
    GnssNeoM9nAsyncStartBusy,
    GnssNeoM9nAsyncStartInvalidArgument,
    GnssNeoM9nAsyncStartNotReady,
    GnssNeoM9nAsyncStartTxError
} GnssNeoM9nAsyncStartResult;

typedef enum
{
    GnssNeoM9nAsyncPollPending = 0,
    GnssNeoM9nAsyncPollComplete
} GnssNeoM9nAsyncPollResult;

typedef enum
{
    GnssNeoM9nConfigReadResponseOk = 0,
    GnssNeoM9nConfigReadNak,
    GnssNeoM9nConfigReadTxError,
    GnssNeoM9nConfigReadChecksumError,
    GnssNeoM9nConfigReadMalformedResponse,
    GnssNeoM9nConfigReadTimeout,
    GnssNeoM9nConfigReadNotReady,
    GnssNeoM9nConfigReadIoError
} GnssNeoM9nConfigReadResult;

typedef enum
{
    GnssNeoM9nTransactionDetailNone = 0,
    GnssNeoM9nTransactionDetailResponseOk,
    GnssNeoM9nTransactionDetailNak,
    GnssNeoM9nTransactionDetailBusy,
    GnssNeoM9nTransactionDetailBadVersion,
    GnssNeoM9nTransactionDetailBadLayer,
    GnssNeoM9nTransactionDetailBadPosition,
    GnssNeoM9nTransactionDetailBadLength,
    GnssNeoM9nTransactionDetailKeyMismatch,
    GnssNeoM9nTransactionDetailValueLengthMismatch,
    GnssNeoM9nTransactionDetailCountOverflow,
    GnssNeoM9nTransactionDetailChecksumError,
    GnssNeoM9nTransactionDetailTxError,
    GnssNeoM9nTransactionDetailTimeout,
    GnssNeoM9nTransactionDetailNotReady,
    GnssNeoM9nTransactionDetailRxDiscontinuity
} GnssNeoM9nTransactionDetail;

typedef enum
{
    GnssNeoM9nConfigReadGroupNone = 0,
    GnssNeoM9nConfigReadGroupUart,
    GnssNeoM9nConfigReadGroupProtocol,
    GnssNeoM9nConfigReadGroupNavPvt,
    GnssNeoM9nConfigReadGroupRate,
    GnssNeoM9nConfigReadGroupDynamicModel,
    GnssNeoM9nConfigReadGroupSignals
} GnssNeoM9nConfigReadGroup;

typedef struct
{
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nConfigReadGroup failed_group;
    uint32_t failed_key;
    uint16_t response_length;
    uint8_t nak_class;
    uint8_t nak_id;
    GnssNeoM9nTransactionDetail detailed_result;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t received_class;
    uint8_t received_id;
    uint8_t response_version;
} GnssNeoM9nConfigReadDiagnostics;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint8_t satellite_count;
    uint8_t used_count;
    uint8_t average_cno_dbhz;
    uint8_t maximum_cno_dbhz;
    uint8_t average_quality;
    uint8_t valid;
    GnssNeoM9nConfigReadResult read_result;
    GnssNeoM9nTransactionDetail detailed_result;
    uint16_t response_length;
    uint8_t expected_class;
    uint8_t expected_id;
    uint8_t received_class;
    uint8_t received_id;
    uint8_t expected_ck_a;
    uint8_t expected_ck_b;
    uint8_t received_ck_a;
    uint8_t received_ck_b;
} GnssNeoM9nSatelliteDiagnostics;

typedef struct
{
    uint32_t ubx_frame_count;
    uint32_t ubx_checksum_error_count;
    uint32_t nmea_sentence_count;
    uint32_t nmea_checksum_ok_count;
    uint32_t nmea_checksum_error_count;
    uint32_t unknown_byte_count;
    uint32_t parser_resync_count;
} GnssNeoM9nStreamDiagnostics;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint16_t noise_per_ms;
    uint16_t agc_count;
    uint8_t rf_block_count;
    uint8_t antenna_status;
    uint8_t antenna_power;
    uint8_t jamming_state;
    uint8_t cw_suppression;
    uint8_t jamming_indicator;
    uint8_t valid;
    GnssNeoM9nConfigReadResult read_result;
    GnssNeoM9nTransactionDetail detailed_result;
    uint16_t response_length;
} GnssNeoM9nRfDiagnostics;

GnssNeoM9nInitResult GnssNeoM9n_Init(uint8_t instance);
int GnssNeoM9n_ApplyDefaultConfig(uint8_t instance);
GnssNeoM9nUpdateResult GnssNeoM9n_Process(uint8_t instance, uint32_t now_ms);
uint8_t GnssNeoM9n_GetData(uint8_t instance, GnssNeoM9nData *out);
uint8_t GnssNeoM9n_IsInitialized(uint8_t instance);
void GnssNeoM9n_GetConfigSnapshot(uint8_t instance, GnssNeoM9nConfigSnapshot *out);
void GnssNeoM9n_GetStatusSnapshot(uint8_t instance, GnssNeoM9nStatusSnapshot *out);
GnssNeoM9nAckState GnssNeoM9n_GetLastAck(uint8_t instance);

/* Bootstrap or GNSS adapter-owner context only for command/config APIs. */
int GnssNeoM9n_SendUbx(uint8_t instance, uint8_t cls, uint8_t id, const uint8_t *payload, uint16_t len);
int GnssNeoM9n_ConfigOutputUbxOnly(uint8_t instance, uint8_t layers);
int GnssNeoM9n_ConfigOutputProtocol(uint8_t instance, uint8_t layers, GnssOutputProtocol output);
int GnssNeoM9n_ConfigNavPvtOutput(uint8_t instance, uint8_t layers, uint8_t rate);
int GnssNeoM9n_ConfigNavRate(uint8_t instance, uint8_t layers, uint8_t hz);
int GnssNeoM9n_ConfigUartBaudrate(uint8_t instance, uint8_t layers, uint32_t baudrate);
int GnssNeoM9n_WaitUartConfigSettle(uint8_t instance, uint32_t minimum_wait_ms,
                                    uint32_t stream_timeout_ms);
int GnssNeoM9n_ConfigDynamicModel(uint8_t instance, uint8_t layers, uint8_t dyn_model);
int GnssNeoM9n_ConfigSignals(uint8_t instance, uint8_t layers, uint32_t constellation_mask);
int GnssNeoM9n_ConfigSignalsGpsBdsGal(uint8_t instance, uint8_t layers);
int GnssNeoM9n_WaitForNewNavPvt(uint8_t instance, uint32_t baseline_sequence,
                                uint64_t minimum_receive_timestamp_us,
                                uint32_t timeout_ms);
int GnssNeoM9n_ConfigPreset(uint8_t instance, uint8_t layers, uint32_t baudrate, uint8_t nav_rate_hz);
GnssNeoM9nConfigReadResult GnssNeoM9n_ReadHardwareConfig(uint8_t instance,
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics);
/* Runtime-owner APIs: each poll advances at most one finite state-machine step. */
GnssNeoM9nAsyncStartResult GnssNeoM9n_ConfigReadAsyncStart(uint8_t instance);
GnssNeoM9nAsyncPollResult GnssNeoM9n_ConfigReadAsyncPoll(uint8_t instance,
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult *result);
void GnssNeoM9n_ConfigReadAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail);
/* Bootstrap or GNSS-owner context only; System callers use the interface. */
GnssNeoM9nConfigReadResult GnssNeoM9n_ValgetRead(uint8_t instance,
    const uint32_t *keys,
    uint8_t count,
    GnssNeoM9nConfigReadDiagnostics *diagnostics);
int GnssNeoM9n_ReadSatelliteDiagnostics(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics);
GnssNeoM9nAsyncStartResult GnssNeoM9n_SatelliteDiagnosticsAsyncStart(uint8_t instance);
GnssNeoM9nAsyncPollResult GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics);
void GnssNeoM9n_SatelliteDiagnosticsAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail);
uint8_t GnssNeoM9n_GetSatelliteDiagnostics(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics);
int GnssNeoM9n_ReadRfDiagnostics(uint8_t instance, GnssNeoM9nRfDiagnostics *diagnostics);
GnssNeoM9nAsyncStartResult GnssNeoM9n_RfDiagnosticsAsyncStart(uint8_t instance);
GnssNeoM9nAsyncPollResult GnssNeoM9n_RfDiagnosticsAsyncPoll(uint8_t instance,
    GnssNeoM9nRfDiagnostics *diagnostics);
void GnssNeoM9n_RfDiagnosticsAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail);
uint8_t GnssNeoM9n_GetRfDiagnostics(uint8_t instance,
    GnssNeoM9nRfDiagnostics *diagnostics);
int GnssNeoM9n_SaveConfig(uint8_t instance, uint8_t layers, uint8_t *saved_count);
uint8_t GnssNeoM9n_GetSaveCacheCount(uint8_t instance);
uint8_t GnssNeoM9n_IsBaudCached(uint8_t instance);
void GnssNeoM9n_StreamDiagnosticsGet(uint8_t instance,
    GnssNeoM9nStreamDiagnostics *diagnostics);

#endif /* __NEO_M9N_DEVICE_H */
