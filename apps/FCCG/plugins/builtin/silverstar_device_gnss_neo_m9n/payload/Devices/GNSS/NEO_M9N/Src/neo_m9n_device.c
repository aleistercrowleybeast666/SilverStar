#include "neo_m9n_device.h"

#include "project_resources.h"
#include "neo_m9n_config.h"
#include "neo_m9n_config_keys.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "silverstar_assert.h"
#include <string.h>

#define GNSS_UBX_SYNC1              0xB5U
#define GNSS_UBX_SYNC2              0x62U
#define GNSS_UBX_NAV_CLASS          0x01U
#define GNSS_UBX_NAV_PVT_ID         0x07U
#define GNSS_UBX_NAV_PVT_LEN        92U
#define GNSS_UBX_NAV_SAT_ID         0x35U
#define GNSS_UBX_NAV_SAT_HEADER_LEN 8U
#define GNSS_UBX_NAV_SAT_BLOCK_LEN  12U
#define GNSS_UBX_NAV_SAT_MAX_COUNT  \
    ((GNSS_UBX_MAX_PAYLOAD_LEN - GNSS_UBX_NAV_SAT_HEADER_LEN) / \
     GNSS_UBX_NAV_SAT_BLOCK_LEN)
#define GNSS_UBX_MON_CLASS          0x0AU
#define GNSS_UBX_MON_RF_ID          0x38U
#define GNSS_UBX_MON_RF_HEADER_LEN  4U
#define GNSS_UBX_MON_RF_BLOCK_LEN   24U
#define GNSS_UBX_ACK_CLASS          0x05U
#define GNSS_UBX_ACK_ACK_ID         0x01U
#define GNSS_UBX_ACK_NAK_ID         0x00U
#define GNSS_UBX_ACK_LEN            2U
#define GNSS_UBX_MAX_PAYLOAD_LEN    1024U
#define GNSS_UBX_CFG_CLASS          0x06U
#define GNSS_UBX_CFG_VALSET_ID      0x8AU
#define GNSS_UBX_CFG_VALGET_ID      0x8BU
#define GNSS_UBX_TX_MAX_PAYLOAD_LEN 128U
#define GNSS_UBX_TX_FRAME_OVERHEAD  8U
#define GNSS_PROTOCOL_DETECT_WINDOW_MS 2000U
#define GNSS_NMEA_TYPE_LEN          7U
#define GNSS_NMEA_MAX_BODY_LEN      96U
#define GNSS_CFG_CACHE_MAX_ITEMS    24U
#define GNSS_VALSET_HEADER_LEN      4U
#define GNSS_VALGET_HEADER_LEN      4U
#define GNSS_VALSET_TRANSACTION_NONE 0x00U
#define GNSS_VALGET_LAYER_RAM       0x00U
#define GNSS_VALGET_RESPONSE_VERSION 0x01U
#define GNSS_VALGET_LAYER_BBR       0x01U
#define GNSS_VALGET_LAYER_FLASH     0x02U
#define GNSS_VALGET_LAYER_DEFAULT   0x07U
#define GNSS_VALGET_EXPECTED_MAX    31U
#define GNSS_VALGET_CACHE_MAX_ITEMS GNSS_VALGET_EXPECTED_MAX
#define GNSS_CFG_ITEM_TYPE_L        1U
#define GNSS_CFG_ITEM_TYPE_U1       1U
#define GNSS_CFG_ITEM_TYPE_U2       2U
#define GNSS_CFG_ITEM_TYPE_U4       4U
#define GNSS_CFG_ITEM_TYPE_U8       8U
#define GNSS_CFG_ITEM_TYPE_E1       1U
#define GNSS_UART_BAUDRATE_MIN      4800U
#define GNSS_MAX_WAIT_POLL_ITERATIONS 8192U
#define GNSS_MAX_BYTES_PER_PROCESS    512U
#define GNSS_PROBE_PASSIVE_MS        200U
#define GNSS_PROBE_UBX_WAIT_MS       2200U
#define GNSS_PROBE_RESCUE_SETTLE_MS  250U
#define GNSS_PROBE_VALID_NMEA_MIN    2U
#define GNSS_PUBX_FRAME_MAX_LEN     64U

typedef enum
{
    GnssProbePhasePassive = 0,
    GnssProbePhaseMonRequest,
    GnssProbePhaseMonResponse,
    GnssProbePhasePubxRequest,
    GnssProbePhasePubxSettle,
    GnssProbePhaseRescueMonRequest,
    GnssProbePhaseRescueMonResponse,
    GnssProbePhaseComplete
} GnssProbePhase;
#define GNSS_MAX_VALGET_ITEMS_PER_FRAME GNSS_VALGET_CACHE_MAX_ITEMS

typedef enum
{
    GnssUbxStateSync1 = 0,
    GnssUbxStateSync2,
    GnssUbxStateClass,
    GnssUbxStateId,
    GnssUbxStateLen1,
    GnssUbxStateLen2,
    GnssUbxStatePayload,
    GnssUbxStateCkA,
    GnssUbxStateCkB
} GnssUbxParseState;

typedef struct
{
    GnssUbxParseState state;
    uint8_t msg_class;
    uint8_t msg_id;
    uint16_t payload_len;
    uint16_t payload_idx;
    uint8_t ck_a;
    uint8_t ck_b;
    uint8_t received_ck_a;
    uint8_t received_ck_b;
    uint8_t payload[GNSS_UBX_MAX_PAYLOAD_LEN];
} GnssUbxParser_t;

typedef struct
{
    uint8_t active;
    uint8_t checksum_seen;
    uint8_t checksum_digit_count;
    uint8_t checksum_calc;
    uint8_t checksum_rx;
    uint8_t type_len;
    uint8_t type_done;
    uint8_t body_len;
    char type[GNSS_NMEA_TYPE_LEN + 1U];
} GnssNmeaParser_t;

typedef GnssNeoM9nConfigItem GnssCfgItem_t;

typedef struct
{
    GnssUbxParser_t parser;
    GnssNmeaParser_t nmea_parser;
    GnssNeoM9nData data;
    GnssNeoM9nData published_data;
    GnssNeoM9nConfigSnapshot config;
    GnssNeoM9nStatusSnapshot status;
    GnssCfgItem_t config_cache[GNSS_CFG_CACHE_MAX_ITEMS];
    GnssNeoM9nConfigSnapshot valget_config;
    GnssCfgItem_t valget_cache[GNSS_VALGET_CACHE_MAX_ITEMS];
    uint8_t config_cache_count;
    uint8_t valget_cache_count;
    uint8_t valget_wait_active;
    uint8_t valget_received;
    uint32_t valget_expected_keys[GNSS_VALGET_EXPECTED_MAX];
    uint8_t valget_expected_key_count;
    uint8_t valget_layer;
    uint8_t identity_seen;
    uint8_t identity_verified;
    GnssProbePhase probe_phase;
    uint32_t probe_phase_started_ms;
    uint32_t probe_nmea_baseline;
    uint32_t probe_baudrate;
    uint32_t item_read_started_ms;
    uint32_t item_write_started_ms;
    uint32_t item_read_key;
    uint8_t item_read_active;
    uint8_t item_write_active;
    GnssNeoM9nConfigReadDiagnostics valget_diagnostics;
    GnssNeoM9nSatelliteDiagnostics satellite_diagnostics;
    GnssNeoM9nRfDiagnostics rf_diagnostics;
    GnssNeoM9nAckState last_ack;
    uint8_t last_ack_class;
    uint8_t last_ack_id;
    uint8_t initialized;
    uint8_t uart_baud_changed;
    uint32_t uart_baseline_ubx_frames;
    uint32_t port_discontinuity_sequence;
    uint32_t parser_resync_count;
    uint8_t transaction_discontinuity;
    uint8_t satellite_wait_active;
    uint8_t rf_wait_active;
    uint32_t satellite_wait_sequence;
    uint32_t rf_wait_sequence;
} NeoM9nContext;

static NeoM9nContext s_contexts[PROJECT_NEO_M9N_INSTANCE_COUNT];

_Static_assert(PROJECT_NEO_M9N_INSTANCE_COUNT <=
               PROJECT_NEO_M9N_INSTANCE_COUNT_MAX,
               "NEO-M9N context count exceeds generated resource bound");

#define s_parser                       (s_contexts[instance].parser)
#define s_nmea_parser                  (s_contexts[instance].nmea_parser)
#define s_data                         (s_contexts[instance].data)
#define s_published_data               (s_contexts[instance].published_data)
#define s_config                       (s_contexts[instance].config)
#define s_status                       (s_contexts[instance].status)
#define s_config_cache                 (s_contexts[instance].config_cache)
#define s_valget_config                (s_contexts[instance].valget_config)
#define s_valget_cache                 (s_contexts[instance].valget_cache)
#define s_config_cache_count           (s_contexts[instance].config_cache_count)
#define s_valget_cache_count           (s_contexts[instance].valget_cache_count)
#define s_valget_wait_active           (s_contexts[instance].valget_wait_active)
#define s_valget_received              (s_contexts[instance].valget_received)
#define s_valget_expected_keys         (s_contexts[instance].valget_expected_keys)
#define s_valget_expected_key_count    \
    (s_contexts[instance].valget_expected_key_count)
#define s_valget_layer (s_contexts[instance].valget_layer)
#define s_valget_diagnostics           (s_contexts[instance].valget_diagnostics)
#define s_satellite_diagnostics        \
    (s_contexts[instance].satellite_diagnostics)
#define s_rf_diagnostics               (s_contexts[instance].rf_diagnostics)
#define s_last_ack                     (s_contexts[instance].last_ack)
#define s_last_ack_class               (s_contexts[instance].last_ack_class)
#define s_last_ack_id                  (s_contexts[instance].last_ack_id)
#define s_initialized                  (s_contexts[instance].initialized)
#define s_uart_baud_changed            (s_contexts[instance].uart_baud_changed)
#define s_uart_baseline_ubx_frames     \
    (s_contexts[instance].uart_baseline_ubx_frames)
#define s_port_discontinuity_sequence  \
    (s_contexts[instance].port_discontinuity_sequence)
#define s_parser_resync_count          (s_contexts[instance].parser_resync_count)
#define s_transaction_discontinuity    \
    (s_contexts[instance].transaction_discontinuity)
#define s_satellite_wait_active        \
    (s_contexts[instance].satellite_wait_active)
#define s_rf_wait_active               (s_contexts[instance].rf_wait_active)
#define s_satellite_wait_sequence      \
    (s_contexts[instance].satellite_wait_sequence)
#define s_rf_wait_sequence             (s_contexts[instance].rf_wait_sequence)

static PlatformUartId NeoM9nResource_UartGet(uint8_t instance)
{
    ProjectNeoM9nResources resources;

    if (ProjectNeoM9nResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    {
        return (PlatformUartId)PLATFORM_UART_COUNT;
    }
    return resources.uart;
}

typedef enum
{
    GnssConfigAsyncIdle = 0,
    GnssConfigAsyncStartGroup,
    GnssConfigAsyncWaitGroup,
    GnssConfigAsyncStartKey,
    GnssConfigAsyncWaitKey,
    GnssConfigAsyncComplete
} GnssConfigAsyncState;

typedef struct
{
    GnssNeoM9nConfigReadGroup group;
    const uint32_t *keys;
    uint8_t key_count;
    uint16_t valid_bits;
} GnssConfigReadGroupDefinition;

typedef struct
{
    GnssConfigAsyncState state;
    GnssNeoM9nConfigSnapshot aggregate;
    GnssNeoM9nConfigReadDiagnostics first_failure;
    GnssNeoM9nConfigReadDiagnostics key_failure;
    GnssNeoM9nConfigReadResult first_result;
    GnssNeoM9nConfigReadResult key_result;
    GnssNeoM9nConfigReadResult result;
    uint32_t start_ms;
    uint32_t request_start_ms;
    uint8_t group_index;
    uint8_t key_index;
} GnssConfigAsyncTransaction;

static const uint32_t s_config_uart_keys[] =
{
    GNSS_CFG_UART1_BAUDRATE
};
static const uint32_t s_config_protocol_keys[] =
{
    GNSS_CFG_UART1INPROT_UBX,
    GNSS_CFG_UART1INPROT_NMEA,
    GNSS_CFG_UART1INPROT_RTCM3X,
    GNSS_CFG_UART1OUTPROT_UBX,
    GNSS_CFG_UART1OUTPROT_NMEA
};
static const uint32_t s_config_nav_pvt_keys[] =
{
    GNSS_CFG_MSGOUT_NAV_PVT_UART1
};
static const uint32_t s_config_rate_keys[] =
{
    GNSS_CFG_RATE_MEAS,
    GNSS_CFG_RATE_NAV,
    GNSS_CFG_RATE_TIMEREF
};
static const uint32_t s_config_dynamic_keys[] =
{
    GNSS_CFG_NAVSPG_DYNMODEL
};
static const uint32_t s_config_signal_keys[] =
{
    GNSS_CFG_SIGNAL_GPS_ENA,
    GNSS_CFG_SIGNAL_GPS_L1CA_ENA,
    GNSS_CFG_SIGNAL_SBAS_ENA,
    GNSS_CFG_SIGNAL_SBAS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GAL_ENA,
    GNSS_CFG_SIGNAL_GAL_E1_ENA,
    GNSS_CFG_SIGNAL_BDS_ENA,
    GNSS_CFG_SIGNAL_BDS_B1_ENA,
    GNSS_CFG_SIGNAL_QZSS_ENA,
    GNSS_CFG_SIGNAL_QZSS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GLO_ENA,
    GNSS_CFG_SIGNAL_GLO_L1_ENA
};
static const GnssConfigReadGroupDefinition s_config_read_groups[] =
{
    {GnssNeoM9nConfigReadGroupUart, s_config_uart_keys,
     (uint8_t)(sizeof(s_config_uart_keys) / sizeof(s_config_uart_keys[0])),
     GNSS_CONFIG_VALID_BAUD},
    {GnssNeoM9nConfigReadGroupProtocol, s_config_protocol_keys,
     (uint8_t)(sizeof(s_config_protocol_keys) /
               sizeof(s_config_protocol_keys[0])),
     GNSS_CONFIG_VALID_PROTOCOL_IN | GNSS_CONFIG_VALID_PROTOCOL_OUT},
    {GnssNeoM9nConfigReadGroupNavPvt, s_config_nav_pvt_keys,
     (uint8_t)(sizeof(s_config_nav_pvt_keys) /
               sizeof(s_config_nav_pvt_keys[0])),
     GNSS_CONFIG_VALID_NAV_PVT},
    {GnssNeoM9nConfigReadGroupRate, s_config_rate_keys,
     (uint8_t)(sizeof(s_config_rate_keys) / sizeof(s_config_rate_keys[0])),
     GNSS_CONFIG_VALID_RATE},
    {GnssNeoM9nConfigReadGroupDynamicModel, s_config_dynamic_keys,
     (uint8_t)(sizeof(s_config_dynamic_keys) /
               sizeof(s_config_dynamic_keys[0])),
     GNSS_CONFIG_VALID_DYNAMIC},
    {GnssNeoM9nConfigReadGroupSignals, s_config_signal_keys,
     (uint8_t)(sizeof(s_config_signal_keys) /
               sizeof(s_config_signal_keys[0])),
     GNSS_CONFIG_VALID_CONSTELLATIONS}
};
static GnssConfigAsyncTransaction
    s_config_async_contexts[PROJECT_NEO_M9N_INSTANCE_COUNT];

#define s_config_async (s_config_async_contexts[instance])

static uint32_t Gnss_IrqLock(void);
static void Gnss_IrqUnlock(uint32_t primask);
static void Gnss_ParserReset(uint8_t instance);
static void Gnss_NmeaReset(uint8_t instance);
static void Gnss_DiscontinuityHandle(uint8_t instance);
static uint8_t Gnss_RingPopByte(uint8_t instance, uint8_t *byte);
static uint32_t Gnss_UartBaudrateGet(uint8_t instance);
static void Gnss_ParseByte(uint8_t instance, uint8_t byte, uint32_t now_ms);
static uint8_t Gnss_ParseNmeaByte(uint8_t instance, uint8_t byte, uint32_t now_ms);
static void Gnss_FinishNmea(uint8_t instance, uint32_t now_ms);
static uint8_t Gnss_HexValue(uint8_t byte, uint8_t *value);
static void Gnss_ChecksumAdd(uint8_t instance, uint8_t byte);
static void Gnss_ParseNavPvt(uint8_t instance, uint32_t now_ms);
static void Gnss_ParseNavSat(uint8_t instance);
static void Gnss_ParseMonRf(uint8_t instance);
static void Gnss_ParseAck(uint8_t instance);
static void Gnss_ParseValget(uint8_t instance);
static void Gnss_UpdateUbxStats(uint8_t instance, uint32_t now_ms);
static void Gnss_UpdateUnknownStats(uint8_t instance, uint32_t now_ms);
static GnssProtocolDetected Gnss_GetDetected(uint8_t instance, uint32_t now_ms);
static uint32_t Gnss_ReadU32Le(const uint8_t *data);
static uint64_t Gnss_ReadU64Le(const uint8_t *data);
static uint16_t Gnss_ReadU16Le(const uint8_t *data);
static int32_t Gnss_ReadI32Le(const uint8_t *data);
static void Gnss_UpdateStatus(uint8_t instance, uint32_t now_ms);
static void Gnss_WriteU16Le(uint8_t *data, uint16_t value);
static void Gnss_WriteU32Le(uint8_t *data, uint32_t value);
static uint8_t Gnss_IsDynModelValid(uint8_t dyn_model);
static void Gnss_ProcessDelayMs(uint8_t instance, uint32_t delay_ms);
static uint8_t Gnss_UbxFrameWait(uint8_t instance, uint32_t baseline_frame_count,
                                 uint32_t timeout_ms);
static GnssNeoM9nPersistTarget Gnss_PersistFromLayers(uint8_t instance, uint8_t layers);
static void Gnss_ConfigCacheStore(uint8_t instance, const GnssCfgItem_t *items, uint8_t count);
static void Gnss_ConfigCacheStoreOnRamSuccess(uint8_t instance, uint8_t layers, const GnssCfgItem_t *items, uint8_t count);
static uint8_t Gnss_ConfigCacheContainsKey(uint8_t instance, uint32_t key);
static uint8_t Gnss_ConfigKeyValueLen(uint32_t key);
static void Gnss_ValgetScratchReset(uint8_t instance);
static void Gnss_ValgetCacheStore(uint8_t instance, uint32_t key, uint64_t value, uint8_t value_len);
static void Gnss_ValgetStore(uint8_t instance, uint32_t key, uint64_t value, uint8_t value_len);
static void Gnss_ClearAckWait(uint8_t instance, uint8_t cls, uint8_t id);
static int Gnss_WaitAck(uint8_t instance, uint8_t cls, uint8_t id, uint32_t timeout_ms);
static GnssNeoM9nConfigReadResult Gnss_WaitValget(uint8_t instance, uint32_t timeout_ms);
static PlatformResult Gnss_UbxFrameEnqueue(uint8_t instance,
    uint8_t cls, uint8_t id, const uint8_t *payload, uint16_t length)
{
    uint8_t frame[GNSS_UBX_TX_MAX_PAYLOAD_LEN + GNSS_UBX_TX_FRAME_OVERHEAD];
    uint8_t ck_a = 0U;
    uint8_t ck_b = 0U;
    uint16_t index;

    if (((payload == NULL) && (length != 0U)) ||
        (length > GNSS_UBX_TX_MAX_PAYLOAD_LEN))
    { return PLATFORM_INVALID_ARGUMENT; }
    frame[0] = GNSS_UBX_SYNC1;
    frame[1] = GNSS_UBX_SYNC2;
    frame[2] = cls;
    frame[3] = id;
    Gnss_WriteU16Le(&frame[4], length);
    if (length != 0U) { (void)memcpy(&frame[6], payload, length); }
    for (index = 2U; index < (uint16_t)(6U + length); index++)
    {
        ck_a = (uint8_t)(ck_a + frame[index]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }
    frame[6U + length] = ck_a;
    frame[7U + length] = ck_b;
    return PlatformUart_WriteFrameAsync(NeoM9nResource_UartGet(instance),
        frame, (uint16_t)(length + GNSS_UBX_TX_FRAME_OVERHEAD),
        PLATFORM_UART_TX_PRIORITY);
}

static GnssNeoM9nAsyncStartResult Gnss_ValgetAsyncStart(uint8_t instance,
    const uint32_t *keys,
    uint8_t count, uint8_t layer);
static GnssNeoM9nAsyncPollResult Gnss_ValgetAsyncPoll(uint8_t instance,
    GnssNeoM9nConfigSnapshot *snapshot,
    GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult *result);
static void Gnss_ValgetAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail);
static GnssNeoM9nConfigReadResult GnssNeoM9n_SendValget(uint8_t instance,
    const uint32_t *keys,
    uint8_t count,
    uint32_t timeout_ms);
static int GnssNeoM9n_SendValset(uint8_t instance, uint8_t layers, const GnssCfgItem_t *items, uint8_t count, uint32_t timeout_ms);

static uint32_t Gnss_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void Gnss_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static void Gnss_ParserReset(uint8_t instance)
{
    memset(&s_parser, 0, sizeof(s_parser));
    s_parser.state = GnssUbxStateSync1;
}

static void Gnss_NmeaReset(uint8_t instance)
{
    memset(&s_nmea_parser, 0, sizeof(s_nmea_parser));
}

static void Gnss_DiscontinuityHandle(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    Gnss_ParserReset(instance);
    Gnss_NmeaReset(instance);
    s_parser_resync_count++;
    s_transaction_discontinuity = 1U;
    if (s_valget_wait_active != 0U)
    {
        s_valget_diagnostics.result = GnssNeoM9nConfigReadIoError;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailRxDiscontinuity;
        s_valget_received = 1U;
    }
    if (s_satellite_wait_active != 0U)
    {
        s_satellite_diagnostics.timestamp_us =
            PlatformTime_Us();
        s_satellite_diagnostics.valid = 0U;
        s_satellite_diagnostics.read_result = GnssNeoM9nConfigReadIoError;
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailRxDiscontinuity;
        s_satellite_diagnostics.sequence++;
    }
    if (s_rf_wait_active != 0U)
    {
        s_rf_diagnostics.timestamp_us = PlatformTime_Us();
        s_rf_diagnostics.valid = 0U;
        s_rf_diagnostics.read_result = GnssNeoM9nConfigReadIoError;
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailRxDiscontinuity;
        s_rf_diagnostics.sequence++;
    }
}

static uint8_t Gnss_HexValue(uint8_t byte, uint8_t *value)
{
    if (value == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(value, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (value == NULL)
    {
        return 0U;
    }

    if ((byte >= (uint8_t)'0') && (byte <= (uint8_t)'9'))
    {
        *value = (uint8_t)(byte - (uint8_t)'0');
        return 1U;
    }
    if ((byte >= (uint8_t)'A') && (byte <= (uint8_t)'F'))
    {
        *value = (uint8_t)(byte - (uint8_t)'A' + 10U);
        return 1U;
    }
    if ((byte >= (uint8_t)'a') && (byte <= (uint8_t)'f'))
    {
        *value = (uint8_t)(byte - (uint8_t)'a' + 10U);
        return 1U;
    }

    return 0U;
}

static void Gnss_FinishNmea(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_nmea_parser, GnssNmeaParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_status.stream_seen = 1U;
    s_status.nmea_seen = 1U;
    s_status.last_nmea_ms = now_ms;
    s_status.nmea_sentence_count++;

    if (s_nmea_parser.type_len != 0U)
    {
        memcpy(s_status.last_nmea_type,
               s_nmea_parser.type,
               sizeof(s_status.last_nmea_type));
        s_status.last_nmea_type[sizeof(s_status.last_nmea_type) - 1U] = '\0';
    }

    if (s_nmea_parser.checksum_seen != 0U)
    {
        if ((s_nmea_parser.checksum_digit_count == 2U) &&
            (s_nmea_parser.checksum_rx == s_nmea_parser.checksum_calc))
        {
            s_status.nmea_checksum_ok_count++;
        }
        else
        {
            s_status.nmea_checksum_error_count++;
            s_parser_resync_count++;
        }
    }

    Gnss_NmeaReset(instance);
}

static void Gnss_NmeaChecksumDigitParse(uint8_t instance, uint8_t byte)
{
    uint8_t hex_value;

    if (s_nmea_parser.checksum_digit_count >= 2U) { return; }
    if (Gnss_HexValue(byte, &hex_value) == 0U)
    {
        s_nmea_parser.checksum_digit_count = 3U;
        return;
    }
    s_nmea_parser.checksum_rx =
        (uint8_t)((s_nmea_parser.checksum_rx << 4) | hex_value);
    s_nmea_parser.checksum_digit_count++;
}

static uint8_t Gnss_ParseNmeaByte(uint8_t instance, uint8_t byte, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_nmea_parser, GnssNmeaParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_nmea_parser.active == 0U)
    {
        if (byte == (uint8_t)'$')
        {
            Gnss_NmeaReset(instance);
            s_nmea_parser.active = 1U;
            return 1U;
        }
        return 0U;
    }

    if (byte == (uint8_t)'\r')
    {
        return 1U;
    }

    if (byte == (uint8_t)'\n')
    {
        Gnss_FinishNmea(instance, now_ms);
        return 1U;
    }

    if (s_nmea_parser.body_len >= GNSS_NMEA_MAX_BODY_LEN)
    {
        Gnss_NmeaReset(instance);
        Gnss_UpdateUnknownStats(instance, now_ms);
        return 1U;
    }
    s_nmea_parser.body_len++;

    if (s_nmea_parser.checksum_seen != 0U)
    {
        Gnss_NmeaChecksumDigitParse(instance, byte);
        return 1U;
    }

    if (byte == (uint8_t)'*')
    {
        s_nmea_parser.checksum_seen = 1U;
        return 1U;
    }

    s_nmea_parser.checksum_calc ^= byte;
    if (byte == (uint8_t)',')
    {
        s_nmea_parser.type_done = 1U;
    }
    else if ((s_nmea_parser.type_done == 0U) &&
             (s_nmea_parser.type_len < GNSS_NMEA_TYPE_LEN))
    {
        s_nmea_parser.type[s_nmea_parser.type_len++] = (char)byte;
        s_nmea_parser.type[s_nmea_parser.type_len] = '\0';
    }

    return 1U;
}

static uint8_t Gnss_RingPopByte(uint8_t instance, uint8_t *byte)
{
    uint16_t read_length = 0U;

    if (PlatformUart_Read(NeoM9nResource_UartGet(instance), byte, 1U, &read_length) !=
        PLATFORM_OK)
    {
        return 0U;
    }
    return (read_length == 1U) ? 1U : 0U;
}

static uint32_t Gnss_UartBaudrateGet(uint8_t instance)
{
    uint32_t baudrate = 0U;

    (void)PlatformUart_BaudGet(NeoM9nResource_UartGet(instance), &baudrate);
    return baudrate;
}

static void Gnss_ChecksumAdd(uint8_t instance, uint8_t byte)
{
    s_parser.ck_a = (uint8_t)(s_parser.ck_a + byte);
    s_parser.ck_b = (uint8_t)(s_parser.ck_b + s_parser.ck_a);
}

static uint32_t Gnss_ReadU32Le(const uint8_t *data)
{
    return ((uint32_t)data[0]) |
           ((uint32_t)data[1] << 8) |
           ((uint32_t)data[2] << 16) |
           ((uint32_t)data[3] << 24);
}

static uint16_t Gnss_ReadU16Le(const uint8_t *data)
{
    return (uint16_t)(((uint16_t)data[1] << 8) | data[0]);
}

static int32_t Gnss_ReadI32Le(const uint8_t *data)
{
    return (int32_t)Gnss_ReadU32Le(data);
}

static void Gnss_WriteU16Le(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)(value & 0xFFU);
    data[1] = (uint8_t)((value >> 8) & 0xFFU);
}

static void Gnss_WriteU32Le(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)(value & 0xFFU);
    data[1] = (uint8_t)((value >> 8) & 0xFFU);
    data[2] = (uint8_t)((value >> 16) & 0xFFU);
    data[3] = (uint8_t)((value >> 24) & 0xFFU);
}

static uint8_t Gnss_IsDynModelValid(uint8_t dyn_model)
{
    return ((dyn_model == GNSS_DYNMODEL_PORTABLE) ||
            (dyn_model == GNSS_DYNMODEL_STATIONARY) ||
            (dyn_model == GNSS_DYNMODEL_PEDESTRIAN) ||
            (dyn_model == GNSS_DYNMODEL_AUTOMOTIVE) ||
            (dyn_model == GNSS_DYNMODEL_SEA) ||
            (dyn_model == GNSS_DYNMODEL_AIRBORNE_1G) ||
            (dyn_model == GNSS_DYNMODEL_AIRBORNE_2G) ||
            (dyn_model == GNSS_DYNMODEL_AIRBORNE_4G)) ? 1U : 0U;
}

static void Gnss_ProcessDelayMs(uint8_t instance, uint32_t delay_ms)
{
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t poll;

    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >= delay_ms)
        {
            break;
        }
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        PlatformTime_DelayMs(1U);
    }
}

static uint64_t Gnss_ReadU64Le(const uint8_t *data)
{
    return (uint64_t)Gnss_ReadU32Le(data) |
           ((uint64_t)Gnss_ReadU32Le(&data[4]) << 32U);
}

static uint8_t Gnss_UbxFrameWait(uint8_t instance, uint32_t baseline_frame_count,
                                 uint32_t timeout_ms)
{
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t poll;

    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        if (s_status.ubx_frames > baseline_frame_count)
        {
            return 1U;
        }
        PlatformTime_DelayMs(1U);
        if ((PlatformTime_Ms() - start_ms) >= timeout_ms)
        {
            break;
        }
    }
    return 0U;
}

static GnssNeoM9nPersistTarget Gnss_PersistFromLayers(uint8_t instance, uint8_t layers)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((layers & (GNSS_CFG_LAYER_BBR | GNSS_CFG_LAYER_FLASH)) ==
        (GNSS_CFG_LAYER_BBR | GNSS_CFG_LAYER_FLASH))
    {
        return GnssNeoM9nPersistAll;
    }

    if ((layers & GNSS_CFG_LAYER_FLASH) != 0U)
    {
        return GnssNeoM9nPersistFlash;
    }

    if ((layers & GNSS_CFG_LAYER_BBR) != 0U)
    {
        return GnssNeoM9nPersistBbr;
    }

    if ((layers & GNSS_CFG_LAYER_RAM) != 0U)
    {
        return GnssNeoM9nPersistRam;
    }

    return GnssNeoM9nPersistNone;
}

static void Gnss_ConfigCacheStore(uint8_t instance, const GnssCfgItem_t *items, uint8_t count)
{
    if (items == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(items, GnssCfgItem_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t i;
    uint8_t j;
    uint8_t found;

    if (items == NULL)
    {
        return;
    }

    for (i = 0U; i < count; i++)
    {
        found = 0U;
        for (j = 0U; j < s_config_cache_count; j++)
        {
            if (s_config_cache[j].key == items[i].key)
            {
                s_config_cache[j] = items[i];
                found = 1U;
                break;
            }
        }

        if ((found == 0U) && (s_config_cache_count < GNSS_CFG_CACHE_MAX_ITEMS))
        {
            s_config_cache[s_config_cache_count] = items[i];
            s_config_cache_count++;
        }
    }

    s_config.save_cache_count = s_config_cache_count;
    s_config.baud_cached = Gnss_ConfigCacheContainsKey(instance, GNSS_CFG_UART1_BAUDRATE);
}

static void Gnss_ConfigCacheStoreOnRamSuccess(uint8_t instance, uint8_t layers, const GnssCfgItem_t *items, uint8_t count)
{
    s_config.last_write_layers = Gnss_PersistFromLayers(instance, layers);

    if ((layers & GNSS_CFG_LAYER_RAM) != 0U)
    {
        Gnss_ConfigCacheStore(instance, items, count);
    }
}

static uint8_t Gnss_ConfigCacheContainsKey(uint8_t instance, uint32_t key)
{
    uint8_t i;

    for (i = 0U; i < s_config_cache_count; i++)
    {
        if (s_config_cache[i].key == key)
        {
            return 1U;
        }
    }

    return 0U;
}

static uint8_t Gnss_ConfigKeyValueLen(uint32_t key)
{
    switch ((key >> 28U) & 0x0FU)
    {
        case 0x01U: /* L */
        case 0x02U: /* U1/I1/E1/X1 */
            return GNSS_CFG_ITEM_TYPE_U1;
        case 0x03U: /* U2/I2/E2/X2 */
            return GNSS_CFG_ITEM_TYPE_U2;
        case 0x04U: /* U4/I4/E4/X4/R4 */
            return GNSS_CFG_ITEM_TYPE_U4;
        case 0x05U: /* U8/I8/X8/R8 */
            return GNSS_CFG_ITEM_TYPE_U8;
        default:
            return 0U;
    }
}

static void Gnss_ValgetScratchReset(uint8_t instance)
{
    memset(&s_valget_config, 0, sizeof(s_valget_config));
    memset(s_valget_cache, 0, sizeof(s_valget_cache));
    s_valget_cache_count = 0U;
    s_valget_config.read_layer = GnssNeoM9nPersistRam;
    s_valget_config.last_write_layers = s_config.last_write_layers;
    s_valget_config.last_ack = s_config.last_ack;
}

static void Gnss_ValgetCacheStore(uint8_t instance, uint32_t key, uint64_t value, uint8_t value_len)
{
    if (s_valget_cache_count >= GNSS_VALGET_CACHE_MAX_ITEMS)
    {
        return;
    }

    s_valget_cache[s_valget_cache_count].key = key;
    s_valget_cache[s_valget_cache_count].value = value;
    s_valget_cache[s_valget_cache_count].value_len = value_len;
    s_valget_cache_count++;
}

static void Gnss_ValgetSignalStore(uint8_t instance, uint32_t key, uint64_t value)
{
    SILVERSTAR_ASSERT_OBJECT(&s_valget_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    switch (key)
    {
        case GNSS_CFG_SIGNAL_GPS_ENA:
        case GNSS_CFG_SIGNAL_GPS_L1CA_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_GPS; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        case GNSS_CFG_SIGNAL_GAL_ENA:
        case GNSS_CFG_SIGNAL_GAL_E1_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_GALILEO; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        case GNSS_CFG_SIGNAL_BDS_ENA:
        case GNSS_CFG_SIGNAL_BDS_B1_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_BDS; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        case GNSS_CFG_SIGNAL_GLO_ENA:
        case GNSS_CFG_SIGNAL_GLO_L1_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_GLONASS; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        case GNSS_CFG_SIGNAL_QZSS_ENA:
        case GNSS_CFG_SIGNAL_QZSS_L1CA_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_QZSS; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        case GNSS_CFG_SIGNAL_SBAS_ENA:
        case GNSS_CFG_SIGNAL_SBAS_L1CA_ENA:
            if (value != 0U) { s_valget_config.constellations_mask |= GNSS_CONSTELLATION_SBAS; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_CONSTELLATIONS;
            break;
        default:
            break;
    }
}

static void Gnss_ValgetStore(uint8_t instance, uint32_t key, uint64_t value, uint8_t value_len)
{
    SILVERSTAR_ASSERT_OBJECT(&s_valget_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    Gnss_ValgetCacheStore(instance, key, value, value_len);

    switch (key)
    {
        case GNSS_CFG_UART1_BAUDRATE:
            s_valget_config.baudrate = (uint32_t)value;
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_BAUD;
            break;

        case GNSS_CFG_RATE_MEAS:
            if ((value != 0U) && ((1000U % (uint32_t)value) == 0U))
            {
                s_valget_config.rate_hz = (uint8_t)(1000U / (uint32_t)value);
            }
            else
            {
                s_valget_config.rate_hz = 0U;
            }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_RATE;
            break;

        case GNSS_CFG_NAVSPG_DYNMODEL:
            s_valget_config.dynamic_model = (uint8_t)value;
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_DYNAMIC;
            break;

        case GNSS_CFG_UART1INPROT_UBX:
            if (value != 0U) { s_valget_config.protocol_in |= 0x01U; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_PROTOCOL_IN;
            break;

        case GNSS_CFG_UART1INPROT_NMEA:
            if (value != 0U) { s_valget_config.protocol_in |= 0x02U; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_PROTOCOL_IN;
            break;

        case GNSS_CFG_UART1INPROT_RTCM3X:
            if (value != 0U) { s_valget_config.protocol_in |= 0x04U; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_PROTOCOL_IN;
            break;

        case GNSS_CFG_UART1OUTPROT_UBX:
            if (value != 0U) { s_valget_config.protocol_out |= 0x01U; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_PROTOCOL_OUT;
            break;

        case GNSS_CFG_UART1OUTPROT_NMEA:
            if (value != 0U) { s_valget_config.protocol_out |= 0x02U; }
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_PROTOCOL_OUT;
            break;

        case GNSS_CFG_MSGOUT_NAV_PVT_UART1:
            s_valget_config.nav_pvt_rate = (uint8_t)value;
            s_valget_config.nav_pvt_known = 1U;
            s_valget_config.valid_mask |= GNSS_CONFIG_VALID_NAV_PVT;
            break;

        default:
            Gnss_ValgetSignalStore(instance, key, value);
            break;
    }
}

static void Gnss_ClearAckWait(uint8_t instance, uint8_t cls, uint8_t id)
{
    s_transaction_discontinuity = 0U;
    s_last_ack = GnssNeoM9nAckNone;
    s_last_ack_class = cls;
    s_last_ack_id = id;
    s_config.last_ack = s_last_ack;
}

static void Gnss_UpdateUbxStats(uint8_t instance, uint32_t now_ms)
{
    s_status.stream_seen = 1U;
    s_status.ubx_seen = 1U;
    s_status.last_ubx_ms = now_ms;
    s_status.ubx_frames++;
}

static void Gnss_UpdateUnknownStats(uint8_t instance, uint32_t now_ms)
{
    s_status.stream_seen = 1U;
    s_status.unknown_seen = 1U;
    s_status.last_unknown_ms = now_ms;
    s_status.unknown_bytes++;
}

static GnssProtocolDetected Gnss_GetDetected(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_status, GnssNeoM9nStatusSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t recent_ubx = ((s_status.last_ubx_ms != 0U) &&
                          ((now_ms - s_status.last_ubx_ms) <= GNSS_PROTOCOL_DETECT_WINDOW_MS)) ? 1U : 0U;
    uint8_t recent_nmea = ((s_status.last_nmea_ms != 0U) &&
                           ((now_ms - s_status.last_nmea_ms) <= GNSS_PROTOCOL_DETECT_WINDOW_MS)) ? 1U : 0U;
    uint8_t recent_unknown = ((s_status.last_unknown_ms != 0U) &&
                              ((now_ms - s_status.last_unknown_ms) <= GNSS_PROTOCOL_DETECT_WINDOW_MS)) ? 1U : 0U;

    if ((recent_ubx != 0U) && (recent_nmea != 0U))
    {
        return GnssProtocolDetectedUbxNmea;
    }
    if (recent_ubx != 0U)
    {
        return GnssProtocolDetectedUbx;
    }
    if (recent_nmea != 0U)
    {
        return GnssProtocolDetectedNmea;
    }
    if (recent_unknown != 0U)
    {
        return GnssProtocolDetectedUnknown;
    }

    return GnssProtocolDetectedNone;
}

static int Gnss_WaitAck(uint8_t instance, uint8_t cls, uint8_t id, uint32_t timeout_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_status, GnssNeoM9nStatusSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t now_ms;
    uint32_t poll;

    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >= timeout_ms)
        {
            break;
        }
        now_ms = PlatformTime_Ms();
        (void)GnssNeoM9n_Process(instance, now_ms);

        if ((s_last_ack_class == cls) && (s_last_ack_id == id))
        {
            if (s_last_ack == GnssNeoM9nAckAck)
            {
                return 0;
            }
            if (s_last_ack == GnssNeoM9nAckNak)
            {
                return -3;
            }
        }

        PlatformTime_DelayMs(1U);
    }

    return -2;
}

static uint8_t Gnss_ValgetCacheContainsKey(uint8_t instance, uint32_t key)
{
    uint8_t index;

    for (index = 0U; index < s_valget_cache_count; index++)
    {
        if (s_valget_cache[index].key == key) { return 1U; }
    }
    return 0U;
}

static GnssNeoM9nConfigReadResult Gnss_WaitValget(uint8_t instance, uint32_t timeout_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_valget_diagnostics,
        GnssNeoM9nConfigReadDiagnostics, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t now_ms;
    uint32_t poll;

    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >= timeout_ms)
        {
            break;
        }
        now_ms = PlatformTime_Ms();
        (void)GnssNeoM9n_Process(instance, now_ms);

        if (s_transaction_discontinuity != 0U)
        {
            return GnssNeoM9nConfigReadIoError;
        }
        if (s_valget_received != 0U)
        {
            return s_valget_diagnostics.result;
        }
        PlatformTime_DelayMs(1U);
    }
    s_valget_diagnostics.result = GnssNeoM9nConfigReadTimeout;
    s_valget_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailTimeout;
    return s_valget_diagnostics.result;
}

static GnssNeoM9nAsyncStartResult Gnss_ValgetAsyncStart(uint8_t instance,
    const uint32_t *keys,
    uint8_t count, uint8_t layer)
{
    if (keys == NULL) { return GnssNeoM9nAsyncStartInvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(keys, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t payload[GNSS_UBX_TX_MAX_PAYLOAD_LEN];
    uint16_t payload_len = GNSS_VALGET_HEADER_LEN;
    uint8_t index;

    if ((keys == NULL) || (count == 0U) ||
        (count > GNSS_VALGET_EXPECTED_MAX) || (layer > GNSS_VALGET_LAYER_FLASH) ||
        ((uint16_t)(GNSS_VALGET_HEADER_LEN + ((uint16_t)count * 4U)) >
         GNSS_UBX_TX_MAX_PAYLOAD_LEN))
    {
        return GnssNeoM9nAsyncStartInvalidArgument;
    }
    if ((s_valget_wait_active != 0U) ||
        (s_satellite_wait_active != 0U) || (s_rf_wait_active != 0U))
    {
        return GnssNeoM9nAsyncStartBusy;
    }
    Gnss_ValgetScratchReset(instance);
    (void)memset(&s_valget_diagnostics, 0,
                 sizeof(s_valget_diagnostics));
    s_valget_diagnostics.result = GnssNeoM9nConfigReadTimeout;
    s_valget_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailTimeout;
    s_valget_diagnostics.expected_class = GNSS_UBX_CFG_CLASS;
    s_valget_diagnostics.expected_id = GNSS_UBX_CFG_VALGET_ID;
    s_valget_received = 0U;
    s_valget_wait_active = 1U;
    s_transaction_discontinuity = 0U;
    s_valget_expected_key_count = count;
    payload[0] = 0x00U;
    payload[1] = layer;
    s_valget_layer = layer;
    payload[2] = 0x00U;
    payload[3] = 0x00U;
    for (index = 0U; index < count; index++)
    {
        s_valget_expected_keys[index] = keys[index];
        Gnss_WriteU32Le(&payload[payload_len], keys[index]);
        payload_len = (uint16_t)(payload_len + 4U);
    }

    {
        PlatformResult send_result = Gnss_UbxFrameEnqueue(instance,
            GNSS_UBX_CFG_CLASS, GNSS_UBX_CFG_VALGET_ID,
            payload, payload_len);
        if (send_result == PLATFORM_OK)
        { return GnssNeoM9nAsyncStartOk; }
        s_valget_wait_active = 0U;
        if (send_result == PLATFORM_BUSY)
        { return GnssNeoM9nAsyncStartBusy; }
    }
    {
        s_valget_diagnostics.result = GnssNeoM9nConfigReadTxError;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailTxError;
        return GnssNeoM9nAsyncStartTxError;
    }
}

static GnssNeoM9nAsyncPollResult Gnss_ValgetAsyncPoll(uint8_t instance,
    GnssNeoM9nConfigSnapshot *snapshot,
    GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult *result)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_valget_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(&s_valget_diagnostics,
        GnssNeoM9nConfigReadDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    if (s_valget_wait_active == 0U)
    {
        return GnssNeoM9nAsyncPollPending;
    }
    if (s_valget_received == 0U)
    {
        return GnssNeoM9nAsyncPollPending;
    }
    s_valget_wait_active = 0U;
    if (s_valget_diagnostics.result == GnssNeoM9nConfigReadResponseOk)
    {
        for (index = 0U; index < s_valget_expected_key_count; index++)
        {
            if (Gnss_ValgetCacheContainsKey(instance,
                    s_valget_expected_keys[index]) == 0U)
            {
                s_valget_diagnostics.result =
                    GnssNeoM9nConfigReadMalformedResponse;
                s_valget_diagnostics.detailed_result =
                    GnssNeoM9nTransactionDetailKeyMismatch;
                break;
            }
        }
    }
    if (snapshot != NULL) { *snapshot = s_valget_config; }
    if (diagnostics != NULL) { *diagnostics = s_valget_diagnostics; }
    if (result != NULL) { *result = s_valget_diagnostics.result; }
    return GnssNeoM9nAsyncPollComplete;
}

static void Gnss_ValgetAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail)
{
    s_valget_diagnostics.result = result;
    s_valget_diagnostics.detailed_result = detail;
    s_valget_received = 1U;
}

static GnssNeoM9nConfigReadResult Gnss_ValgetLayerRead(uint8_t instance,
    const uint32_t *keys, uint8_t count, uint32_t timeout_ms, uint8_t layer)
{
    if (keys == NULL) { return GnssNeoM9nConfigReadNotReady; }
    SILVERSTAR_ASSERT_OBJECT(keys, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nAsyncStartResult start_result;

    /* Bootstrap-only path may synchronously drain frames queued before submit. */
    (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
    start_result = Gnss_ValgetAsyncStart(instance, keys, count, layer);
    if (start_result == GnssNeoM9nAsyncStartInvalidArgument)
    {
        return GnssNeoM9nConfigReadMalformedResponse;
    }
    if (start_result == GnssNeoM9nAsyncStartBusy)
    {
        s_valget_diagnostics.result = GnssNeoM9nConfigReadNotReady;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBusy;
        return s_valget_diagnostics.result;
    }
    if (start_result == GnssNeoM9nAsyncStartTxError)
    {
        return GnssNeoM9nConfigReadTxError;
    }
    result = Gnss_WaitValget(instance, timeout_ms);
    if (s_valget_wait_active != 0U)
    {
        if (result == GnssNeoM9nConfigReadTimeout)
        {
            Gnss_ValgetAsyncCancel(instance, result,
                GnssNeoM9nTransactionDetailTimeout);
        }
        (void)Gnss_ValgetAsyncPoll(instance, NULL, NULL, &result);
    }
    return result;
}

static GnssNeoM9nConfigReadResult GnssNeoM9n_SendValget(uint8_t instance,
    const uint32_t *keys, uint8_t count, uint32_t timeout_ms)
{
    return Gnss_ValgetLayerRead(instance, keys, count, timeout_ms, GNSS_VALGET_LAYER_RAM);
}

static int Gnss_ValsetRawSend(uint8_t instance, uint8_t layers, const GnssCfgItem_t *items, uint8_t count, uint32_t timeout_ms)
{
    if (items == NULL) { return -1; }
    SILVERSTAR_ASSERT_OBJECT(items, GnssCfgItem_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t payload[GNSS_UBX_TX_MAX_PAYLOAD_LEN];
    uint16_t payload_len = GNSS_VALSET_HEADER_LEN;
    uint8_t i;

    if ((items == NULL) ||
        (count == 0U) ||
        ((layers & GNSS_CFG_LAYER_ALL) == 0U) ||
        ((layers & (uint8_t)(~GNSS_CFG_LAYER_ALL)) != 0U))
    {
        return -1;
    }

    payload[0] = 0x00U;
    payload[1] = layers;
    payload[2] = GNSS_VALSET_TRANSACTION_NONE;
    payload[3] = 0x00U;

    for (i = 0U; i < count; i++)
    {
        if ((items[i].value_len != GNSS_CFG_ITEM_TYPE_L) &&
            (items[i].value_len != GNSS_CFG_ITEM_TYPE_U2) &&
            (items[i].value_len != GNSS_CFG_ITEM_TYPE_U4))
        {
            return -1;
        }

        if ((uint16_t)(payload_len + 4U + items[i].value_len) > GNSS_UBX_TX_MAX_PAYLOAD_LEN)
        {
            return -1;
        }

        Gnss_WriteU32Le(&payload[payload_len], items[i].key);
        payload_len = (uint16_t)(payload_len + 4U);

        if (items[i].value_len == GNSS_CFG_ITEM_TYPE_U4)
        {
            Gnss_WriteU32Le(&payload[payload_len],
                            (uint32_t)items[i].value);
        }
        else if (items[i].value_len == GNSS_CFG_ITEM_TYPE_U2)
        {
            Gnss_WriteU16Le(&payload[payload_len], (uint16_t)items[i].value);
        }
        else
        {
            payload[payload_len] = (uint8_t)items[i].value;
        }

        payload_len = (uint16_t)(payload_len + items[i].value_len);
    }

    Gnss_ClearAckWait(instance, GNSS_UBX_CFG_CLASS, GNSS_UBX_CFG_VALSET_ID);

    if (GnssNeoM9n_SendUbx(instance, GNSS_UBX_CFG_CLASS, GNSS_UBX_CFG_VALSET_ID, payload, payload_len) != 0)
    {
        return -1;
    }

    return Gnss_WaitAck(instance, GNSS_UBX_CFG_CLASS, GNSS_UBX_CFG_VALSET_ID, timeout_ms);
}

/* Compare and verify one exact key and layer. NVM is never blindly retried. */
static int Gnss_ConfigItemRead(uint8_t instance, const GnssCfgItem_t *item,
    uint8_t layer, uint32_t timeout_ms, uint8_t *matched)
{
    if ((item == NULL) || (matched == NULL)) { return -1; }
    SILVERSTAR_ASSERT_OBJECT(item, GnssCfgItem_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    *matched = 0U;
    if (Gnss_ValgetLayerRead(instance, &item->key, 1U, timeout_ms, layer) !=
        GnssNeoM9nConfigReadResponseOk) { return -2; }
    if ((s_valget_cache_count != 1U) || (s_valget_cache[0].key != item->key) ||
        (s_valget_cache[0].value_len != item->value_len)) { return -4; }
    *matched = (s_valget_cache[0].value == item->value) ? 1U : 0U;
    return 0;
}

static int Gnss_ConfigItemApply(uint8_t instance, const GnssCfgItem_t *item,
    uint8_t layer, uint32_t timeout_ms)
{
    uint8_t matched;
    int result;
    if (item == NULL) { return -1; }
    SILVERSTAR_ASSERT_OBJECT(item, GnssCfgItem_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Gnss_ConfigItemRead(instance, item, layer, timeout_ms, &matched);
    if ((result != 0) || (matched != 0U)) { return result; }
    result = Gnss_ValsetRawSend(instance, (uint8_t)(1U << layer), item, 1U, timeout_ms);
    if ((layer == GNSS_VALGET_LAYER_RAM) && (item->key == GNSS_CFG_UART1_BAUDRATE))
    {
        /* The baud ACK can be emitted at either baud. Readback at the new baud is authoritative. */
        if ((result != 0) && (result != -2)) { return result; }
        if (PlatformUart_BaudSet(NeoM9nResource_UartGet(instance), (uint32_t)item->value) != PLATFORM_OK)
        { return -1; }
        PlatformTime_DelayMs(GNSS_UART_CONFIG_SETTLE_MS);
    }
    else if (result != 0) { return result; }
    result = Gnss_ConfigItemRead(instance, item, layer, timeout_ms, &matched);
    if (result != 0) { return result; }
    return (matched != 0U) ? 0 : -4;
}

static int GnssNeoM9n_SendValset(uint8_t instance, uint8_t layers,
    const GnssCfgItem_t *items, uint8_t count, uint32_t timeout_ms)
{
    uint8_t layer;
    uint8_t index;
    int result;
    if ((items == NULL) || (count == 0U) || (count > GNSS_CFG_CACHE_MAX_ITEMS) ||
        (layers == 0U) || ((layers & (uint8_t)~GNSS_CFG_LAYER_ALL) != 0U)) { return -1; }
    SILVERSTAR_ASSERT_OBJECT(items, GnssCfgItem_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (GnssNeoM9n_Identify(instance) != GnssNeoM9nIdentifyOk) { return -4; }
    for (layer = GNSS_VALGET_LAYER_RAM; layer <= GNSS_VALGET_LAYER_FLASH; layer++)
    {
        if ((layers & (uint8_t)(1U << layer)) == 0U) { continue; }
        for (index = 0U; index < count; index++)
        {
            result = Gnss_ConfigItemApply(instance, &items[index], layer, timeout_ms);
            if (result != 0) { return result; }
        }
    }
    return 0;
}

static void Gnss_ParseNavPvt(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    const uint8_t *p = s_parser.payload;

    s_data.iTOW = Gnss_ReadU32Le(&p[0]);
    s_data.year = Gnss_ReadU16Le(&p[4]);
    s_data.month = p[6];
    s_data.day = p[7];
    s_data.hour = p[8];
    s_data.min = p[9];
    s_data.sec = p[10];
    s_data.validDate = (uint8_t)(p[11] & 0x01U);
    s_data.validTime = (uint8_t)((p[11] & 0x02U) ? 1U : 0U);
    s_data.fixType = p[20];
    s_data.gnssFixOK = (uint8_t)(p[21] & 0x01U);
    s_data.numSV = p[23];
    s_data.lon = Gnss_ReadI32Le(&p[24]);
    s_data.lat = Gnss_ReadI32Le(&p[28]);
    s_data.height = Gnss_ReadI32Le(&p[32]);
    s_data.hMSL = Gnss_ReadI32Le(&p[36]);
    s_data.hAcc = Gnss_ReadU32Le(&p[40]);
    s_data.vAcc = Gnss_ReadU32Le(&p[44]);
    s_data.velN = Gnss_ReadI32Le(&p[48]);
    s_data.velE = Gnss_ReadI32Le(&p[52]);
    s_data.velD = Gnss_ReadI32Le(&p[56]);
    s_data.gSpeed = Gnss_ReadI32Le(&p[60]);
    s_data.headMot = Gnss_ReadI32Le(&p[64]);
    s_data.sAcc = Gnss_ReadU32Le(&p[68]);
    s_data.headAcc = Gnss_ReadU32Le(&p[72]);
    s_data.pDOP = Gnss_ReadU16Le(&p[76]);
    s_data.lastUpdate_ms = now_ms;
    s_data.lastUpdate_us = PlatformTime_Us();
    s_status.pvt_seen = 1U;
    s_status.ubx_pvt_count++;

    Gnss_UpdateStatus(instance, now_ms);
    /* Publish the sequence only after every field and availability flag is complete. */
    s_data.pvtSequence++;
}

static void Gnss_NavSatPayloadStore(uint8_t instance, const uint8_t *payload, uint8_t count)
{
    uint16_t offset;
    uint32_t cno_sum = 0U;
    uint32_t quality_sum = 0U;
    uint8_t index;
    uint8_t used_count = 0U;
    uint8_t maximum_cno = 0U;

    if (payload == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(payload, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (index = 0U; index < count; index++)
    {
        uint8_t cno;
        uint32_t flags;

        offset = (uint16_t)(GNSS_UBX_NAV_SAT_HEADER_LEN +
            ((uint16_t)index * GNSS_UBX_NAV_SAT_BLOCK_LEN));
        cno = payload[offset + 2U];
        flags = Gnss_ReadU32Le(&payload[offset + 8U]);
        cno_sum += cno;
        quality_sum += flags & 0x07U;
        if (cno > maximum_cno) { maximum_cno = cno; }
        if ((flags & 0x08U) != 0U) { used_count++; }
    }
    s_satellite_diagnostics.timestamp_us = PlatformTime_Us();
    s_satellite_diagnostics.satellite_count = count;
    s_satellite_diagnostics.used_count = used_count;
    s_satellite_diagnostics.average_cno_dbhz = (count != 0U) ?
        (uint8_t)(cno_sum / count) : 0U;
    s_satellite_diagnostics.maximum_cno_dbhz = maximum_cno;
    s_satellite_diagnostics.average_quality = (count != 0U) ?
        (uint8_t)(quality_sum / count) : 0U;
    s_satellite_diagnostics.valid = 1U;
    s_satellite_diagnostics.read_result = GnssNeoM9nConfigReadResponseOk;
    s_satellite_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailResponseOk;
    s_satellite_diagnostics.sequence++;
}

static void Gnss_ParseNavSat(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    const uint8_t *payload = s_parser.payload;
    uint16_t expected_length;
    uint8_t count;

    s_satellite_diagnostics.timestamp_us = PlatformTime_Us();
    s_satellite_diagnostics.response_length = s_parser.payload_len;
    s_satellite_diagnostics.expected_class = GNSS_UBX_NAV_CLASS;
    s_satellite_diagnostics.expected_id = GNSS_UBX_NAV_SAT_ID;
    s_satellite_diagnostics.received_class = s_parser.msg_class;
    s_satellite_diagnostics.received_id = s_parser.msg_id;
    s_satellite_diagnostics.expected_ck_a = s_parser.ck_a;
    s_satellite_diagnostics.expected_ck_b = s_parser.ck_b;
    s_satellite_diagnostics.received_ck_a = s_parser.received_ck_a;
    s_satellite_diagnostics.received_ck_b = s_parser.received_ck_b;
    s_satellite_diagnostics.valid = 0U;
    s_satellite_diagnostics.read_result =
        GnssNeoM9nConfigReadMalformedResponse;
    if (s_parser.payload_len < GNSS_UBX_NAV_SAT_HEADER_LEN)
    {
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadLength;
        s_satellite_diagnostics.sequence++;
        return;
    }
    if (payload[4] != 0x01U)
    {
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadVersion;
        s_satellite_diagnostics.sequence++;
        return;
    }
    count = payload[5];
    if (count > GNSS_UBX_NAV_SAT_MAX_COUNT)
    {
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailCountOverflow;
        s_satellite_diagnostics.sequence++;
        return;
    }
    expected_length = (uint16_t)(GNSS_UBX_NAV_SAT_HEADER_LEN +
        ((uint16_t)count * GNSS_UBX_NAV_SAT_BLOCK_LEN));
    if (s_parser.payload_len != expected_length)
    {
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadLength;
        s_satellite_diagnostics.sequence++;
        return;
    }

    Gnss_NavSatPayloadStore(instance, payload, count);
}

static void Gnss_MonRfPayloadStore(uint8_t instance, const uint8_t *payload, uint8_t count)
{
    uint16_t offset;
    uint32_t noise_sum = 0U;
    uint32_t agc_sum = 0U;
    uint8_t index;
    uint8_t maximum_jamming_state = 0U;
    uint8_t maximum_cw_suppression = 0U;

    if (payload == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(payload, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (index = 0U; index < count; index++)
    {
        uint8_t jamming_state;
        uint8_t cw_suppression;

        offset = (uint16_t)(GNSS_UBX_MON_RF_HEADER_LEN +
            ((uint16_t)index * GNSS_UBX_MON_RF_BLOCK_LEN));
        noise_sum += Gnss_ReadU16Le(&payload[offset + 12U]);
        agc_sum += Gnss_ReadU16Le(&payload[offset + 14U]);
        jamming_state = payload[offset + 1U] & 0x03U;
        cw_suppression = payload[offset + 16U];
        if (jamming_state > maximum_jamming_state)
        { maximum_jamming_state = jamming_state; }
        if (cw_suppression > maximum_cw_suppression)
        { maximum_cw_suppression = cw_suppression; }
        if (index == 0U)
        {
            s_rf_diagnostics.antenna_status = payload[offset + 2U];
            s_rf_diagnostics.antenna_power = payload[offset + 3U];
        }
    }
    s_rf_diagnostics.timestamp_us = PlatformTime_Us();
    s_rf_diagnostics.rf_block_count = count;
    s_rf_diagnostics.noise_per_ms = (uint16_t)(noise_sum / count);
    s_rf_diagnostics.agc_count = (uint16_t)(agc_sum / count);
    s_rf_diagnostics.jamming_state = maximum_jamming_state;
    s_rf_diagnostics.cw_suppression = maximum_cw_suppression;
    s_rf_diagnostics.jamming_indicator = maximum_cw_suppression;
    s_rf_diagnostics.valid = 1U;
    s_rf_diagnostics.read_result = GnssNeoM9nConfigReadResponseOk;
    s_rf_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailResponseOk;
    s_rf_diagnostics.sequence++;
}

static void Gnss_ParseMonRf(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    const uint8_t *payload = s_parser.payload;
    uint16_t expected_length;
    uint8_t count;

    s_rf_diagnostics.timestamp_us = PlatformTime_Us();
    s_rf_diagnostics.response_length = s_parser.payload_len;
    s_rf_diagnostics.valid = 0U;
    s_rf_diagnostics.read_result =
        GnssNeoM9nConfigReadMalformedResponse;
    if (s_parser.payload_len < GNSS_UBX_MON_RF_HEADER_LEN)
    {
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadLength;
        s_rf_diagnostics.sequence++;
        return;
    }
    if (payload[0] != 0x00U)
    {
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadVersion;
        s_rf_diagnostics.sequence++;
        return;
    }
    count = payload[1];
    expected_length = (uint16_t)(GNSS_UBX_MON_RF_HEADER_LEN +
        ((uint16_t)count * GNSS_UBX_MON_RF_BLOCK_LEN));
    if ((count == 0U) || (s_parser.payload_len != expected_length))
    {
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadLength;
        s_rf_diagnostics.sequence++;
        return;
    }
    Gnss_MonRfPayloadStore(instance, payload, count);
}

static void Gnss_ParseAck(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_parser.payload_len == GNSS_UBX_ACK_LEN) &&
        (s_parser.payload[0] == GNSS_UBX_CFG_CLASS) &&
        ((s_parser.payload[1] == GNSS_UBX_CFG_VALSET_ID) ||
         (s_parser.payload[1] == GNSS_UBX_CFG_VALGET_ID)))
    {
        s_last_ack_class = s_parser.payload[0];
        s_last_ack_id = s_parser.payload[1];
        s_last_ack = (s_parser.msg_id == GNSS_UBX_ACK_ACK_ID) ?
                     GnssNeoM9nAckAck : GnssNeoM9nAckNak;
        s_config.last_ack = s_last_ack;
        if (s_last_ack == GnssNeoM9nAckAck)
        {
            s_status.ubx_ack_count++;
        }
        else
        {
            s_status.ubx_nak_count++;
        }
        if ((s_valget_wait_active != 0U) &&
            (s_parser.payload[1] == GNSS_UBX_CFG_VALGET_ID) &&
            (s_last_ack == GnssNeoM9nAckNak))
        {
            s_valget_diagnostics.result = GnssNeoM9nConfigReadNak;
            s_valget_diagnostics.detailed_result =
                GnssNeoM9nTransactionDetailNak;
            s_valget_diagnostics.nak_class = s_parser.payload[0];
            s_valget_diagnostics.nak_id = s_parser.payload[1];
            s_valget_diagnostics.received_class = s_parser.msg_class;
            s_valget_diagnostics.received_id = s_parser.msg_id;
            s_valget_diagnostics.response_length = s_parser.payload_len;
            s_valget_received = 1U;
        }
    }
}

static void Gnss_ValgetFailureSet(uint8_t instance, GnssNeoM9nTransactionDetail detail)
{
    s_valget_diagnostics.result = GnssNeoM9nConfigReadMalformedResponse;
    s_valget_diagnostics.detailed_result = detail;
    s_valget_received = 1U;
}

static uint8_t Gnss_ValgetHeaderValidate(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_parser.payload_len < GNSS_VALGET_HEADER_LEN)
    {
        Gnss_ValgetFailureSet(instance, GnssNeoM9nTransactionDetailBadLength);
        return 0U;
    }
    s_valget_diagnostics.response_version = s_parser.payload[0];
    if (s_parser.payload[0] != GNSS_VALGET_RESPONSE_VERSION)
    {
        Gnss_ValgetFailureSet(instance, GnssNeoM9nTransactionDetailBadVersion);
        return 0U;
    }
    if (s_parser.payload[1] != s_valget_layer)
    {
        Gnss_ValgetFailureSet(instance, GnssNeoM9nTransactionDetailBadLayer);
        return 0U;
    }
    if ((s_parser.payload[2] != 0x00U) ||
        (s_parser.payload[3] != 0x00U))
    {
        Gnss_ValgetFailureSet(instance, GnssNeoM9nTransactionDetailBadPosition);
        return 0U;
    }
    return 1U;
}

static uint8_t Gnss_ValgetKeyExpected(uint8_t instance, uint32_t key)
{
    uint8_t index;

    for (index = 0U; index < s_valget_expected_key_count; index++)
    {
        if (s_valget_expected_keys[index] == key) { return 1U; }
    }
    return 0U;
}

static uint64_t Gnss_ValgetValueGet(uint8_t instance, uint16_t index, uint8_t value_len)
{
    if (value_len == GNSS_CFG_ITEM_TYPE_U8)
    { return Gnss_ReadU64Le(&s_parser.payload[index]); }
    if (value_len == GNSS_CFG_ITEM_TYPE_U4)
    { return Gnss_ReadU32Le(&s_parser.payload[index]); }
    if (value_len == GNSS_CFG_ITEM_TYPE_U2)
    { return Gnss_ReadU16Le(&s_parser.payload[index]); }
    return s_parser.payload[index];
}

static uint8_t Gnss_ValgetItemsParse(uint8_t instance, uint16_t *final_index)
{
    uint16_t index = GNSS_VALGET_HEADER_LEN;
    uint32_t key;
    uint64_t value;
    uint8_t value_len;
    uint8_t item_count;

    if (final_index == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(final_index, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (item_count = 0U;
         item_count < GNSS_MAX_VALGET_ITEMS_PER_FRAME;
         item_count++)
    {
        if ((uint16_t)(index + 4U) > s_parser.payload_len) { break; }
        key = Gnss_ReadU32Le(&s_parser.payload[index]);
        index = (uint16_t)(index + 4U);
        if (Gnss_ValgetKeyExpected(instance, key) == 0U)
        {
            Gnss_ValgetFailureSet(instance, GnssNeoM9nTransactionDetailKeyMismatch);
            return 0U;
        }
        value_len = Gnss_ConfigKeyValueLen(key);
        if ((value_len == 0U) ||
            ((uint16_t)(index + value_len) > s_parser.payload_len))
        {
            Gnss_ValgetFailureSet(instance,
                GnssNeoM9nTransactionDetailValueLengthMismatch);
            return 0U;
        }
        value = Gnss_ValgetValueGet(instance, index, value_len);
        Gnss_ValgetStore(instance, key, value, value_len);
        index = (uint16_t)(index + value_len);
    }
    *final_index = index;
    return 1U;
}

static void Gnss_ParseValget(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint16_t idx;

    if (s_valget_wait_active == 0U) { return; }
    s_valget_diagnostics.response_length = s_parser.payload_len;
    s_valget_diagnostics.received_class = s_parser.msg_class;
    s_valget_diagnostics.received_id = s_parser.msg_id;
    if ((Gnss_ValgetHeaderValidate(instance) == 0U) ||
        (Gnss_ValgetItemsParse(instance, &idx) == 0U)) { return; }
    if ((idx != s_parser.payload_len) || (s_valget_cache_count == 0U))
    {
        s_valget_diagnostics.result =
            GnssNeoM9nConfigReadMalformedResponse;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailBadLength;
    }
    else
    {
        s_valget_diagnostics.result = GnssNeoM9nConfigReadResponseOk;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailResponseOk;
    }
    s_valget_received = 1U;
}

static void Gnss_UpdateStatus(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_status, GnssNeoM9nStatusSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint32_t age_ms = now_ms - s_data.lastUpdate_ms;
    uint8_t ground_speed_usable;

    s_data.online = ((s_data.lastUpdate_ms != 0U) && (age_ms <= GNSS_TIMEOUT_MS)) ? 1U : 0U;
    s_data.hasValidFix = ((s_data.online != 0U) &&
                          (s_data.gnssFixOK != 0U) &&
                          (s_data.fixType >= 2U)) ? 1U : 0U;
    s_data.positionUsable = ((s_data.online != 0U) &&
                             (s_data.gnssFixOK != 0U) &&
                             ((s_data.fixType == 3U) ||
                              (s_data.fixType == 4U)) &&
                             (s_data.numSV >= GNSS_NAV_MIN_SV) &&
                             (s_data.hAcc <= GNSS_NAV_MAX_HACC_MM) &&
                             (s_data.vAcc <= GNSS_NAV_MAX_VACC_MM) &&
                             (age_ms <= GNSS_NAV_MAX_AGE_MS)) ? 1U : 0U;
    s_data.velocityUsable = ((s_data.online != 0U) &&
                             (s_data.gnssFixOK != 0U) &&
                             ((s_data.fixType == 3U) ||
                              (s_data.fixType == 4U)) &&
                             (s_data.numSV >= GNSS_NAV_MIN_SV) &&
                             (s_data.sAcc <= GNSS_NAV_MAX_SACC_MMPS) &&
                             (age_ms <= GNSS_NAV_MAX_AGE_MS)) ? 1U : 0U;
    ground_speed_usable = ((s_data.gSpeed > 0) &&
                           ((uint32_t)s_data.gSpeed >= GNSS_COURSE_MIN_GSPEED_MMPS)) ? 1U : 0U;
    s_data.courseUsable = ((s_data.velocityUsable != 0U) &&
                           (ground_speed_usable != 0U) &&
                           (s_data.headAcc <= GNSS_COURSE_MAX_HEADACC_E5) &&
                           (age_ms <= GNSS_NAV_MAX_AGE_MS)) ? 1U : 0U;
}

static void Gnss_ChecksumErrorHandle(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_status.ubx_checksum_error_count++;
    s_parser_resync_count++;
    if ((s_valget_wait_active != 0U) &&
        (s_parser.msg_class == GNSS_UBX_CFG_CLASS) &&
        (s_parser.msg_id == GNSS_UBX_CFG_VALGET_ID))
    {
        s_valget_diagnostics.result = GnssNeoM9nConfigReadChecksumError;
        s_valget_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailChecksumError;
        s_valget_diagnostics.received_class = s_parser.msg_class;
        s_valget_diagnostics.received_id = s_parser.msg_id;
        s_valget_diagnostics.response_length = s_parser.payload_len;
        s_valget_received = 1U;
    }
    else if ((s_parser.msg_class == GNSS_UBX_NAV_CLASS) &&
             (s_parser.msg_id == GNSS_UBX_NAV_SAT_ID))
    {
        s_satellite_diagnostics.timestamp_us = PlatformTime_Us();
        s_satellite_diagnostics.valid = 0U;
        s_satellite_diagnostics.read_result =
            GnssNeoM9nConfigReadChecksumError;
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailChecksumError;
        s_satellite_diagnostics.response_length = s_parser.payload_len;
        s_satellite_diagnostics.expected_class = GNSS_UBX_NAV_CLASS;
        s_satellite_diagnostics.expected_id = GNSS_UBX_NAV_SAT_ID;
        s_satellite_diagnostics.received_class = s_parser.msg_class;
        s_satellite_diagnostics.received_id = s_parser.msg_id;
        s_satellite_diagnostics.expected_ck_a = s_parser.ck_a;
        s_satellite_diagnostics.expected_ck_b = s_parser.ck_b;
        s_satellite_diagnostics.received_ck_a = s_parser.received_ck_a;
        s_satellite_diagnostics.received_ck_b = s_parser.received_ck_b;
        s_satellite_diagnostics.sequence++;
    }
    else if ((s_parser.msg_class == GNSS_UBX_MON_CLASS) &&
             (s_parser.msg_id == GNSS_UBX_MON_RF_ID))
    {
        s_rf_diagnostics.timestamp_us = PlatformTime_Us();
        s_rf_diagnostics.valid = 0U;
        s_rf_diagnostics.read_result = GnssNeoM9nConfigReadChecksumError;
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailChecksumError;
        s_rf_diagnostics.response_length = s_parser.payload_len;
        s_rf_diagnostics.sequence++;
    }
}

static void Gnss_ParseSync1(uint8_t instance, uint8_t byte, uint32_t now_ms)
{
    if (byte == GNSS_UBX_SYNC1)
    {
        Gnss_NmeaReset(instance);
        s_parser.state = GnssUbxStateSync2;
    }
    else if (Gnss_ParseNmeaByte(instance, byte, now_ms) == 0U)
    {
        Gnss_UpdateUnknownStats(instance, now_ms);
    }
}

static void Gnss_ParseSync2(uint8_t instance, uint8_t byte, uint32_t now_ms)
{
    if (byte == GNSS_UBX_SYNC2)
    {
        s_parser.ck_a = 0U;
        s_parser.ck_b = 0U;
        s_parser.state = GnssUbxStateClass;
        return;
    }
    Gnss_ParserReset(instance);
    if (byte == GNSS_UBX_SYNC1)
    {
        s_parser.state = GnssUbxStateSync2;
    }
    else if (Gnss_ParseNmeaByte(instance, byte, now_ms) == 0U)
    {
        Gnss_UpdateUnknownStats(instance, now_ms);
    }
}

static void Gnss_ValgetBadLengthSet(uint8_t instance)
{
    if ((s_valget_wait_active == 0U) ||
        (s_parser.msg_class != GNSS_UBX_CFG_CLASS) ||
        (s_parser.msg_id != GNSS_UBX_CFG_VALGET_ID))
    {
        return;
    }
    s_valget_diagnostics.result = GnssNeoM9nConfigReadMalformedResponse;
    s_valget_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailBadLength;
    s_valget_diagnostics.received_class = s_parser.msg_class;
    s_valget_diagnostics.received_id = s_parser.msg_id;
    s_valget_diagnostics.response_length = s_parser.payload_len;
    s_valget_received = 1U;
}

static void Gnss_ParseLengthMsb(uint8_t instance, uint8_t byte)
{
    s_parser.payload_len |= ((uint16_t)byte << 8);
    Gnss_ChecksumAdd(instance, byte);
    s_parser.payload_idx = 0U;
    if (s_parser.payload_len > GNSS_UBX_MAX_PAYLOAD_LEN)
    {
        s_status.ubx_checksum_error_count++;
        Gnss_ValgetBadLengthSet(instance);
        Gnss_ParserReset(instance);
    }
    else if (s_parser.payload_len == 0U)
    {
        s_parser.state = GnssUbxStateCkA;
    }
    else
    {
        s_parser.state = GnssUbxStatePayload;
    }
}

static void Gnss_ParsePayloadByte(uint8_t instance, uint8_t byte)
{
    s_parser.payload[s_parser.payload_idx] = byte;
    s_parser.payload_idx++;
    Gnss_ChecksumAdd(instance, byte);
    if (s_parser.payload_idx >= s_parser.payload_len)
    {
        s_parser.state = GnssUbxStateCkA;
    }
}

static void Gnss_MonVerParse(uint8_t instance)
{
    uint16_t offset;
    uint8_t model = 0U;
    uint8_t protocol = 0U;
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_parser.payload_len < 40U) || (((s_parser.payload_len - 40U) % 30U) != 0U)) { return; }
    for (offset = 40U; (offset + 30U) <= s_parser.payload_len; offset = (uint16_t)(offset + 30U))
    {
        if (memcmp(&s_parser.payload[offset], "MOD=NEO-M9N", 12U) == 0) { model = 1U; }
        if (memcmp(&s_parser.payload[offset], "PROTVER=27.", 11U) == 0) { protocol = 1U; }
    }
    s_contexts[instance].identity_seen = 1U;
    s_contexts[instance].identity_verified = (uint8_t)(model & protocol);
}

static GnssNeoM9nIdentifyResult Gnss_IdentityPoll(uint8_t instance)
{
    uint32_t poll;
    if (GnssNeoM9n_SendUbx(instance, GNSS_UBX_MON_CLASS, 0x04U, NULL, 0U) != 0)
    { return GnssNeoM9nIdentifyIoError; }
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (poll = 0U; poll < 200U; poll++)
    {
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        if (s_contexts[instance].identity_seen != 0U)
        { return (s_contexts[instance].identity_verified != 0U) ? GnssNeoM9nIdentifyOk : GnssNeoM9nIdentifyWrongModel; }
        PlatformTime_DelayMs(1U);
    }
    return GnssNeoM9nIdentifyTimeout;
}

GnssNeoM9nIdentifyResult GnssNeoM9n_Identify(uint8_t instance)
{
    uint32_t candidates[] =
    {
        GNSS_DEFAULT_BAUDRATE, GNSS_FACTORY_BAUDRATE,
        GNSS_UART_BAUD_4800, GNSS_UART_BAUD_9600,
        GNSS_UART_BAUD_19200, GNSS_UART_BAUD_38400,
        GNSS_UART_BAUD_57600, GNSS_UART_BAUD_115200,
        GNSS_UART_BAUD_230400, GNSS_UART_BAUD_460800,
        GNSS_UART_BAUD_576000, GNSS_UART_BAUD_921600
    };
    uint8_t index;
    uint8_t prior;
    GnssNeoM9nIdentifyResult result;
    if (instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) { return GnssNeoM9nIdentifyIoError; }
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_contexts[instance].identity_verified != 0U) { return GnssNeoM9nIdentifyOk; }
    candidates[0] = Gnss_UartBaudrateGet(instance);
    for (index = 0U; index < sizeof(candidates) / sizeof(candidates[0]); index++)
    {
        for (prior = 0U; prior < index; prior++)
        { if (candidates[prior] == candidates[index]) { break; } }
        if (prior < index) { continue; }
        if (PlatformUart_BaudSet(NeoM9nResource_UartGet(instance), candidates[index]) != PLATFORM_OK)
        { return GnssNeoM9nIdentifyIoError; }
        Gnss_ParserReset(instance);
        s_contexts[instance].identity_seen = 0U;
        result = Gnss_IdentityPoll(instance);
        if (result != GnssNeoM9nIdentifyTimeout) { return result; }
    }
    return GnssNeoM9nIdentifyTimeout;
}

GnssNeoM9nProbeStartResult GnssNeoM9n_ProbeStart(
    uint8_t instance, uint32_t baudrate)
{
    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) ||
        (s_contexts[instance].initialized == 0U))
    { return GnssNeoM9nProbeStartResult_NotReady; }
    if (PlatformUart_BaudSet(NeoM9nResource_UartGet(instance), baudrate) !=
        PLATFORM_OK)
    { return GnssNeoM9nProbeStartResult_IoError; }
    Gnss_ParserReset(instance);
    Gnss_NmeaReset(instance);
    s_contexts[instance].identity_seen = 0U;
    s_contexts[instance].identity_verified = 0U;
    s_contexts[instance].probe_phase = GnssProbePhasePassive;
    s_contexts[instance].probe_phase_started_ms = PlatformTime_Ms();
    s_contexts[instance].probe_nmea_baseline = s_status.nmea_checksum_ok_count;
    s_contexts[instance].probe_baudrate = baudrate;
    s_contexts[instance].item_read_active = 0U;
    s_contexts[instance].item_write_active = 0U;
    return GnssNeoM9nProbeStartResult_Ok;
}

static PlatformResult Gnss_ProbeMonVerSend(uint8_t instance)
{
    static const uint8_t request[8] =
    {
        GNSS_UBX_SYNC1, GNSS_UBX_SYNC2, GNSS_UBX_MON_CLASS,
        0x04U, 0x00U, 0x00U, 0x0EU, 0x34U
    };
    return PlatformUart_WriteFrameAsync(NeoM9nResource_UartGet(instance),
        request, sizeof(request), PLATFORM_UART_TX_PRIORITY);
}

/* PUBX,41 is specified by the u-blox M9 interface description. It changes
 * only volatile UART protocol settings here; the normal VALGET/VALSET path
 * later applies the project baud and verifies the exact M9N identity. */
static PlatformResult Gnss_ProbePubxSend(uint8_t instance)
{
    static const char prefix[] = "PUBX,41,1,0007,0003,";
    static const char suffix[] = ",0";
    static const char hex[] = "0123456789ABCDEF";
    uint8_t frame[GNSS_PUBX_FRAME_MAX_LEN];
    uint8_t digits[10U];
    uint8_t digit_count = 0U;
    uint16_t length = 0U;
    uint16_t index;
    uint32_t baudrate = s_contexts[instance].probe_baudrate;
    uint8_t checksum = 0U;

    frame[length++] = (uint8_t)'$';
    for (index = 0U; index < sizeof(prefix) - 1U; index++)
    { frame[length++] = (uint8_t)prefix[index]; }
    do
    {
        digits[digit_count++] = (uint8_t)('0' + (baudrate % 10U));
        baudrate /= 10U;
    } while ((baudrate != 0U) && (digit_count < sizeof(digits)));
    while (digit_count != 0U)
    { frame[length++] = digits[--digit_count]; }
    for (index = 0U; index < sizeof(suffix) - 1U; index++)
    { frame[length++] = (uint8_t)suffix[index]; }
    for (index = 1U; index < length; index++) { checksum ^= frame[index]; }
    frame[length++] = (uint8_t)'*';
    frame[length++] = (uint8_t)hex[checksum >> 4U];
    frame[length++] = (uint8_t)hex[checksum & 0x0FU];
    frame[length++] = (uint8_t)'\r';
    frame[length++] = (uint8_t)'\n';
    return PlatformUart_WriteFrameAsync(NeoM9nResource_UartGet(instance),
        frame, length, PLATFORM_UART_TX_PRIORITY);
}

GnssNeoM9nProbePollResult GnssNeoM9n_ProbePoll(uint8_t instance)
{
    uint32_t now_ms;
    PlatformResult result;
    GnssProbePhase phase;

    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) ||
        (s_contexts[instance].initialized == 0U))
    { return GnssNeoM9nProbePollResult_NotReady; }
    now_ms = PlatformTime_Ms();
    (void)GnssNeoM9n_Process(instance, now_ms);
    phase = s_contexts[instance].probe_phase;
    if (s_contexts[instance].identity_seen != 0U)
    {
        s_contexts[instance].probe_phase = GnssProbePhaseComplete;
        return (s_contexts[instance].identity_verified != 0U) ?
            GnssNeoM9nProbePollResult_Identified :
            GnssNeoM9nProbePollResult_WrongModel;
    }
    if ((phase == GnssProbePhasePassive) &&
        ((uint32_t)(now_ms - s_contexts[instance].probe_phase_started_ms) >=
            GNSS_PROBE_PASSIVE_MS))
    { s_contexts[instance].probe_phase = GnssProbePhaseMonRequest; }
    else if ((phase == GnssProbePhaseMonResponse) &&
        ((uint32_t)(now_ms - s_contexts[instance].probe_phase_started_ms) >=
            GNSS_PROBE_UBX_WAIT_MS))
    {
        if ((uint32_t)(s_status.nmea_checksum_ok_count -
                s_contexts[instance].probe_nmea_baseline) <
            GNSS_PROBE_VALID_NMEA_MIN)
        { return GnssNeoM9nProbePollResult_WrongModel; }
        s_contexts[instance].probe_phase = GnssProbePhasePubxRequest;
    }
    else if ((phase == GnssProbePhasePubxSettle) &&
        ((uint32_t)(now_ms - s_contexts[instance].probe_phase_started_ms) >=
            GNSS_PROBE_RESCUE_SETTLE_MS))
    { s_contexts[instance].probe_phase = GnssProbePhaseRescueMonRequest; }
    else if ((phase == GnssProbePhaseRescueMonResponse) &&
        ((uint32_t)(now_ms - s_contexts[instance].probe_phase_started_ms) >=
            GNSS_PROBE_UBX_WAIT_MS))
    { return GnssNeoM9nProbePollResult_WrongModel; }

    phase = s_contexts[instance].probe_phase;
    if ((phase == GnssProbePhaseMonRequest) ||
        (phase == GnssProbePhaseRescueMonRequest))
    {
        result = Gnss_ProbeMonVerSend(instance);
        if (result == PLATFORM_BUSY) { return GnssNeoM9nProbePollResult_Pending; }
        if (result != PLATFORM_OK) { return GnssNeoM9nProbePollResult_WrongModel; }
        s_contexts[instance].probe_phase =
            (phase == GnssProbePhaseMonRequest) ?
                GnssProbePhaseMonResponse : GnssProbePhaseRescueMonResponse;
        s_contexts[instance].probe_phase_started_ms = now_ms;
    }
    else if (phase == GnssProbePhasePubxRequest)
    {
        result = Gnss_ProbePubxSend(instance);
        if (result == PLATFORM_BUSY) { return GnssNeoM9nProbePollResult_Pending; }
        if (result != PLATFORM_OK) { return GnssNeoM9nProbePollResult_WrongModel; }
        s_contexts[instance].probe_phase = GnssProbePhasePubxSettle;
        s_contexts[instance].probe_phase_started_ms = now_ms;
    }
    return GnssNeoM9nProbePollResult_Pending;
}

static void Gnss_ParsedFrameDispatch(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    Gnss_UpdateUbxStats(instance, now_ms);
    if ((s_parser.msg_class == GNSS_UBX_MON_CLASS) && (s_parser.msg_id == 0x04U))
    { Gnss_MonVerParse(instance); return; }
    if ((s_parser.msg_class == GNSS_UBX_NAV_CLASS) &&
        (s_parser.msg_id == GNSS_UBX_NAV_PVT_ID) &&
        (s_parser.payload_len == GNSS_UBX_NAV_PVT_LEN))
    {
        Gnss_ParseNavPvt(instance, now_ms);
    }
    else if ((s_parser.msg_class == GNSS_UBX_NAV_CLASS) &&
             (s_parser.msg_id == GNSS_UBX_NAV_SAT_ID))
    {
        Gnss_ParseNavSat(instance);
    }
    else if ((s_parser.msg_class == GNSS_UBX_MON_CLASS) &&
             (s_parser.msg_id == GNSS_UBX_MON_RF_ID))
    {
        Gnss_ParseMonRf(instance);
    }
    else if ((s_parser.msg_class == GNSS_UBX_ACK_CLASS) &&
             ((s_parser.msg_id == GNSS_UBX_ACK_ACK_ID) ||
              (s_parser.msg_id == GNSS_UBX_ACK_NAK_ID)) &&
             (s_parser.payload_len == GNSS_UBX_ACK_LEN))
    {
        Gnss_ParseAck(instance);
    }
    else if ((s_parser.msg_class == GNSS_UBX_CFG_CLASS) &&
             (s_parser.msg_id == GNSS_UBX_CFG_VALGET_ID))
    {
        Gnss_ParseValget(instance);
    }
}

static void Gnss_ParseChecksumB(uint8_t instance, uint8_t byte, uint32_t now_ms)
{
    s_parser.received_ck_b = byte;
    if ((s_parser.received_ck_a == s_parser.ck_a) &&
        (s_parser.received_ck_b == s_parser.ck_b))
    {
        Gnss_ParsedFrameDispatch(instance, now_ms);
    }
    else
    {
        Gnss_ChecksumErrorHandle(instance);
    }
    Gnss_ParserReset(instance);
}

static void Gnss_ParseByte(uint8_t instance, uint8_t byte, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_status.rx_bytes++;
    s_status.last_rx_ms = now_ms;
    switch (s_parser.state)
    {
    case GnssUbxStateSync1:
        Gnss_ParseSync1(instance, byte, now_ms);
        break;
    case GnssUbxStateSync2:
        Gnss_ParseSync2(instance, byte, now_ms);
        break;
    case GnssUbxStateClass:
        s_parser.msg_class = byte;
        Gnss_ChecksumAdd(instance, byte);
        s_parser.state = GnssUbxStateId;
        break;
    case GnssUbxStateId:
        s_parser.msg_id = byte;
        Gnss_ChecksumAdd(instance, byte);
        s_parser.state = GnssUbxStateLen1;
        break;
    case GnssUbxStateLen1:
        s_parser.payload_len = byte;
        Gnss_ChecksumAdd(instance, byte);
        s_parser.state = GnssUbxStateLen2;
        break;
    case GnssUbxStateLen2:
        Gnss_ParseLengthMsb(instance, byte);
        break;
    case GnssUbxStatePayload:
        Gnss_ParsePayloadByte(instance, byte);
        break;
    case GnssUbxStateCkA:
        s_parser.received_ck_a = byte;
        s_parser.state = GnssUbxStateCkB;
        break;
    case GnssUbxStateCkB:
        Gnss_ParseChecksumB(instance, byte, now_ms);
        break;
    default:
        Gnss_ParserReset(instance);
        break;
    }
}

int GnssNeoM9n_ApplyDefaultConfig(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    GnssNeoM9nData data;
    uint32_t baseline_sequence = 0U;
    uint64_t signal_complete_us;
    int result;

    result = GnssNeoM9n_ConfigUartBaudrate(instance,
        GNSS_CFG_LAYER_PERSISTENT_DEFAULT, GNSS_DEFAULT_BAUDRATE);
    if (result != 0) { return result; }
    result = GnssNeoM9n_WaitUartConfigSettle(instance,
        GNSS_UART_CONFIG_SETTLE_MS, GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS);
    if (result != 0) { return result; }
    result = GnssNeoM9n_ConfigOutputProtocol(instance, GNSS_CFG_LAYER_PERSISTENT_DEFAULT,
                                             GnssOutputProtocolUbxOnly);
    if (result != 0)
    {
        return result;
    }

    result = GnssNeoM9n_ConfigNavPvtOutput(instance, GNSS_CFG_LAYER_PERSISTENT_DEFAULT, 1U);
    if (result != 0)
    {
        return result;
    }

    result = GnssNeoM9n_ConfigNavRate(instance, GNSS_CFG_LAYER_PERSISTENT_DEFAULT,
                                      GNSS_TARGET_RATE_HZ);
    if (result != 0)
    {
        return result;
    }

    result = GnssNeoM9n_ConfigDynamicModel(instance, GNSS_CFG_LAYER_PERSISTENT_DEFAULT,
                                           GNSS_TARGET_DYNMODEL);
    if (result != 0)
    {
        return result;
    }

    (void)GnssNeoM9n_GetData(instance, &data);
    baseline_sequence = data.pvtSequence;
    result = GnssNeoM9n_ConfigSignalsGpsBdsGal(instance,
        GNSS_CFG_LAYER_PERSISTENT_DEFAULT);
    if (result != 0) { return result; }
    signal_complete_us = PlatformTime_Us();
    return GnssNeoM9n_WaitForNewNavPvt(instance,
        baseline_sequence, signal_complete_us,
        GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS);
}

static void Gnss_DiagnosticsResetLocked(uint8_t instance)
{
    (void)memset(&s_valget_diagnostics, 0, sizeof(s_valget_diagnostics));
    (void)memset(&s_satellite_diagnostics, 0,
                 sizeof(s_satellite_diagnostics));
    (void)memset(&s_rf_diagnostics, 0, sizeof(s_rf_diagnostics));
    s_satellite_diagnostics.read_result = GnssNeoM9nConfigReadNotReady;
    s_satellite_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailNotReady;
    s_rf_diagnostics.read_result = GnssNeoM9nConfigReadNotReady;
    s_rf_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailNotReady;
}

static void Gnss_TransactionStateResetLocked(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(&s_config_async, 0, sizeof(s_config_async));
    (void)memset(s_config_cache, 0, sizeof(s_config_cache));
    s_config_cache_count = 0U;
    s_contexts[instance].identity_seen = 0U;
    s_contexts[instance].identity_verified = 0U;
    s_contexts[instance].probe_phase = GnssProbePhaseComplete;
    s_valget_layer = GNSS_VALGET_LAYER_RAM;
    s_uart_baud_changed = 0U;
    s_uart_baseline_ubx_frames = 0U;
    s_parser_resync_count = 0U;
    s_transaction_discontinuity = 0U;
    s_valget_wait_active = 0U;
    s_valget_received = 0U;
    s_satellite_wait_active = 0U;
    s_rf_wait_active = 0U;
    s_satellite_wait_sequence = 0U;
    s_rf_wait_sequence = 0U;
    s_last_ack = GnssNeoM9nAckNone;
    s_last_ack_class = 0U;
    s_last_ack_id = 0U;
}

static void Gnss_ConfigDefaultsSetLocked(uint8_t instance)
{
    s_config.baudrate = GNSS_DEFAULT_BAUDRATE;
    s_config.rate_hz = GNSS_DEFAULT_RATE_HZ;
    s_config.dynamic_model = GNSS_TARGET_DYNMODEL;
    s_config.constellations_mask = GNSS_CONSTELLATION_GPS |
                                   GNSS_CONSTELLATION_GALILEO |
                                   GNSS_CONSTELLATION_BDS;
    s_config.protocol_in = 0x07U;
    s_config.protocol_out = 0x02U;
    s_config.nav_pvt_rate = 0U;
    s_config.nav_pvt_known = 1U;
    s_config.save_cache_count = 0U;
    s_config.read_layer = GnssNeoM9nPersistNone;
    s_config.last_write_layers = GnssNeoM9nPersistNone;
    s_config.last_ack = GnssNeoM9nAckNone;
}

static void Gnss_RuntimeStateResetLocked(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_data, GnssNeoM9nData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(&s_data, 0, sizeof(s_data));
    (void)memset(&s_published_data, 0, sizeof(s_published_data));
    (void)memset(&s_config, 0, sizeof(s_config));
    (void)memset(&s_status, 0, sizeof(s_status));
    Gnss_DiagnosticsResetLocked(instance);
    Gnss_TransactionStateResetLocked(instance);
    Gnss_ConfigDefaultsSetLocked(instance);
    Gnss_ParserReset(instance);
    Gnss_NmeaReset(instance);
    s_initialized = 1U;
    s_status.initialized = s_initialized;
    s_status.uart_baudrate = Gnss_UartBaudrateGet(instance);
}

GnssNeoM9nInitResult GnssNeoM9n_Init(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_data, GnssNeoM9nData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    PlatformUartDiagnostics port_diagnostics;
    uint32_t primask;

    primask = Gnss_IrqLock();
    Gnss_RuntimeStateResetLocked(instance);
    Gnss_IrqUnlock(primask);

    if (PlatformUart_Init(NeoM9nResource_UartGet(instance)) != PLATFORM_OK)
    {
        s_initialized = 0U;
        s_status.initialized = 0U;
        return GnssNeoM9n_InitUartError;
    }
    (void)PlatformUart_DiagnosticsGet(NeoM9nResource_UartGet(instance), &port_diagnostics);
    s_port_discontinuity_sequence =
        port_diagnostics.rx_discontinuity_count;
    //仅修改波特率时打开该注释，单片机波特率需要同步修改
    return GnssNeoM9n_InitOk;
}

GnssNeoM9nUpdateResult GnssNeoM9n_Process(uint8_t instance, uint32_t now_ms)
{
    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    PlatformUartDiagnostics port_diagnostics;
    uint8_t byte;
    uint8_t processed = 0U;
    uint32_t primask;
    uint16_t byte_count;

    if (s_initialized == 0U)
    {
        return GnssNeoM9n_UpdateNoData;
    }

    (void)PlatformUart_DiagnosticsGet(NeoM9nResource_UartGet(instance), &port_diagnostics);
    if (port_diagnostics.rx_discontinuity_count !=
        s_port_discontinuity_sequence)
    {
        s_port_discontinuity_sequence =
            port_diagnostics.rx_discontinuity_count;
        Gnss_DiscontinuityHandle(instance);
    }

    for (byte_count = 0U;
         byte_count < GNSS_MAX_BYTES_PER_PROCESS;
         byte_count++)
    {
        if (Gnss_RingPopByte(instance, &byte) == 0U)
        {
            break;
        }
        Gnss_ParseByte(instance, byte, now_ms);
        processed = 1U;
    }
    if (byte_count == GNSS_MAX_BYTES_PER_PROCESS)
    {
        s_status.process_limit_count++;
    }

    Gnss_UpdateStatus(instance, now_ms);
    primask = Gnss_IrqLock();
    s_published_data = s_data;
    Gnss_IrqUnlock(primask);

    return (processed != 0U) ? GnssNeoM9n_UpdateOk : GnssNeoM9n_UpdateNoData;
}

uint8_t GnssNeoM9n_GetData(uint8_t instance, GnssNeoM9nData *out)
{
    GnssNeoM9nData snapshot;
    uint32_t primask;

    if (out == NULL)
    {
        return 0U;
    }

    primask = Gnss_IrqLock();
    snapshot = s_published_data;
    Gnss_IrqUnlock(primask);
    *out = snapshot;
    return snapshot.online;
}

uint8_t GnssNeoM9n_IsInitialized(uint8_t instance)
{
    return s_initialized;
}

void GnssNeoM9n_GetConfigSnapshot(uint8_t instance, GnssNeoM9nConfigSnapshot *out)
{
    if (out == NULL)
    {
        return;
    }

    s_config.save_cache_count = s_config_cache_count;
    s_config.baud_cached = Gnss_ConfigCacheContainsKey(instance, GNSS_CFG_UART1_BAUDRATE);
    *out = s_config;
}

void GnssNeoM9n_GetStatusSnapshot(uint8_t instance, GnssNeoM9nStatusSnapshot *out)
{
    if (out == NULL)
    {
        return;
    }

    s_status.initialized = s_initialized;
    s_status.uart_baudrate = Gnss_UartBaudrateGet(instance);
    s_status.detected = Gnss_GetDetected(instance, PlatformTime_Ms());
    *out = s_status;
}

static void Gnss_ConfigSnapshotMerge(GnssNeoM9nConfigSnapshot *destination,
                                     const GnssNeoM9nConfigSnapshot *source)
{
    if ((destination == NULL) || (source == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(destination, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(source, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((source->valid_mask & GNSS_CONFIG_VALID_BAUD) != 0U)
    {
        destination->baudrate = source->baudrate;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_RATE) != 0U)
    {
        destination->rate_hz = source->rate_hz;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_DYNAMIC) != 0U)
    {
        destination->dynamic_model = source->dynamic_model;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_CONSTELLATIONS) != 0U)
    {
        destination->constellations_mask |= source->constellations_mask;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_PROTOCOL_IN) != 0U)
    {
        destination->protocol_in |= source->protocol_in;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_PROTOCOL_OUT) != 0U)
    {
        destination->protocol_out |= source->protocol_out;
    }
    if ((source->valid_mask & GNSS_CONFIG_VALID_NAV_PVT) != 0U)
    {
        destination->nav_pvt_rate = source->nav_pvt_rate;
        destination->nav_pvt_known = source->nav_pvt_known;
    }
    destination->valid_mask |= source->valid_mask;
}

static GnssNeoM9nConfigReadResult Gnss_ConfigGroupRead(uint8_t instance,
    GnssNeoM9nConfigReadGroup group,
    const uint32_t *keys,
    uint8_t key_count,
    uint16_t valid_bits,
    GnssNeoM9nConfigSnapshot *aggregate,
    GnssNeoM9nConfigReadDiagnostics *failure)
{
    GnssNeoM9nConfigReadDiagnostics first_failure;
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nConfigReadResult first_result =
        GnssNeoM9nConfigReadResponseOk;
    uint8_t index;

    if ((keys == NULL) || (aggregate == NULL))
    { return GnssNeoM9nConfigReadNotReady; }
    SILVERSTAR_ASSERT_OBJECT(keys, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(aggregate, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = GnssNeoM9n_SendValget(instance, keys, key_count,
                                   GNSS_CONFIG_READ_GROUP_TIMEOUT_MS);
    if (result == GnssNeoM9nConfigReadResponseOk)
    {
        Gnss_ConfigSnapshotMerge(aggregate, &s_valget_config);
        aggregate->valid_mask |= valid_bits;
        return result;
    }

    (void)memset(&first_failure, 0, sizeof(first_failure));
    for (index = 0U; index < key_count; index++)
    {
        result = GnssNeoM9n_SendValget(instance, &keys[index], 1U,
                                       GNSS_CONFIG_READ_KEY_TIMEOUT_MS);
        if (result == GnssNeoM9nConfigReadResponseOk)
        {
            Gnss_ConfigSnapshotMerge(aggregate, &s_valget_config);
        }
        else if (first_result == GnssNeoM9nConfigReadResponseOk)
        {
            first_result = result;
            first_failure = s_valget_diagnostics;
            first_failure.failed_group = group;
            first_failure.failed_key = keys[index];
        }
    }
    aggregate->valid_mask &= (uint16_t)(~valid_bits);
    if (first_result == GnssNeoM9nConfigReadResponseOk)
    {
        aggregate->valid_mask |= valid_bits;
    }
    else if (failure != NULL)
    {
        *failure = first_failure;
    }
    return first_result;
}

static void Gnss_ConfigGroupAccumulate(uint8_t instance,
    GnssNeoM9nConfigReadGroup group,
    const uint32_t *keys,
    uint8_t key_count,
    uint16_t valid_bits,
    GnssNeoM9nConfigSnapshot *aggregate,
    GnssNeoM9nConfigReadResult *first_result,
    GnssNeoM9nConfigReadDiagnostics *first_failure)
{
    GnssNeoM9nConfigReadDiagnostics group_failure;
    GnssNeoM9nConfigReadResult result;

    if ((aggregate == NULL) || (first_result == NULL) ||
        (first_failure == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(aggregate, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(first_result, GnssNeoM9nConfigReadResult,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(&group_failure, 0, sizeof(group_failure));
    result = Gnss_ConfigGroupRead(instance, group, keys, key_count, valid_bits,
                                  aggregate, &group_failure);
    if ((result != GnssNeoM9nConfigReadResponseOk) &&
        (*first_result == GnssNeoM9nConfigReadResponseOk))
    {
        *first_result = result;
        *first_failure = group_failure;
    }
}

static GnssNeoM9nConfigReadResult Gnss_ConfigNotReadyStore(
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics)
{
    if (elapsed_ms != NULL) { *elapsed_ms = 0U; }
    if (out != NULL) { (void)memset(out, 0, sizeof(*out)); }
    if (diagnostics != NULL)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
        diagnostics->result = GnssNeoM9nConfigReadNotReady;
        diagnostics->detailed_result = GnssNeoM9nTransactionDetailNotReady;
    }
    return GnssNeoM9nConfigReadNotReady;
}

static void Gnss_PortDiscontinuityUpdate(uint8_t instance)
{
    PlatformUartDiagnostics port_diagnostics;

    (void)PlatformUart_DiagnosticsGet(NeoM9nResource_UartGet(instance),
                                      &port_diagnostics);
    if (port_diagnostics.rx_discontinuity_count !=
        s_port_discontinuity_sequence)
    {
        s_port_discontinuity_sequence =
            port_diagnostics.rx_discontinuity_count;
        Gnss_DiscontinuityHandle(instance);
    }
}

static void Gnss_ConfigReadResultStore(uint8_t instance,
    GnssNeoM9nConfigSnapshot *aggregate,
    GnssNeoM9nConfigReadDiagnostics *first_failure,
    GnssNeoM9nConfigReadResult first_result)
{
    SILVERSTAR_ASSERT_OBJECT(aggregate, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(first_failure,
        GnssNeoM9nConfigReadDiagnostics, SILVERSTAR_ASSERT_MODULE_DEVICE);
    aggregate->save_cache_count = s_config_cache_count;
    aggregate->baud_cached =
        Gnss_ConfigCacheContainsKey(instance, GNSS_CFG_UART1_BAUDRATE);
    if (first_result == GnssNeoM9nConfigReadResponseOk)
    {
        s_config = *aggregate;
        *first_failure = s_valget_diagnostics;
        first_failure->result = GnssNeoM9nConfigReadResponseOk;
        first_failure->failed_group = GnssNeoM9nConfigReadGroupNone;
        first_failure->failed_key = 0U;
    }
}

GnssNeoM9nConfigReadResult GnssNeoM9n_ReadHardwareConfig(uint8_t instance,
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics)
{
    GnssNeoM9nConfigSnapshot aggregate;
    GnssNeoM9nConfigReadDiagnostics first_failure;
    GnssNeoM9nConfigReadResult first_result =
        GnssNeoM9nConfigReadResponseOk;
    uint32_t start_ms = PlatformTime_Ms();
    uint8_t group_index;

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized == 0U)
    {
        return Gnss_ConfigNotReadyStore(out, elapsed_ms, diagnostics);
    }
    Gnss_PortDiscontinuityUpdate(instance);
    (void)memset(&aggregate, 0, sizeof(aggregate));
    (void)memset(&first_failure, 0, sizeof(first_failure));
    aggregate.read_layer = GnssNeoM9nPersistRam;
    aggregate.last_write_layers = s_config.last_write_layers;
    aggregate.last_ack = s_config.last_ack;
    for (group_index = 0U;
         group_index < (uint8_t)(sizeof(s_config_read_groups) /
                                 sizeof(s_config_read_groups[0]));
         group_index++)
    {
        const GnssConfigReadGroupDefinition *group =
            &s_config_read_groups[group_index];
        Gnss_ConfigGroupAccumulate(instance, group->group, group->keys,
            group->key_count, group->valid_bits, &aggregate,
            &first_result, &first_failure);
    }
    Gnss_ConfigReadResultStore(instance, &aggregate, &first_failure, first_result);
    if (out != NULL) { *out = aggregate; }
    if (elapsed_ms != NULL) { *elapsed_ms = PlatformTime_Ms() - start_ms; }
    if (diagnostics != NULL) { *diagnostics = first_failure; }
    return first_result;
}

static void Gnss_ConfigAsyncFinish(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    const GnssNeoM9nConfigReadDiagnostics *diagnostics)
{
    s_config_async.result = result;
    if (diagnostics != NULL)
    {
        s_config_async.first_failure = *diagnostics;
    }
    s_config_async.first_failure.result = result;
    s_config_async.state = GnssConfigAsyncComplete;
}

static void Gnss_ConfigAsyncNextGroup(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    s_config_async.group_index++;
    if (s_config_async.group_index >=
        (uint8_t)(sizeof(s_config_read_groups) /
                  sizeof(s_config_read_groups[0])))
    {
        s_config_async.aggregate.save_cache_count = s_config_cache_count;
        s_config_async.aggregate.baud_cached =
            Gnss_ConfigCacheContainsKey(instance, GNSS_CFG_UART1_BAUDRATE);
        if (s_config_async.first_result ==
            GnssNeoM9nConfigReadResponseOk)
        {
            s_config = s_config_async.aggregate;
            s_config_async.first_failure = s_valget_diagnostics;
            s_config_async.first_failure.failed_group =
                GnssNeoM9nConfigReadGroupNone;
            s_config_async.first_failure.failed_key = 0U;
        }
        Gnss_ConfigAsyncFinish(instance, s_config_async.first_result,
                               &s_config_async.first_failure);
        return;
    }
    s_config_async.state = GnssConfigAsyncStartGroup;
}

static void Gnss_ConfigAsyncKeyFinish(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    const GnssNeoM9nConfigSnapshot *snapshot,
    const GnssNeoM9nConfigReadDiagnostics *diagnostics)
{
    const GnssConfigReadGroupDefinition *group =
        &s_config_read_groups[s_config_async.group_index];

    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((result == GnssNeoM9nConfigReadResponseOk) && (snapshot != NULL))
    {
        Gnss_ConfigSnapshotMerge(&s_config_async.aggregate, snapshot);
    }
    else if (s_config_async.key_result ==
             GnssNeoM9nConfigReadResponseOk)
    {
        s_config_async.key_result = result;
        if (diagnostics != NULL)
        {
            s_config_async.key_failure = *diagnostics;
        }
        s_config_async.key_failure.failed_group = group->group;
        s_config_async.key_failure.failed_key =
            group->keys[s_config_async.key_index];
    }
    s_config_async.key_index++;
    if (s_config_async.key_index < group->key_count)
    {
        s_config_async.state = GnssConfigAsyncStartKey;
        return;
    }
    s_config_async.aggregate.valid_mask &=
        (uint16_t)(~group->valid_bits);
    if (s_config_async.key_result == GnssNeoM9nConfigReadResponseOk)
    {
        s_config_async.aggregate.valid_mask |= group->valid_bits;
    }
    else if (s_config_async.first_result ==
             GnssNeoM9nConfigReadResponseOk)
    {
        s_config_async.first_result = s_config_async.key_result;
        s_config_async.first_failure = s_config_async.key_failure;
    }
    Gnss_ConfigAsyncNextGroup(instance);
}

GnssNeoM9nAsyncStartResult GnssNeoM9n_ConfigReadAsyncStart(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized == 0U)
    {
        return GnssNeoM9nAsyncStartNotReady;
    }
    if ((s_config_async.state != GnssConfigAsyncIdle) ||
        (s_valget_wait_active != 0U) ||
        (s_satellite_wait_active != 0U) || (s_rf_wait_active != 0U))
    {
        return GnssNeoM9nAsyncStartBusy;
    }
    (void)memset(&s_config_async, 0, sizeof(s_config_async));
    s_config_async.state = GnssConfigAsyncStartGroup;
    s_config_async.start_ms = PlatformTime_Ms();
    s_config_async.first_result = GnssNeoM9nConfigReadResponseOk;
    s_config_async.key_result = GnssNeoM9nConfigReadResponseOk;
    s_config_async.result = GnssNeoM9nConfigReadNotReady;
    s_config_async.aggregate.read_layer = GnssNeoM9nPersistRam;
    s_config_async.aggregate.last_write_layers =
        s_config.last_write_layers;
    s_config_async.aggregate.last_ack = s_config.last_ack;
    return GnssNeoM9nAsyncStartOk;
}

static GnssNeoM9nAsyncPollResult Gnss_ConfigAsyncCompleteStore(uint8_t instance,
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult *result)
{
    if (out != NULL) { *out = s_config_async.aggregate; }
    if (elapsed_ms != NULL)
    {
        *elapsed_ms = PlatformTime_Ms() - s_config_async.start_ms;
    }
    if (diagnostics != NULL)
    {
        *diagnostics = s_config_async.first_failure;
    }
    if (result != NULL) { *result = s_config_async.result; }
    s_config_async.state = GnssConfigAsyncIdle;
    return GnssNeoM9nAsyncPollComplete;
}

static void Gnss_ConfigAsyncGroupStart(uint8_t instance,
    const GnssConfigReadGroupDefinition *group)
{
    GnssNeoM9nAsyncStartResult start_result;

    SILVERSTAR_ASSERT_OBJECT(group, GnssConfigReadGroupDefinition,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_result = Gnss_ValgetAsyncStart(instance, group->keys, group->key_count, GNSS_VALGET_LAYER_RAM);
    if (start_result == GnssNeoM9nAsyncStartBusy) { return; }
    s_config_async.request_start_ms = PlatformTime_Ms();
    if (start_result == GnssNeoM9nAsyncStartOk)
    {
        s_config_async.state = GnssConfigAsyncWaitGroup;
    }
    else
    {
        s_config_async.key_index = 0U;
        s_config_async.key_result = GnssNeoM9nConfigReadResponseOk;
        s_config_async.state = GnssConfigAsyncStartKey;
    }
}

static void Gnss_ConfigAsyncKeyStart(uint8_t instance,
    const GnssConfigReadGroupDefinition *group)
{
    GnssNeoM9nConfigReadDiagnostics response;
    GnssNeoM9nAsyncStartResult start_result;

    SILVERSTAR_ASSERT_OBJECT(group, GnssConfigReadGroupDefinition,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_result = Gnss_ValgetAsyncStart(instance,
        &group->keys[s_config_async.key_index], 1U, GNSS_VALGET_LAYER_RAM);
    if (start_result == GnssNeoM9nAsyncStartBusy) { return; }
    s_config_async.request_start_ms = PlatformTime_Ms();
    if (start_result == GnssNeoM9nAsyncStartOk)
    {
        s_config_async.state = GnssConfigAsyncWaitKey;
        return;
    }
    (void)memset(&response, 0, sizeof(response));
    response.result = (start_result == GnssNeoM9nAsyncStartTxError) ?
        GnssNeoM9nConfigReadTxError : GnssNeoM9nConfigReadNotReady;
    response.detailed_result =
        (start_result == GnssNeoM9nAsyncStartTxError) ?
            GnssNeoM9nTransactionDetailTxError :
            GnssNeoM9nTransactionDetailBusy;
    Gnss_ConfigAsyncKeyFinish(instance, response.result, NULL, &response);
}

static uint8_t Gnss_ConfigAsyncDiscontinuityFinish(uint8_t instance,
    const GnssConfigReadGroupDefinition *group,
    GnssNeoM9nConfigReadDiagnostics *response,
    GnssNeoM9nConfigReadResult response_result)
{
    if (response->detailed_result !=
        GnssNeoM9nTransactionDetailRxDiscontinuity)
    {
        return 0U;
    }
    response->failed_group = group->group;
    response->failed_key = (s_config_async.state == GnssConfigAsyncWaitKey) ?
        group->keys[s_config_async.key_index] : 0U;
    Gnss_ConfigAsyncFinish(instance, response_result, response);
    return 1U;
}

static void Gnss_ConfigAsyncGroupResponseHandle(uint8_t instance,
    const GnssConfigReadGroupDefinition *group,
    const GnssNeoM9nConfigSnapshot *snapshot,
    GnssNeoM9nConfigReadResult response_result)
{
    if (response_result == GnssNeoM9nConfigReadResponseOk)
    {
        Gnss_ConfigSnapshotMerge(&s_config_async.aggregate, snapshot);
        s_config_async.aggregate.valid_mask |= group->valid_bits;
        Gnss_ConfigAsyncNextGroup(instance);
        return;
    }
    s_config_async.key_index = 0U;
    s_config_async.key_result = GnssNeoM9nConfigReadResponseOk;
    (void)memset(&s_config_async.key_failure, 0,
                 sizeof(s_config_async.key_failure));
    s_config_async.state = GnssConfigAsyncStartKey;
}

static void Gnss_ConfigAsyncWaitPoll(uint8_t instance,
    const GnssConfigReadGroupDefinition *group)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics response;
    GnssNeoM9nConfigReadResult response_result;
    uint32_t timeout_ms;

    SILVERSTAR_ASSERT_OBJECT(group, GnssConfigReadGroupDefinition,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    timeout_ms = (s_config_async.state == GnssConfigAsyncWaitGroup) ?
        GNSS_CONFIG_READ_GROUP_TIMEOUT_MS : GNSS_CONFIG_READ_KEY_TIMEOUT_MS;
    if ((PlatformTime_Ms() - s_config_async.request_start_ms) >= timeout_ms)
    {
        Gnss_ValgetAsyncCancel(instance, GnssNeoM9nConfigReadTimeout,
                               GnssNeoM9nTransactionDetailTimeout);
    }
    if (Gnss_ValgetAsyncPoll(instance, &snapshot, &response, &response_result) ==
        GnssNeoM9nAsyncPollPending)
    {
        return;
    }
    if (Gnss_ConfigAsyncDiscontinuityFinish(instance,
            group, &response, response_result) != 0U)
    {
        return;
    }
    if (s_config_async.state == GnssConfigAsyncWaitGroup)
    {
        Gnss_ConfigAsyncGroupResponseHandle(instance, group, &snapshot,
                                            response_result);
    }
    else
    {
        Gnss_ConfigAsyncKeyFinish(instance, response_result, &snapshot, &response);
    }
}

GnssNeoM9nAsyncPollResult GnssNeoM9n_ConfigReadAsyncPoll(uint8_t instance,
    GnssNeoM9nConfigSnapshot *out,
    uint32_t *elapsed_ms,
    GnssNeoM9nConfigReadDiagnostics *diagnostics,
    GnssNeoM9nConfigReadResult *result)
{
    const GnssConfigReadGroupDefinition *group;

    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    group = NULL;
    if ((s_config_async.state != GnssConfigAsyncIdle) &&
        (s_config_async.state != GnssConfigAsyncComplete))
    {
        SILVERSTAR_ASSERT(
            s_config_async.group_index <
                (uint8_t)(sizeof(s_config_read_groups) /
                          sizeof(s_config_read_groups[0])),
            SILVERSTAR_ASSERT_MODULE_DEVICE,
            SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        group = &s_config_read_groups[s_config_async.group_index];
    }
    switch (s_config_async.state)
    {
    case GnssConfigAsyncIdle:
        break;
    case GnssConfigAsyncStartGroup:
        Gnss_ConfigAsyncGroupStart(instance, group);
        break;
    case GnssConfigAsyncWaitGroup:
    case GnssConfigAsyncWaitKey:
        Gnss_ConfigAsyncWaitPoll(instance, group);
        break;
    case GnssConfigAsyncStartKey:
        Gnss_ConfigAsyncKeyStart(instance, group);
        break;
    case GnssConfigAsyncComplete:
        return Gnss_ConfigAsyncCompleteStore(instance,
            out, elapsed_ms, diagnostics, result);
    default:
        SILVERSTAR_ASSERT(0U, SILVERSTAR_ASSERT_MODULE_DEVICE,
                          SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        break;
    }
    return GnssNeoM9nAsyncPollPending;
}

void GnssNeoM9n_ConfigReadAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail)
{
    GnssNeoM9nConfigReadDiagnostics diagnostics;

    SILVERSTAR_ASSERT_OBJECT(&s_config_async, GnssConfigAsyncTransaction,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_config_async.state == GnssConfigAsyncIdle) ||
        (s_config_async.state == GnssConfigAsyncComplete))
    {
        return;
    }
    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    diagnostics.result = result;
    diagnostics.detailed_result = detail;
    if (s_config_async.group_index <
        (uint8_t)(sizeof(s_config_read_groups) /
                  sizeof(s_config_read_groups[0])))
    {
        diagnostics.failed_group =
            s_config_read_groups[s_config_async.group_index].group;
    }
    s_valget_wait_active = 0U;
    s_valget_received = 0U;
    s_config_async.result = result;
    s_config_async.first_failure = diagnostics;
    s_config_async.state = GnssConfigAsyncIdle;
}

GnssNeoM9nItemStartResult GnssNeoM9n_ItemReadStart(
    uint8_t instance, uint32_t key)
{
    GnssNeoM9nAsyncStartResult result;

    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) ||
        (Gnss_ConfigKeyValueLen(key) == 0U))
    { return GnssNeoM9nItemStartResult_InvalidArgument; }
    if (s_initialized == 0U)
    { return GnssNeoM9nItemStartResult_NotReady; }
    if ((s_contexts[instance].item_read_active != 0U) ||
        (s_contexts[instance].item_write_active != 0U) ||
        (s_config_async.state != GnssConfigAsyncIdle))
    { return GnssNeoM9nItemStartResult_Busy; }
    result = Gnss_ValgetAsyncStart(instance, &key, 1U,
        GNSS_VALGET_LAYER_RAM);
    if (result == GnssNeoM9nAsyncStartBusy)
    { return GnssNeoM9nItemStartResult_Busy; }
    if (result != GnssNeoM9nAsyncStartOk)
    { return GnssNeoM9nItemStartResult_IoError; }
    s_contexts[instance].item_read_key = key;
    s_contexts[instance].item_read_started_ms = PlatformTime_Ms();
    s_contexts[instance].item_read_active = 1U;
    return GnssNeoM9nItemStartResult_Ok;
}

GnssNeoM9nItemPollResult GnssNeoM9n_ItemReadPoll(
    uint8_t instance, GnssNeoM9nConfigItem *item)
{
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nAsyncPollResult poll_result;

    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) || (item == NULL) ||
        (s_contexts[instance].item_read_active == 0U))
    { return GnssNeoM9nItemPollResult_NotReady; }
    (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
    if ((s_valget_received == 0U) &&
        ((uint32_t)(PlatformTime_Ms() -
            s_contexts[instance].item_read_started_ms) >=
            GNSS_CONFIG_READ_GROUP_TIMEOUT_MS))
    {
        Gnss_ValgetAsyncCancel(instance, GnssNeoM9nConfigReadTimeout,
            GnssNeoM9nTransactionDetailTimeout);
    }
    poll_result = Gnss_ValgetAsyncPoll(instance, NULL, NULL, &result);
    if (poll_result == GnssNeoM9nAsyncPollPending)
    { return GnssNeoM9nItemPollResult_Pending; }
    s_contexts[instance].item_read_active = 0U;
    if (result == GnssNeoM9nConfigReadTimeout)
    { return GnssNeoM9nItemPollResult_Timeout; }
    if (result == GnssNeoM9nConfigReadNak)
    { return GnssNeoM9nItemPollResult_Nak; }
    if ((result != GnssNeoM9nConfigReadResponseOk) ||
        (s_valget_cache_count != 1U) ||
        (s_valget_cache[0].key != s_contexts[instance].item_read_key))
    { return GnssNeoM9nItemPollResult_IoError; }
    *item = s_valget_cache[0];
    return GnssNeoM9nItemPollResult_Complete;
}

GnssNeoM9nItemStartResult GnssNeoM9n_ItemWriteStart(
    uint8_t instance, const GnssNeoM9nConfigItem *item)
{
    uint8_t payload[12] = {0U, GNSS_CFG_LAYER_RAM, 0U, 0U};
    PlatformResult result;
    uint8_t index;

    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) || (item == NULL) ||
        (item->value_len == 0U) || (item->value_len > 4U) ||
        (item->value_len != Gnss_ConfigKeyValueLen(item->key)))
    { return GnssNeoM9nItemStartResult_InvalidArgument; }
    if (s_initialized == 0U)
    { return GnssNeoM9nItemStartResult_NotReady; }
    if ((s_contexts[instance].item_read_active != 0U) ||
        (s_contexts[instance].item_write_active != 0U) ||
        (s_valget_wait_active != 0U) ||
        (s_config_async.state != GnssConfigAsyncIdle) ||
        (s_satellite_wait_active != 0U) || (s_rf_wait_active != 0U))
    { return GnssNeoM9nItemStartResult_Busy; }
    Gnss_WriteU32Le(&payload[4], item->key);
    for (index = 0U; index < item->value_len; index++)
    { payload[8U + index] = (uint8_t)(item->value >> (8U * index)); }
    Gnss_ClearAckWait(instance, GNSS_UBX_CFG_CLASS,
        GNSS_UBX_CFG_VALSET_ID);
    result = Gnss_UbxFrameEnqueue(instance, GNSS_UBX_CFG_CLASS,
        GNSS_UBX_CFG_VALSET_ID, payload,
        (uint16_t)(8U + item->value_len));
    if (result == PLATFORM_BUSY)
    { return GnssNeoM9nItemStartResult_Busy; }
    if (result != PLATFORM_OK)
    { return GnssNeoM9nItemStartResult_IoError; }
    s_contexts[instance].item_write_started_ms = PlatformTime_Ms();
    s_contexts[instance].item_write_active = 1U;
    return GnssNeoM9nItemStartResult_Ok;
}

GnssNeoM9nItemPollResult GnssNeoM9n_ItemWritePoll(uint8_t instance)
{
    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) ||
        (s_contexts[instance].item_write_active == 0U))
    { return GnssNeoM9nItemPollResult_NotReady; }
    (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
    if (s_transaction_discontinuity != 0U)
    {
        s_contexts[instance].item_write_active = 0U;
        return GnssNeoM9nItemPollResult_IoError;
    }
    if ((s_last_ack_class == GNSS_UBX_CFG_CLASS) &&
        (s_last_ack_id == GNSS_UBX_CFG_VALSET_ID))
    {
        if (s_last_ack == GnssNeoM9nAckAck)
        {
            s_contexts[instance].item_write_active = 0U;
            return GnssNeoM9nItemPollResult_Complete;
        }
        if (s_last_ack == GnssNeoM9nAckNak)
        {
            s_contexts[instance].item_write_active = 0U;
            return GnssNeoM9nItemPollResult_Nak;
        }
    }
    if ((uint32_t)(PlatformTime_Ms() -
            s_contexts[instance].item_write_started_ms) >=
        GNSS_ACK_TIMEOUT_MS)
    {
        s_contexts[instance].item_write_active = 0U;
        return GnssNeoM9nItemPollResult_Timeout;
    }
    return GnssNeoM9nItemPollResult_Pending;
}

GnssNeoM9nConfigReadResult GnssNeoM9n_ValgetRead(uint8_t instance,
    const uint32_t *keys,
    uint8_t count,
    GnssNeoM9nConfigReadDiagnostics *diagnostics)
{
    GnssNeoM9nConfigReadResult result = GnssNeoM9n_SendValget(instance,
        keys, count, GNSS_CONFIG_READ_GROUP_TIMEOUT_MS);

    if (diagnostics != NULL) { *diagnostics = s_valget_diagnostics; }
    return result;
}

GnssNeoM9nAckState GnssNeoM9n_GetLastAck(uint8_t instance)
{
    return s_last_ack;
}

uint8_t GnssNeoM9n_GetSatelliteDiagnostics(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL) { return 0U; }
    primask = Gnss_IrqLock();
    *diagnostics = s_satellite_diagnostics;
    Gnss_IrqUnlock(primask);
    return (uint8_t)(diagnostics->sequence != 0U);
}

uint8_t GnssNeoM9n_GetRfDiagnostics(uint8_t instance,
    GnssNeoM9nRfDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL) { return 0U; }
    primask = Gnss_IrqLock();
    *diagnostics = s_rf_diagnostics;
    Gnss_IrqUnlock(primask);
    return (uint8_t)(diagnostics->sequence != 0U);
}

GnssNeoM9nAsyncStartResult GnssNeoM9n_SatelliteDiagnosticsAsyncStart(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_satellite_diagnostics,
        GnssNeoM9nSatelliteDiagnostics, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized == 0U)
    {
        return GnssNeoM9nAsyncStartNotReady;
    }
    if ((s_config_async.state != GnssConfigAsyncIdle) ||
        (s_valget_wait_active != 0U) ||
        (s_satellite_wait_active != 0U) || (s_rf_wait_active != 0U))
    {
        return GnssNeoM9nAsyncStartBusy;
    }
    s_satellite_wait_sequence = s_satellite_diagnostics.sequence;
    s_satellite_wait_active = 1U;
    s_transaction_discontinuity = 0U;
    s_satellite_diagnostics.valid = 0U;
    s_satellite_diagnostics.read_result = GnssNeoM9nConfigReadTimeout;
    s_satellite_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailTimeout;
    s_satellite_diagnostics.response_length = 0U;
    s_satellite_diagnostics.expected_class = GNSS_UBX_NAV_CLASS;
    s_satellite_diagnostics.expected_id = GNSS_UBX_NAV_SAT_ID;
    s_satellite_diagnostics.received_class = 0U;
    s_satellite_diagnostics.received_id = 0U;
    s_satellite_diagnostics.expected_ck_a = 0U;
    s_satellite_diagnostics.expected_ck_b = 0U;
    s_satellite_diagnostics.received_ck_a = 0U;
    s_satellite_diagnostics.received_ck_b = 0U;
    if (GnssNeoM9n_SendUbx(instance, GNSS_UBX_NAV_CLASS,
                            GNSS_UBX_NAV_SAT_ID,
                            NULL,
                            0U) != 0)
    {
        s_satellite_diagnostics.read_result = GnssNeoM9nConfigReadTxError;
        s_satellite_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailTxError;
        s_satellite_diagnostics.timestamp_us = PlatformTime_Us();
        s_satellite_diagnostics.sequence++;
        s_satellite_wait_active = 0U;
        return GnssNeoM9nAsyncStartTxError;
    }
    return GnssNeoM9nAsyncStartOk;
}

GnssNeoM9nAsyncPollResult GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics)
{
    if (s_satellite_diagnostics.sequence == s_satellite_wait_sequence)
    {
        return GnssNeoM9nAsyncPollPending;
    }
    s_satellite_wait_active = 0U;
    if (diagnostics != NULL) { *diagnostics = s_satellite_diagnostics; }
    return GnssNeoM9nAsyncPollComplete;
}

void GnssNeoM9n_SatelliteDiagnosticsAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail)
{
    if (s_satellite_wait_active == 0U) { return; }
    s_satellite_diagnostics.timestamp_us = PlatformTime_Us();
    s_satellite_diagnostics.valid = 0U;
    s_satellite_diagnostics.read_result = result;
    s_satellite_diagnostics.detailed_result = detail;
    s_satellite_diagnostics.sequence++;
    s_satellite_wait_active = 0U;
}

int GnssNeoM9n_ReadSatelliteDiagnostics(uint8_t instance,
    GnssNeoM9nSatelliteDiagnostics *diagnostics)
{
    GnssNeoM9nAsyncStartResult start_result;
    uint32_t start_ms;
    uint32_t poll;

    if (diagnostics == NULL) { return -4; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, GnssNeoM9nSatelliteDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_result = GnssNeoM9n_SatelliteDiagnosticsAsyncStart(instance);
    if (start_result == GnssNeoM9nAsyncStartNotReady)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
        diagnostics->read_result = GnssNeoM9nConfigReadNotReady;
        diagnostics->detailed_result = GnssNeoM9nTransactionDetailNotReady;
        return -3;
    }
    if (start_result == GnssNeoM9nAsyncStartBusy) { return -5; }
    if (start_result == GnssNeoM9nAsyncStartTxError)
    {
        *diagnostics = s_satellite_diagnostics;
        return -1;
    }
    start_ms = PlatformTime_Ms();
    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >=
            GNSS_CONFIG_READ_TIMEOUT_MS)
        {
            break;
        }
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        if (GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(instance, diagnostics) ==
            GnssNeoM9nAsyncPollComplete)
        {
            if (diagnostics->read_result ==
                GnssNeoM9nConfigReadResponseOk)
            { return 0; }
            return (diagnostics->read_result ==
                GnssNeoM9nConfigReadIoError) ? -6 : -5;
        }
        PlatformTime_DelayMs(1U);
    }
    GnssNeoM9n_SatelliteDiagnosticsAsyncCancel(instance,
        GnssNeoM9nConfigReadTimeout,
        GnssNeoM9nTransactionDetailTimeout);
    (void)GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(instance, diagnostics);
    return -2;
}

GnssNeoM9nAsyncStartResult GnssNeoM9n_RfDiagnosticsAsyncStart(uint8_t instance)
{
    SILVERSTAR_ASSERT_OBJECT(&s_rf_diagnostics, GnssNeoM9nRfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized == 0U)
    {
        return GnssNeoM9nAsyncStartNotReady;
    }
    if ((s_config_async.state != GnssConfigAsyncIdle) ||
        (s_valget_wait_active != 0U) ||
        (s_satellite_wait_active != 0U) || (s_rf_wait_active != 0U))
    {
        return GnssNeoM9nAsyncStartBusy;
    }
    s_rf_wait_sequence = s_rf_diagnostics.sequence;
    s_rf_wait_active = 1U;
    s_transaction_discontinuity = 0U;
    s_rf_diagnostics.valid = 0U;
    s_rf_diagnostics.read_result = GnssNeoM9nConfigReadTimeout;
    s_rf_diagnostics.detailed_result =
        GnssNeoM9nTransactionDetailTimeout;
    s_rf_diagnostics.response_length = 0U;
    if (GnssNeoM9n_SendUbx(instance, GNSS_UBX_MON_CLASS,
                            GNSS_UBX_MON_RF_ID,
                            NULL,
                            0U) != 0)
    {
        s_rf_diagnostics.read_result = GnssNeoM9nConfigReadTxError;
        s_rf_diagnostics.detailed_result =
            GnssNeoM9nTransactionDetailTxError;
        s_rf_diagnostics.timestamp_us = PlatformTime_Us();
        s_rf_diagnostics.sequence++;
        s_rf_wait_active = 0U;
        return GnssNeoM9nAsyncStartTxError;
    }
    return GnssNeoM9nAsyncStartOk;
}

GnssNeoM9nAsyncPollResult GnssNeoM9n_RfDiagnosticsAsyncPoll(uint8_t instance,
    GnssNeoM9nRfDiagnostics *diagnostics)
{
    if (s_rf_diagnostics.sequence == s_rf_wait_sequence)
    {
        return GnssNeoM9nAsyncPollPending;
    }
    s_rf_wait_active = 0U;
    if (diagnostics != NULL) { *diagnostics = s_rf_diagnostics; }
    return GnssNeoM9nAsyncPollComplete;
}

void GnssNeoM9n_RfDiagnosticsAsyncCancel(uint8_t instance,
    GnssNeoM9nConfigReadResult result,
    GnssNeoM9nTransactionDetail detail)
{
    if (s_rf_wait_active == 0U) { return; }
    s_rf_diagnostics.timestamp_us = PlatformTime_Us();
    s_rf_diagnostics.valid = 0U;
    s_rf_diagnostics.read_result = result;
    s_rf_diagnostics.detailed_result = detail;
    s_rf_diagnostics.sequence++;
    s_rf_wait_active = 0U;
}

int GnssNeoM9n_ReadRfDiagnostics(uint8_t instance, GnssNeoM9nRfDiagnostics *diagnostics)
{
    GnssNeoM9nAsyncStartResult start_result;
    uint32_t start_ms;
    uint32_t poll;

    if (diagnostics == NULL) { return -4; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, GnssNeoM9nRfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_result = GnssNeoM9n_RfDiagnosticsAsyncStart(instance);
    if (start_result == GnssNeoM9nAsyncStartNotReady)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
        diagnostics->read_result = GnssNeoM9nConfigReadNotReady;
        diagnostics->detailed_result = GnssNeoM9nTransactionDetailNotReady;
        return -3;
    }
    if (start_result == GnssNeoM9nAsyncStartBusy) { return -5; }
    if (start_result == GnssNeoM9nAsyncStartTxError)
    {
        *diagnostics = s_rf_diagnostics;
        return -1;
    }
    start_ms = PlatformTime_Ms();
    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        if ((PlatformTime_Ms() - start_ms) >=
            GNSS_CONFIG_READ_TIMEOUT_MS)
        {
            break;
        }
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        if (GnssNeoM9n_RfDiagnosticsAsyncPoll(instance, diagnostics) ==
            GnssNeoM9nAsyncPollComplete)
        {
            if (diagnostics->read_result ==
                GnssNeoM9nConfigReadResponseOk)
            { return 0; }
            return (diagnostics->read_result ==
                GnssNeoM9nConfigReadIoError) ? -6 : -5;
        }
        PlatformTime_DelayMs(1U);
    }
    GnssNeoM9n_RfDiagnosticsAsyncCancel(instance,
        GnssNeoM9nConfigReadTimeout,
        GnssNeoM9nTransactionDetailTimeout);
    (void)GnssNeoM9n_RfDiagnosticsAsyncPoll(instance, diagnostics);
    return -2;
}

int GnssNeoM9n_SendUbx(uint8_t instance, uint8_t cls, uint8_t id, const uint8_t *payload, uint16_t len)
{
    uint8_t frame[GNSS_UBX_TX_MAX_PAYLOAD_LEN + GNSS_UBX_TX_FRAME_OVERHEAD];
    uint8_t ck_a = 0U;
    uint8_t ck_b = 0U;
    uint16_t frame_len;
    uint16_t i;

    SILVERSTAR_ASSERT_OBJECT(&s_parser, GnssUbxParser_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (((payload == NULL) && (len != 0U)) || (len > GNSS_UBX_TX_MAX_PAYLOAD_LEN))
    {
        return -1;
    }

    frame[0] = GNSS_UBX_SYNC1;
    frame[1] = GNSS_UBX_SYNC2;
    frame[2] = cls;
    frame[3] = id;
    Gnss_WriteU16Le(&frame[4], len);

    if (len != 0U)
    {
        memcpy(&frame[6], payload, len);
    }

    for (i = 2U; i < (uint16_t)(6U + len); i++)
    {
        ck_a = (uint8_t)(ck_a + frame[i]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }

    frame[6U + len] = ck_a;
    frame[7U + len] = ck_b;
    frame_len = (uint16_t)(len + GNSS_UBX_TX_FRAME_OVERHEAD);

    return (PlatformUart_Write(NeoM9nResource_UartGet(instance), frame, frame_len,
                               GNSS_CFG_TIMEOUT_MS) == PLATFORM_OK) ? 0 : -1;
}

/*
 * 配置发送为同步阻塞接口，仅用于初始化阶段或手动调试阶段。
 * 不要在 UART/DMA/IDLE 回调中调用；是否写入RAM/BBR/Flash由上层启动策略决定。
 */
int GnssNeoM9n_ConfigOutputUbxOnly(uint8_t instance, uint8_t layers)
{
    return GnssNeoM9n_ConfigOutputProtocol(instance, layers, GnssOutputProtocolUbxOnly);
}

int GnssNeoM9n_ConfigOutputProtocol(uint8_t instance, uint8_t layers, GnssOutputProtocol output)
{
    int result;
    uint8_t out_ubx;
    uint8_t out_nmea;
    const GnssCfgItem_t items[] =
    {
        {GNSS_CFG_UART1INPROT_UBX, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_UART1INPROT_NMEA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_UART1INPROT_RTCM3X, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_UART1OUTPROT_UBX, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_UART1OUTPROT_NMEA, 0U, GNSS_CFG_ITEM_TYPE_L}
    };
    GnssCfgItem_t output_items[sizeof(items) / sizeof(items[0])];

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (output == GnssOutputProtocolNmeaOnly)
    {
        out_ubx = 0U;
        out_nmea = 1U;
    }
    else if (output == GnssOutputProtocolUbxOnly)
    {
        out_ubx = 1U;
        out_nmea = 0U;
    }
    else if (output == GnssOutputProtocolUbxNmea)
    {
        out_ubx = 1U;
        out_nmea = 1U;
    }
    else
    {
        return -1;
    }

    memcpy(output_items, items, sizeof(output_items));
    output_items[3].value = out_ubx;
    output_items[4].value = out_nmea;

    /*
 * 这里的 UART1 是 u-blox 模块内部 UART1，不是主控侧串口编号。
     * 保留输入 NMEA/RTCM3X 是为了后续调试或差分输入。
     * OUTPUT 命令默认只写 RAM；是否保存由用户显式执行 SAVE 决定。
     */
    result = GnssNeoM9n_SendValset(instance, layers,
                                   output_items,
                                   (uint8_t)(sizeof(output_items) / sizeof(output_items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers,
                                          output_items,
                                          (uint8_t)(sizeof(output_items) / sizeof(output_items[0])));
        s_config.protocol_in = 0x07U;
        s_config.protocol_out = (uint8_t)((out_ubx != 0U ? 0x01U : 0x00U) |
                                          (out_nmea != 0U ? 0x02U : 0x00U));
    }
    return result;
}

int GnssNeoM9n_ConfigNavPvtOutput(uint8_t instance, uint8_t layers, uint8_t rate)
{
    int result;
    const GnssCfgItem_t items[] =
    {
        {GNSS_CFG_MSGOUT_NAV_PVT_UART1, rate, GNSS_CFG_ITEM_TYPE_U1}
    };

    /*
     * rate = 1 表示每个 navigation epoch 输出一次 UBX-NAV-PVT，rate 不是 Hz。
     * 如果导航频率是 25Hz 且 rate=1，则 PVT 输出就是 25Hz。
     * rate = 0 表示关闭 UBX-NAV-PVT 输出。
     */
    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.nav_pvt_rate = rate;
        s_config.nav_pvt_known = 1U;
    }
    return result;
}

int GnssNeoM9n_ConfigNavRate(uint8_t instance, uint8_t layers, uint8_t hz)
{
    int result;
    uint16_t meas_ms;
    const GnssCfgItem_t items_template[] =
    {
        {GNSS_CFG_RATE_MEAS, 0U, GNSS_CFG_ITEM_TYPE_U2},
        {GNSS_CFG_RATE_NAV, 1U, GNSS_CFG_ITEM_TYPE_U2},
        {GNSS_CFG_RATE_TIMEREF, 1U, GNSS_CFG_ITEM_TYPE_E1}
    };
    GnssCfgItem_t items[sizeof(items_template) / sizeof(items_template[0])];

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((hz == 0U) || (hz > GNSS_MAX_RATE_HZ) || ((1000U % hz) != 0U))
    {
        return -1;
    }

    meas_ms = (uint16_t)(1000U / hz);
    if (meas_ms < 40U)
    {
        return -1;
    }

    memcpy(items, items_template, sizeof(items));
    items[0].value = meas_ms;

    /*
     * 25Hz 是 NEO-M9N PVT 最大导航更新率，meas_ms = 40。
     * 25Hz 会增加串口数据量和解析频率，但本项目认为数据连续性优先。
     * 最终配置推荐配合 921600 baud 使用，并确保 ring buffer 留有余量。
     */
    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.rate_hz = hz;
    }
    return result;
}

int GnssNeoM9n_ConfigUartBaudrate(uint8_t instance, uint8_t layers, uint32_t baudrate)
{
    int result;
    uint32_t old_baudrate;
    const GnssCfgItem_t items[] =
    {
        {GNSS_CFG_UART1_BAUDRATE, baudrate, GNSS_CFG_ITEM_TYPE_U4}
    };

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((baudrate < GNSS_UART_BAUDRATE_MIN) || (baudrate > GNSS_MAX_BAUDRATE))
    {
        return -1;
    }

    /*
     * 发送该配置后，NEO-M9N UART 会切换到新波特率，本函数同步重配板级 UART。
     * 如果目标波特率与固件默认配置不一致，掉电重启后需要固件侧也匹配。
     * 波特率适合最终写入 Flash，否则模块断电后回到默认 38400，调试会很不方便。
     */
    old_baudrate = Gnss_UartBaudrateGet(instance);
    s_uart_baud_changed = (old_baudrate != baudrate) ? 1U : 0U;
    s_uart_baseline_ubx_frames = s_status.ubx_frames;
    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result != 0)
    {
        return result;
    }

    if (old_baudrate != baudrate)
    {
        if (PlatformUart_BaudSet(NeoM9nResource_UartGet(instance), baudrate) != PLATFORM_OK)
        {
            return -1;
        }
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.baudrate = baudrate;
        s_status.uart_baudrate = Gnss_UartBaudrateGet(instance);
        return 0;
    }

    s_config.baudrate = baudrate;
    s_status.uart_baudrate = Gnss_UartBaudrateGet(instance);
    Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
    return 0;
}

int GnssNeoM9n_WaitUartConfigSettle(uint8_t instance, uint32_t minimum_wait_ms,
                                    uint32_t stream_timeout_ms)
{
    if (minimum_wait_ms < GNSS_UART_CONFIG_SETTLE_MS)
    {
        return -1;
    }
    Gnss_ProcessDelayMs(instance, minimum_wait_ms);
    if ((s_uart_baud_changed != 0U) &&
        (Gnss_UbxFrameWait(instance, s_uart_baseline_ubx_frames,
                           stream_timeout_ms) == 0U))
    {
        return -2;
    }
    s_uart_baud_changed = 0U;
    return 0;
}

int GnssNeoM9n_ConfigDynamicModel(uint8_t instance, uint8_t layers, uint8_t dyn_model)
{
    int result;
    const GnssCfgItem_t items[] =
    {
        {GNSS_CFG_NAVSPG_DYNMODEL, dyn_model, GNSS_CFG_ITEM_TYPE_E1}
    };

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (Gnss_IsDynModelValid(dyn_model) == 0U)
    {
        return -1;
    }

    /*
     * Airborne <4g 适合高动态场景，会让 GNSS 内部运动限制更宽松，
     * 更不容易因为高速/高动态导致解无效。
     * 代价是低动态或静止时报告的位置标准差可能更大。
     * 本项目认为“数据中断比精度稍差更不可接受”，因此默认建议 Airborne <4g。
     * 本函数只改动态模型，不修改 minCNO、minElev、pAcc、PDOP 等滤波门限。
     */
    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.dynamic_model = dyn_model;
    }
    return result;
}

int GnssNeoM9n_ConfigSignals(uint8_t instance, uint8_t layers, uint32_t constellation_mask)
{
    int result;
    const GnssCfgItem_t items_template[] =
    {
        {GNSS_CFG_SIGNAL_GPS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GPS_L1CA_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GAL_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GAL_E1_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_BDS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_BDS_B1_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GLO_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GLO_L1_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_QZSS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_QZSS_L1CA_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_SBAS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_SBAS_L1CA_ENA, 0U, GNSS_CFG_ITEM_TYPE_L}
    };
    GnssCfgItem_t items[sizeof(items_template) / sizeof(items_template[0])];

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((constellation_mask == 0UL) ||
        ((constellation_mask & ~(GNSS_CONSTELLATION_GPS |
                                 GNSS_CONSTELLATION_GALILEO |
                                 GNSS_CONSTELLATION_BDS |
                                 GNSS_CONSTELLATION_GLONASS |
                                 GNSS_CONSTELLATION_QZSS |
                                 GNSS_CONSTELLATION_SBAS)) != 0UL))
    {
        return -1;
    }

    memcpy(items, items_template, sizeof(items));
    items[0].value = ((constellation_mask & GNSS_CONSTELLATION_GPS) != 0UL) ? 1U : 0U;
    items[1].value = items[0].value;
    items[2].value = ((constellation_mask & GNSS_CONSTELLATION_GALILEO) != 0UL) ? 1U : 0U;
    items[3].value = items[2].value;
    items[4].value = ((constellation_mask & GNSS_CONSTELLATION_BDS) != 0UL) ? 1U : 0U;
    items[5].value = items[4].value;
    items[6].value = ((constellation_mask & GNSS_CONSTELLATION_GLONASS) != 0UL) ? 1U : 0U;
    items[7].value = items[6].value;
    items[8].value = ((constellation_mask & GNSS_CONSTELLATION_QZSS) != 0UL) ? 1U : 0U;
    items[9].value = items[8].value;
    items[10].value = ((constellation_mask & GNSS_CONSTELLATION_SBAS) != 0UL) ? 1U : 0U;
    items[11].value = items[10].value;

    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.constellations_mask = constellation_mask;
        Gnss_ProcessDelayMs(instance, GNSS_SIGNAL_RESET_WAIT_MS);
    }

    return result;
}

int GnssNeoM9n_ConfigSignalsGpsBdsGal(uint8_t instance, uint8_t layers)
{
    int result;
    const GnssCfgItem_t items[] =
    {
        {GNSS_CFG_SIGNAL_GPS_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GPS_L1CA_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_BDS_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_BDS_B1_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GAL_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GAL_E1_ENA, 1U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GLO_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_GLO_L1_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_QZSS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_QZSS_L1CA_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_SBAS_ENA, 0U, GNSS_CFG_ITEM_TYPE_L},
        {GNSS_CFG_SIGNAL_SBAS_L1CA_ENA, 0U, GNSS_CFG_ITEM_TYPE_L}
    };

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    /*
     * 中国地区测试配置：GPS + BeiDou + Galileo。
     * u-blox 这里不是“优先级配置”，而是“启用哪些星座/信号”。
     * BeiDou 在中国地区是重要主力星座，GPS 作为基础星座保留，
     * Galileo 用于增加可用卫星数和连续性。
     * GLONASS、QZSS、SBAS 默认关闭以减少变量。
     * 如果后续实测 numSV 不足或掉 fix，再考虑新增函数启用 GLONASS。
     * 修改 CFG-SIGNAL 组会触发 GNSS 子系统复位；调用后应等待 ACK，
     * 并至少延时 GNSS_SIGNAL_RESET_WAIT_MS，再继续发送其他 GNSS 配置命令。
     * 本函数不配置更严格的滤波门限，避免因为门限过严导致数据中断。
     */
    result = GnssNeoM9n_SendValset(instance, layers,
                                   items,
                                   (uint8_t)(sizeof(items) / sizeof(items[0])),
                                   GNSS_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        Gnss_ConfigCacheStoreOnRamSuccess(instance, layers, items, (uint8_t)(sizeof(items) / sizeof(items[0])));
        s_config.constellations_mask = GNSS_CONSTELLATION_GPS |
                                       GNSS_CONSTELLATION_BDS |
                                       GNSS_CONSTELLATION_GALILEO;
        Gnss_ProcessDelayMs(instance, GNSS_SIGNAL_RESET_WAIT_MS);
    }

    return result;
}

int GnssNeoM9n_WaitForNewNavPvt(uint8_t instance, uint32_t baseline_sequence,
                                uint64_t minimum_receive_timestamp_us,
                                uint32_t timeout_ms)
{
    GnssNeoM9nData data;
    uint32_t start_ms = PlatformTime_Ms();
    uint32_t poll;

    SILVERSTAR_ASSERT_OBJECT(&s_data, GnssNeoM9nData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (poll = 0U; poll < GNSS_MAX_WAIT_POLL_ITERATIONS; poll++)
    {
        (void)GnssNeoM9n_Process(instance, PlatformTime_Ms());
        (void)GnssNeoM9n_GetData(instance, &data);
        if ((data.pvtSequence > baseline_sequence) &&
            (data.lastUpdate_us > minimum_receive_timestamp_us))
        {
            return 0;
        }
        PlatformTime_DelayMs(1U);
        if ((PlatformTime_Ms() - start_ms) >= timeout_ms)
        {
            break;
        }
    }
    return -2;
}

int GnssNeoM9n_SaveConfig(uint8_t instance, uint8_t layers, uint8_t *saved_count)
{
    int result;

    SILVERSTAR_ASSERT_OBJECT(s_config_cache, GnssCfgItem_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (saved_count != NULL)
    {
        *saved_count = 0U;
    }

    if (((layers & (GNSS_CFG_LAYER_BBR | GNSS_CFG_LAYER_FLASH)) == 0U) ||
        ((layers & GNSS_CFG_LAYER_RAM) != 0U) ||
        ((layers & (uint8_t)(~GNSS_CFG_LAYER_ALL)) != 0U))
    {
        return -1;
    }

    if (s_config_cache_count == 0U)
    {
        return -4;
    }

    result = GnssNeoM9n_SendValset(instance, layers,
                                   s_config_cache,
                                   s_config_cache_count,
                                   GNSS_SAVE_ACK_TIMEOUT_MS);
    if (result == 0)
    {
        if (saved_count != NULL)
        {
            *saved_count = s_config_cache_count;
        }
        s_config.last_write_layers = Gnss_PersistFromLayers(instance, layers);
    }

    return result;
}

uint8_t GnssNeoM9n_GetSaveCacheCount(uint8_t instance)
{
    return s_config_cache_count;
}

uint8_t GnssNeoM9n_IsBaudCached(uint8_t instance)
{
    return Gnss_ConfigCacheContainsKey(instance, GNSS_CFG_UART1_BAUDRATE);
}

int GnssNeoM9n_ConfigPreset(uint8_t instance, uint8_t layers, uint32_t baudrate, uint8_t nav_rate_hz)
{
    GnssNeoM9nData data;
    uint32_t baseline_sequence;
    uint64_t signal_complete_us;

    SILVERSTAR_ASSERT_OBJECT(&s_config, GnssNeoM9nConfigSnapshot,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    /*
     * 固定顺序：UART、链路稳定等待、协议、NAV-PVT、导航率、动态模型、
     * 星座/信号、等待严格晚于信号配置的新NAV-PVT。信号配置必须是最后
     * 一个配置写入，之后不得再发送配置命令。
     */
    if (GnssNeoM9n_ConfigUartBaudrate(instance, layers, baudrate) != 0)
    {
        return -1;
    }
    if (GnssNeoM9n_WaitUartConfigSettle(instance,
            GNSS_UART_CONFIG_SETTLE_MS,
            GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS) != 0)
    {
        return -1;
    }
    if (GnssNeoM9n_ConfigOutputUbxOnly(instance, layers) != 0)
    {
        return -1;
    }

    if (GnssNeoM9n_ConfigNavPvtOutput(instance, layers, 1U) != 0)
    {
        return -1;
    }

    if (GnssNeoM9n_ConfigNavRate(instance, layers, nav_rate_hz) != 0)
    {
        return -1;
    }

    if (GnssNeoM9n_ConfigDynamicModel(instance, layers, GNSS_TARGET_DYNMODEL) != 0)
    {
        return -1;
    }

    (void)GnssNeoM9n_GetData(instance, &data);
    baseline_sequence = data.pvtSequence;
    if (GnssNeoM9n_ConfigSignalsGpsBdsGal(instance, layers) != 0)
    {
        return -1;
    }

    signal_complete_us = PlatformTime_Us();
    return GnssNeoM9n_WaitForNewNavPvt(instance,
        baseline_sequence, signal_complete_us,
        GNSS_SIGNAL_STREAM_RECOVERY_TIMEOUT_MS);
}

void GnssNeoM9n_StreamDiagnosticsGet(uint8_t instance,
    GnssNeoM9nStreamDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return; }
    diagnostics->ubx_frame_count = s_status.ubx_frames;
    diagnostics->ubx_checksum_error_count =
        s_status.ubx_checksum_error_count;
    diagnostics->nmea_sentence_count = s_status.nmea_sentence_count;
    diagnostics->nmea_checksum_ok_count =
        s_status.nmea_checksum_ok_count;
    diagnostics->nmea_checksum_error_count =
        s_status.nmea_checksum_error_count;
    diagnostics->unknown_byte_count = s_status.unknown_bytes;
    diagnostics->parser_resync_count = s_parser_resync_count;
}
