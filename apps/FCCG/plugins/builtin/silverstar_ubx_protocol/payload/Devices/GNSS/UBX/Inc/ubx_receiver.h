#ifndef __UBX_RECEIVER_H
#define __UBX_RECEIVER_H

#include <stdint.h>

#define UBX_RECEIVER_PAYLOAD_MAX 512U
#define UBX_RECEIVER_TX_MAX 80U
#define UBX_RECEIVER_INPUT_MAX 512U
#define UBX_RECEIVER_ITEMS_MAX 12U
#define UBX_RECEIVER_RETRIES_MAX 3U
#define UBX_RECEIVER_LAYER_RAM 0U
#define UBX_RECEIVER_LAYER_BBR 1U
#define UBX_RECEIVER_LAYER_FLASH 2U

typedef enum
{
    UBX_RECEIVER_OK = 0,
    UBX_RECEIVER_BUSY,
    UBX_RECEIVER_INVALID_ARGUMENT,
    UBX_RECEIVER_IO_ERROR,
    UBX_RECEIVER_TIMEOUT,
    UBX_RECEIVER_WRONG_MODEL,
    UBX_RECEIVER_NAK,
    UBX_RECEIVER_BAD_FRAME,
    UBX_RECEIVER_VERIFY_FAILED,
    UBX_RECEIVER_UNSUPPORTED_LAYER,
    UBX_RECEIVER_TIME_ERROR,
    UBX_RECEIVER_DUPLICATE_EPOCH,
    UBX_RECEIVER_BAD_STATE
} UbxReceiverResult;

typedef enum
{
    UBX_RECEIVER_STOPPED = 0,
    UBX_RECEIVER_IDENTIFY,
    UBX_RECEIVER_READ_RAM,
    UBX_RECEIVER_WRITE_RAM,
    UBX_RECEIVER_VERIFY_RAM,
    UBX_RECEIVER_READ_PERSISTENT,
    UBX_RECEIVER_WRITE_PERSISTENT,
    UBX_RECEIVER_VERIFY_PERSISTENT,
    UBX_RECEIVER_VERIFY_SAMPLE,
    UBX_RECEIVER_READY,
    UBX_RECEIVER_FAILED
} UbxReceiverState;

typedef enum
{
    UBX_RECEIVER_NEO_M8N = 0,
    UBX_RECEIVER_NEO_M9N,
    UBX_RECEIVER_MAX_M10S,
    UBX_RECEIVER_NEO_F10N,
    UBX_RECEIVER_MODEL_COUNT
} UbxReceiverModel;

typedef struct
{
    const char *model;
    const char *protocol_version;
    uint32_t factory_baud;
    uint32_t target_baud;
    uint16_t measurement_ms;
    uint8_t dynamic_model;
    uint8_t legacy_configuration;
    uint8_t persistent_layers;
    uint8_t constellation_mask; /* System-neutral: GPS=1, BDS=2, Galileo=4, GLO=8. */
    uint8_t glonass_supported;
} UbxReceiverProfile;

typedef UbxReceiverResult (*UbxReceiverSend)(void *context,
    const uint8_t *frame, uint16_t length);
typedef UbxReceiverResult (*UbxReceiverSetBaud)(void *context, uint32_t baud);

typedef struct
{
    void *context;
    UbxReceiverSend send;
    UbxReceiverSetBaud set_baud;
} UbxReceiverPort;

typedef struct
{
    uint64_t epoch_ms;
    uint64_t receive_timestamp_us;
    uint32_t itow_ms;
    uint32_t sequence;
    uint32_t source_generation;
    int32_t longitude_e7;
    int32_t latitude_e7;
    int32_t height_ellipsoid_mm;
    int32_t height_msl_mm;
    int32_t velocity_enu_mmps[3];
    uint32_t hacc_mm;
    uint32_t vacc_mm;
    uint32_t sacc_mmps;
    uint8_t fix_type;
    uint8_t flags;
    uint8_t satellites;
    uint8_t valid_solution;
} UbxReceiverSample;

typedef struct
{
    uint32_t baud;
    uint16_t valid_items;
    uint16_t measurement_ms;
    uint16_t navigation_cycles;
    uint8_t constellation_mask;
    uint8_t dynamic_model;
    uint8_t protocol_in;
    uint8_t protocol_out;
    uint8_t nav_pvt_rate;
    uint16_t response_length;
    uint8_t response_class;
    uint8_t response_id;
    uint8_t response_version;
} UbxReceiverReadback;

typedef struct
{
    UbxReceiverPort port;
    const UbxReceiverProfile *profile;
    UbxReceiverState state;
    UbxReceiverResult result;
    UbxReceiverSample latest;
    UbxReceiverReadback readback;
    uint64_t now_us;
    uint64_t deadline_us;
    uint64_t not_before_us;
    uint64_t week_offset_ms;
    uint32_t current_baud;
    uint32_t ram_write_count;
    uint32_t nvm_write_count;
    uint32_t checksum_errors;
    uint32_t malformed_frames;
    uint32_t unknown_frames;
    uint32_t stale_ack_count;
    uint32_t epoch_errors;
    uint32_t config_generation;
    uint32_t read_transaction_id;
    uint16_t payload_length;
    uint16_t payload_index;
    uint16_t skip_remaining;
    uint8_t parser_state;
    uint8_t msg_class;
    uint8_t msg_id;
    uint8_t checksum_a;
    uint8_t checksum_b;
    uint8_t received_checksum_a;
    uint8_t payload[UBX_RECEIVER_PAYLOAD_MAX];
    uint8_t item;
    uint8_t retries;
    uint8_t baud_candidate;
    uint8_t waiting;
    uint8_t requested_persistent_layer;
    uint8_t persistent_verified;
    uint8_t identified;
    uint8_t baud_reidentify;
    uint8_t legacy_reply[64];
    uint8_t legacy_length;
    uint8_t ack_id;
    uint8_t read_only;
} UbxReceiver;

const UbxReceiverProfile *UbxReceiver_ProfileGet(UbxReceiverModel model);
UbxReceiverResult UbxReceiver_Init(UbxReceiver *receiver,
    const UbxReceiverPort *port, UbxReceiverModel model, uint8_t exclusive_port,
    uint8_t persistent_layer, uint64_t now_us);
UbxReceiverResult UbxReceiver_Process(UbxReceiver *receiver, uint64_t now_us);
/* Starts a fresh RAM query. A mismatch fails; this path never sends VALSET or
 * legacy configuration writes and never treats ACK as readback evidence. */
UbxReceiverResult UbxReceiver_ConfigReadStart(UbxReceiver *receiver, uint64_t now_us);
/* Explicit maintenance only: compare every supported key in the selected
 * nonvolatile layer, write differing keys once, and verify by VALGET. */
UbxReceiverResult UbxReceiver_ConfigPersistStart(UbxReceiver *receiver,
    uint8_t persistent_layer, uint64_t now_us);
UbxReceiverResult UbxReceiver_Feed(UbxReceiver *receiver, const uint8_t *data,
    uint16_t length, uint64_t receive_us);
UbxReceiverResult UbxReceiver_FrameBuild(uint8_t msg_class, uint8_t msg_id,
    const uint8_t *payload, uint16_t length, uint8_t *frame,
    uint16_t capacity, uint16_t *frame_length);

#endif /* __UBX_RECEIVER_H */
