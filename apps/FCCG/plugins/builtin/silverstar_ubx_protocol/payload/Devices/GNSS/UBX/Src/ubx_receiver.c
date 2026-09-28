#include "ubx_receiver.h"
#include "silverstar_assert.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>

#define UBX_CFG_CLASS 0x06U
#define UBX_CFG_VALGET 0x8BU
#define UBX_CFG_VALSET 0x8AU
#define UBX_MON_CLASS 0x0AU
#define UBX_MON_VER 0x04U
#define UBX_NAV_CLASS 0x01U
#define UBX_NAV_PVT 0x07U
#define UBX_ACK_CLASS 0x05U
#define UBX_ACK_ACK 0x01U
#define UBX_ACK_NAK 0x00U
#define UBX_TIMEOUT_US 300000U
#define UBX_SAMPLE_TIMEOUT_US 5000000U
#define UBX_GPS_WEEK_MS 604800000UL
#define UBX_WEEK_EDGE_MS 10000UL
#define UBX_PVT_LENGTH 92U
#define UBX_SYNC1 0xB5U
#define UBX_SYNC2 0x62U
#define UBX_BAUD_CANDIDATES 4U
#define UBX_MODERN_ITEM_COUNT 12U
#define UBX_LEGACY_ITEM_COUNT 5U

/* Model-specific ceilings use conservative documented combinations. M9 keeps
 * the existing 25 Hz / 921600 baud baseline; M8, M10 and F10 use 5 Hz / 115200.
 * GPS/BDS/Galileo are explicit; F10 has no GLONASS key. F10 individual dual-band
 * settings remain paired receiver defaults; no L5 health override is written.
 * F10 keys/wait: UBX-23002975 R02 section 4.9.20 (ACK then 0.5 s). */
static const UbxReceiverProfile s_profiles[UBX_RECEIVER_MODEL_COUNT] =
{
    {"NEO-M8N", "PROTVER=18.", 9600U, 115200U, 200U, 0U, 1U, 0U, 7U, 1U},
    {"NEO-M9N", "PROTVER=27.", 38400U, 921600U, 40U, 8U, 0U, 6U, 7U, 1U},
    {"MAX-M10S", "PROTVER=34.", 9600U, 115200U, 200U, 0U, 0U, 2U, 7U, 1U},
    {"NEO-F10N", "PROTVER=40.", 38400U, 115200U, 200U, 0U, 0U, 6U, 7U, 0U}
};

static const uint32_t s_keys[UBX_MODERN_ITEM_COUNT] =
{
    0x10730001UL, /* CFG-UART1INPROT-UBX, L */
    0x10740001UL, /* CFG-UART1OUTPROT-UBX, L */
    0x10740002UL, /* CFG-UART1OUTPROT-NMEA, L */
    0x30210001UL, /* CFG-RATE-MEAS, U2 milliseconds */
    0x20910007UL, /* CFG-MSGOUT-UBX_NAV_PVT_UART1, U1 */
    0x20110021UL, /* CFG-NAVSPG-DYNMODEL, E1 */
    0x30210002UL, /* CFG-RATE-NAV, U2 navigation cycles */
    0x1031001FUL, /* CFG-SIGNAL-GPS_ENA, L */
    0x10310022UL, /* CFG-SIGNAL-BDS_ENA, L */
    0x10310021UL, /* CFG-SIGNAL-GAL_ENA, L */
    0x10310025UL, /* CFG-SIGNAL-GLO_ENA, L: M9/M10 only */
    0x40520001UL  /* CFG-UART1-BAUDRATE, U4: last, then reidentify */
};

static uint32_t UbxReceiver_U32Read(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8U) |
        ((uint32_t)data[2] << 16U) | ((uint32_t)data[3] << 24U);
}

static int32_t UbxReceiver_I32Read(const uint8_t *data)
{
    uint32_t raw = UbxReceiver_U32Read(data);
    int64_t signed_value = (raw > INT32_MAX) ?
        (int64_t)raw - 4294967296LL : (int64_t)raw;
    return (int32_t)signed_value;
}

static void UbxReceiver_U32Write(uint8_t *data, uint32_t value)
{
    uint8_t i;
    for (i = 0U; i < 4U; i++) { data[i] = (uint8_t)(value >> (8U * i)); }
}

static uint8_t UbxReceiver_KeyWidth(uint32_t key)
{
    uint8_t type = (uint8_t)(key >> 28U);
    if ((type == 1U) || (type == 2U)) { return 1U; }
    if (type == 3U) { return 2U; }
    if (type == 4U) { return 4U; }
    return 0U;
}

static uint32_t UbxReceiver_TargetValue(const UbxReceiver *receiver)
{
    switch (receiver->item)
    {
        case 2U: return 0U;
        case 3U: return receiver->profile->measurement_ms;
        case 5U: return receiver->profile->dynamic_model;
        case 10U: return 0U;
        case 11U: return receiver->profile->target_baud;
        default: return 1U;
    }
}

const UbxReceiverProfile *UbxReceiver_ProfileGet(UbxReceiverModel model)
{
    if ((uint32_t)model >= (uint32_t)UBX_RECEIVER_MODEL_COUNT)
    {
        return NULL;
    }
    return &s_profiles[model];
}

UbxReceiverResult UbxReceiver_FrameBuild(uint8_t msg_class, uint8_t msg_id,
    const uint8_t *payload, uint16_t length, uint8_t *frame,
    uint16_t capacity, uint16_t *frame_length)
{
    uint16_t i;
    uint8_t a = 0U;
    uint8_t b = 0U;
    if ((frame == NULL) || (frame_length == NULL) ||
        ((payload == NULL) && (length != 0U)) ||
        (length > UBX_RECEIVER_PAYLOAD_MAX) || ((uint32_t)length + 8U > capacity))
    {
        return UBX_RECEIVER_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(frame, uint8_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    frame[0] = UBX_SYNC1; frame[1] = UBX_SYNC2;
    frame[2] = msg_class; frame[3] = msg_id;
    frame[4] = (uint8_t)length; frame[5] = (uint8_t)(length >> 8U);
    if (length != 0U) { memcpy(&frame[6], payload, length); }
    for (i = 2U; i < length + 6U; i++) { a += frame[i]; b += a; }
    frame[length + 6U] = a; frame[length + 7U] = b;
    *frame_length = length + 8U;
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_Fail(UbxReceiver *receiver, UbxReceiverResult result)
{
    receiver->state = UBX_RECEIVER_FAILED;
    receiver->result = result;
    receiver->waiting = 0U;
    return result;
}

UbxReceiverResult UbxReceiver_Init(UbxReceiver *receiver,
    const UbxReceiverPort *port, UbxReceiverModel model, uint8_t exclusive_port,
    uint8_t persistent_layer, uint64_t now_us)
{
    const UbxReceiverProfile *profile = UbxReceiver_ProfileGet(model);
    if ((receiver == NULL) || (port == NULL) || (profile == NULL) ||
        (port->send == NULL) || (port->set_baud == NULL) || (exclusive_port == 0U) ||
        (persistent_layer > UBX_RECEIVER_LAYER_FLASH))
    {
        return UBX_RECEIVER_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((persistent_layer != UBX_RECEIVER_LAYER_RAM) &&
        ((profile->persistent_layers & (1U << persistent_layer)) == 0U))
    {
        return UBX_RECEIVER_UNSUPPORTED_LAYER;
    }
    memset(receiver, 0, sizeof(*receiver));
    receiver->port = *port;
    receiver->profile = profile;
    receiver->requested_persistent_layer = persistent_layer;
    receiver->state = UBX_RECEIVER_IDENTIFY;
    receiver->now_us = now_us;
    receiver->current_baud = profile->target_baud;
    receiver->config_generation = 1U;
    if (port->set_baud(port->context, receiver->current_baud) != UBX_RECEIVER_OK)
    {
        return UbxReceiver_Fail(receiver, UBX_RECEIVER_IO_ERROR);
    }
    return UBX_RECEIVER_BUSY;
}

static uint8_t UbxReceiver_IsWrite(UbxReceiverState state)
{
    return (state == UBX_RECEIVER_WRITE_RAM) || (state == UBX_RECEIVER_WRITE_PERSISTENT);
}

static uint8_t UbxReceiver_LayerGet(const UbxReceiver *receiver)
{
    return ((receiver->state == UBX_RECEIVER_READ_PERSISTENT) ||
            (receiver->state == UBX_RECEIVER_WRITE_PERSISTENT) ||
            (receiver->state == UBX_RECEIVER_VERIFY_PERSISTENT)) ?
        receiver->requested_persistent_layer : UBX_RECEIVER_LAYER_RAM;
}

static void UbxReceiver_NextItem(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t count = (receiver->profile->legacy_configuration != 0U) ?
        UBX_LEGACY_ITEM_COUNT : UBX_MODERN_ITEM_COUNT;
    uint8_t layer = UbxReceiver_LayerGet(receiver);
    receiver->item++;
    if ((receiver->profile->legacy_configuration == 0U) &&
        (receiver->profile->glonass_supported == 0U) && (receiver->item == 10U))
    { receiver->item++; }
    receiver->waiting = 0U;
    receiver->retries = 0U;
    receiver->state = (layer == UBX_RECEIVER_LAYER_RAM) ?
        UBX_RECEIVER_READ_RAM : UBX_RECEIVER_READ_PERSISTENT;
    if (receiver->item < count) { return; }
    receiver->item = 0U;
    if (receiver->read_only != 0U)
    { receiver->state = UBX_RECEIVER_READY; return; }
    if ((layer == UBX_RECEIVER_LAYER_RAM) &&
        (receiver->requested_persistent_layer != UBX_RECEIVER_LAYER_RAM))
    {
        receiver->state = UBX_RECEIVER_READ_PERSISTENT;
    }
    else
    {
        receiver->persistent_verified = (layer != UBX_RECEIVER_LAYER_RAM);
        receiver->state = UBX_RECEIVER_VERIFY_SAMPLE;
        receiver->deadline_us = receiver->now_us + UBX_SAMPLE_TIMEOUT_US;
        receiver->waiting = 1U;
    }
}

static UbxReceiverResult UbxReceiver_Send(UbxReceiver *receiver, uint8_t msg_class,
    uint8_t msg_id, const uint8_t *payload, uint16_t length)
{
    uint8_t frame[UBX_RECEIVER_TX_MAX];
    uint16_t frame_length;
    UbxReceiverResult result = UbxReceiver_FrameBuild(msg_class, msg_id, payload,
        length, frame, sizeof(frame), &frame_length);
    if (result != UBX_RECEIVER_OK) { return UbxReceiver_Fail(receiver, result); }
    result = receiver->port.send(receiver->port.context, frame, frame_length);
    if (result != UBX_RECEIVER_OK) { return UbxReceiver_Fail(receiver, result); }
    receiver->waiting = 1U;
    receiver->ack_id = msg_id;
    receiver->deadline_us = receiver->now_us + UBX_TIMEOUT_US;
    return UBX_RECEIVER_BUSY;
}

static UbxReceiverResult UbxReceiver_ModernRequest(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t payload[12] = {0U};
    uint8_t length = 8U;
    uint8_t id = UBX_CFG_VALGET;
    uint8_t layer = UbxReceiver_LayerGet(receiver);
    UbxReceiverResult result;
    payload[1] = layer;
    UbxReceiver_U32Write(&payload[4], s_keys[receiver->item]);
    if (UbxReceiver_IsWrite(receiver->state) != 0U)
    {
        id = UBX_CFG_VALSET;
        payload[1] = (uint8_t)(1U << layer);
        UbxReceiver_U32Write(&payload[8], UbxReceiver_TargetValue(receiver));
        length += UbxReceiver_KeyWidth(s_keys[receiver->item]);
        if (layer == UBX_RECEIVER_LAYER_RAM) { receiver->ram_write_count++; }
        else { receiver->nvm_write_count++; }
    }
    result = UbxReceiver_Send(receiver, UBX_CFG_CLASS, id, payload, length);
    if ((result == UBX_RECEIVER_BUSY) && (id == UBX_CFG_VALSET) &&
        (layer == UBX_RECEIVER_LAYER_RAM) && (receiver->item == 11U))
    {
        /* Baud ACK may be lost at the old speed; authority is new-speed
         * MON-VER and VALGET, never ACK reception alone. */
        receiver->current_baud = receiver->profile->target_baud;
        if (receiver->port.set_baud(receiver->port.context,
            receiver->current_baud) != UBX_RECEIVER_OK)
        {
            return UbxReceiver_Fail(receiver, UBX_RECEIVER_IO_ERROR);
        }
        receiver->baud_reidentify = 1U;
        receiver->not_before_us = receiver->now_us + 100000U;
        receiver->state = UBX_RECEIVER_IDENTIFY;
        receiver->waiting = 0U;
    }
    return result;
}

static UbxReceiverResult UbxReceiver_LegacyRequest(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    static const uint8_t ids[UBX_LEGACY_ITEM_COUNT] = {0x08U, 0x01U, 0x24U, 0x3EU, 0x00U};
    uint8_t payload[64] = {0U};
    uint8_t length = 0U;
    uint8_t id = ids[receiver->item];
    UbxReceiverResult result;
    if (receiver->item == 1U) { payload[0] = 1U; payload[1] = 7U; length = 2U; }
    if (receiver->item == 4U) { payload[0] = 1U; length = 1U; }
    if (receiver->state == UBX_RECEIVER_WRITE_RAM)
    {
        length = receiver->legacy_length;
        memcpy(payload, receiver->legacy_reply, length);
        receiver->ram_write_count++;
    }
    result = UbxReceiver_Send(receiver, UBX_CFG_CLASS, id, payload, length);
    if ((result == UBX_RECEIVER_BUSY) && (receiver->state == UBX_RECEIVER_WRITE_RAM) &&
        (receiver->item == 4U))
    {
        receiver->current_baud = receiver->profile->target_baud;
        if (receiver->port.set_baud(receiver->port.context,
            receiver->current_baud) != UBX_RECEIVER_OK)
        {
            return UbxReceiver_Fail(receiver, UBX_RECEIVER_IO_ERROR);
        }
        receiver->baud_reidentify = 1U;
        receiver->not_before_us = receiver->now_us + 100000U;
        receiver->state = UBX_RECEIVER_IDENTIFY;
        receiver->waiting = 0U;
    }
    return result;
}

static UbxReceiverResult UbxReceiver_Timeout(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    receiver->waiting = 0U;
    if (UbxReceiver_IsWrite(receiver->state) != 0U)
    {
        /* An ACK timeout does not prove a write failed. Read back instead of
         * repeating an uncertain nonvolatile write. */
        receiver->state = (receiver->state == UBX_RECEIVER_WRITE_RAM) ?
            UBX_RECEIVER_VERIFY_RAM : UBX_RECEIVER_VERIFY_PERSISTENT;
        if ((receiver->state == UBX_RECEIVER_VERIFY_RAM) &&
            (receiver->profile->legacy_configuration == 0U) &&
            (receiver->item >= 7U) && (receiver->item <= 10U))
        { receiver->not_before_us = receiver->now_us + 500000U; }
        receiver->retries = 0U;
        return UBX_RECEIVER_BUSY;
    }
    receiver->retries++;
    if (receiver->retries < UBX_RECEIVER_RETRIES_MAX) { return UBX_RECEIVER_BUSY; }
    if ((receiver->state == UBX_RECEIVER_IDENTIFY) && (receiver->baud_reidentify == 0U))
    {
        uint32_t baud;
        receiver->baud_candidate++;
        if (receiver->baud_candidate >= UBX_BAUD_CANDIDATES)
        {
            return UbxReceiver_Fail(receiver, UBX_RECEIVER_TIMEOUT);
        }
        baud = (receiver->baud_candidate == 1U) ? receiver->profile->factory_baud :
            ((receiver->baud_candidate == 2U) ? 9600U : 38400U);
        receiver->retries = 0U;
        receiver->current_baud = baud;
        if (receiver->port.set_baud(receiver->port.context, baud) != UBX_RECEIVER_OK)
        {
            return UbxReceiver_Fail(receiver, UBX_RECEIVER_IO_ERROR);
        }
        return UBX_RECEIVER_BUSY;
    }
    return UbxReceiver_Fail(receiver, UBX_RECEIVER_TIMEOUT);
}

UbxReceiverResult UbxReceiver_Process(UbxReceiver *receiver, uint64_t now_us)
{
    if ((receiver == NULL) || (receiver->profile == NULL)) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (now_us < receiver->now_us) { return UbxReceiver_Fail(receiver, UBX_RECEIVER_TIME_ERROR); }
    receiver->now_us = now_us;
    if (receiver->state == UBX_RECEIVER_READY) { return UBX_RECEIVER_OK; }
    if (receiver->state == UBX_RECEIVER_FAILED) { return receiver->result; }
    if (receiver->state == UBX_RECEIVER_STOPPED) { return UBX_RECEIVER_BAD_STATE; }
    if (now_us < receiver->not_before_us) { return UBX_RECEIVER_BUSY; }
    if (receiver->waiting != 0U)
    {
        if (now_us < receiver->deadline_us) { return UBX_RECEIVER_BUSY; }
        if (receiver->state == UBX_RECEIVER_VERIFY_SAMPLE)
        {
            return UbxReceiver_Fail(receiver, UBX_RECEIVER_TIMEOUT);
        }
        return UbxReceiver_Timeout(receiver);
    }
    if (receiver->state == UBX_RECEIVER_IDENTIFY)
    {
        return UbxReceiver_Send(receiver, UBX_MON_CLASS, UBX_MON_VER, NULL, 0U);
    }
    if (receiver->profile->legacy_configuration != 0U) { return UbxReceiver_LegacyRequest(receiver); }
    return UbxReceiver_ModernRequest(receiver);
}

UbxReceiverResult UbxReceiver_ConfigReadStart(UbxReceiver *receiver, uint64_t now_us)
{
    if ((receiver == NULL) || (receiver->profile == NULL)) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    if (receiver->state != UBX_RECEIVER_READY) { return UBX_RECEIVER_BAD_STATE; }
    if (now_us < receiver->now_us) { return UBX_RECEIVER_TIME_ERROR; }
    memset(&receiver->readback, 0, sizeof(receiver->readback));
    receiver->read_transaction_id++;
    receiver->read_only = 1U;
    receiver->item = 0U; receiver->retries = 0U; receiver->waiting = 0U;
    receiver->state = UBX_RECEIVER_READ_RAM;
    receiver->now_us = now_us;
    return UBX_RECEIVER_BUSY;
}

UbxReceiverResult UbxReceiver_ConfigPersistStart(UbxReceiver *receiver,
    uint8_t persistent_layer, uint64_t now_us)
{
    if ((receiver == NULL) || (receiver->profile == NULL)) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (receiver->state != UBX_RECEIVER_READY) { return UBX_RECEIVER_BAD_STATE; }
    if ((persistent_layer == UBX_RECEIVER_LAYER_RAM) ||
        (persistent_layer > UBX_RECEIVER_LAYER_FLASH) ||
        ((receiver->profile->persistent_layers & (1U << persistent_layer)) == 0U))
    { return UBX_RECEIVER_UNSUPPORTED_LAYER; }
    if (now_us < receiver->now_us) { return UBX_RECEIVER_TIME_ERROR; }
    receiver->requested_persistent_layer = persistent_layer;
    receiver->persistent_verified = 0U;
    receiver->read_only = 0U;
    receiver->item = 0U; receiver->retries = 0U; receiver->waiting = 0U;
    receiver->state = UBX_RECEIVER_READ_PERSISTENT;
    receiver->now_us = now_us;
    return UBX_RECEIVER_BUSY;
}

static void UbxReceiver_ReadbackStore(UbxReceiver *receiver, uint8_t item, uint32_t value)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    UbxReceiverReadback *readback = &receiver->readback;
    readback->response_length = receiver->payload_length;
    readback->response_class = receiver->msg_class;
    readback->response_id = receiver->msg_id;
    readback->response_version = receiver->profile->legacy_configuration == 0U ? receiver->payload[0] : 0U;
    readback->valid_items |= (uint16_t)(1U << item);
    switch (item)
    {
        case 0U: readback->protocol_in = (uint8_t)value; break;
        case 1U: readback->protocol_out = (uint8_t)((readback->protocol_out & 2U) | (value & 1U)); break;
        case 2U: readback->protocol_out = (uint8_t)((readback->protocol_out & 1U) | ((value & 1U) << 1U)); break;
        case 3U: readback->measurement_ms = (uint16_t)value; break;
        case 4U: readback->nav_pvt_rate = (uint8_t)value; break;
        case 5U: readback->dynamic_model = (uint8_t)value; break;
        case 6U: readback->navigation_cycles = (uint16_t)value; break;
        case 7U: case 8U: case 9U: case 10U:
        {
            uint8_t bit = (uint8_t)(1U << (item - 7U));
            readback->constellation_mask = (uint8_t)((readback->constellation_mask & (uint8_t)~bit) |
                ((value != 0U) ? bit : 0U));
            break;
        }
        case 11U: readback->baud = value; break;
        default: break;
    }
}

static uint8_t UbxReceiver_TextContains(const uint8_t *data, uint16_t length,
    const char *text)
{
    uint16_t i;
    uint16_t size = (uint16_t)strlen(text);
    if (size > length) { return 0U; }
    for (i = 0U; i <= length - size; i++)
    {
        if (memcmp(&data[i], text, size) == 0) { return 1U; }
    }
    return 0U;
}

static UbxReceiverResult UbxReceiver_IdentityReceive(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((receiver->payload_length < 40U) || ((receiver->payload_length - 40U) % 30U != 0U))
    {
        receiver->malformed_frames++;
        return UBX_RECEIVER_BAD_FRAME;
    }
    if ((UbxReceiver_TextContains(receiver->payload, receiver->payload_length,
        receiver->profile->model) == 0U) ||
        (UbxReceiver_TextContains(receiver->payload, receiver->payload_length,
        receiver->profile->protocol_version) == 0U))
    {
        return UbxReceiver_Fail(receiver, UBX_RECEIVER_WRONG_MODEL);
    }
    if (receiver->state != UBX_RECEIVER_IDENTIFY) { return UBX_RECEIVER_OK; }
    receiver->identified = 1U;
    receiver->waiting = 0U;
    receiver->retries = 0U;
    receiver->state = (receiver->baud_reidentify != 0U) ?
        UBX_RECEIVER_VERIFY_RAM : UBX_RECEIVER_READ_RAM;
    receiver->baud_reidentify = 0U;
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_ValgetReceive(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t width = UbxReceiver_KeyWidth(s_keys[receiver->item]);
    uint32_t actual = 0U;
    uint8_t i;
    uint8_t verify = (receiver->state == UBX_RECEIVER_VERIFY_RAM) ||
                     (receiver->state == UBX_RECEIVER_VERIFY_PERSISTENT);
    if ((receiver->state != UBX_RECEIVER_READ_RAM) &&
        (receiver->state != UBX_RECEIVER_READ_PERSISTENT) && (verify == 0U))
    {
        receiver->unknown_frames++;
        return UBX_RECEIVER_BUSY;
    }
    if ((receiver->payload_length != 8U + width) || (receiver->payload[0] != 1U) ||
        (receiver->payload[1] != UbxReceiver_LayerGet(receiver)) ||
        (receiver->payload[2] != 0U) || (receiver->payload[3] != 0U) ||
        (UbxReceiver_U32Read(&receiver->payload[4]) != s_keys[receiver->item]))
    {
        receiver->malformed_frames++;
        return UBX_RECEIVER_BAD_FRAME;
    }
    for (i = 0U; i < width; i++) { actual |= (uint32_t)receiver->payload[8U + i] << (8U * i); }
    if (UbxReceiver_LayerGet(receiver) == UBX_RECEIVER_LAYER_RAM)
    { UbxReceiver_ReadbackStore(receiver, receiver->item, actual); }
    receiver->waiting = 0U;
    receiver->retries = 0U;
    if (actual == UbxReceiver_TargetValue(receiver)) { UbxReceiver_NextItem(receiver); }
    else if ((verify != 0U) || (receiver->read_only != 0U))
    { return UbxReceiver_Fail(receiver, UBX_RECEIVER_VERIFY_FAILED); }
    else
    {
        receiver->state = (UbxReceiver_LayerGet(receiver) == UBX_RECEIVER_LAYER_RAM) ?
            UBX_RECEIVER_WRITE_RAM : UBX_RECEIVER_WRITE_PERSISTENT;
    }
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_LegacySignalsResolve(UbxReceiver *receiver,
    uint8_t *expected, uint8_t length)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t index;
    uint8_t seen = 0U;
    uint8_t known = 0U;
    if ((length < 4U) || (expected[0] != 0U) || (expected[3] > 7U) ||
        (length != 4U + 8U * expected[3])) { return UBX_RECEIVER_BAD_FRAME; }
    for (index = 0U; index < expected[3]; index++)
    {
        uint8_t offset = (uint8_t)(4U + 8U * index);
        uint8_t id = expected[offset];
        uint8_t bit = (id == 0U) ? 1U : (id == 3U) ? 2U :
            (id == 2U) ? 4U : (id == 6U) ? 8U : 0U;
        if ((id > 6U) || ((seen & (1U << id)) != 0U)) { return UBX_RECEIVER_BAD_FRAME; }
        seen |= (uint8_t)(1U << id);
        known |= bit;
        if (bit != 0U)
        {
            expected[offset+4U] = (uint8_t)((expected[offset+4U] & 0xFEU) |
                (((receiver->profile->constellation_mask & bit) != 0U) ? 1U : 0U));
        }
    }
    return ((known & receiver->profile->constellation_mask) == receiver->profile->constellation_mask) ?
        UBX_RECEIVER_OK : UBX_RECEIVER_VERIFY_FAILED;
}

static void UbxReceiver_LegacyReadbackStore(UbxReceiver *receiver, uint8_t length)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    const uint8_t *payload = receiver->payload;
    switch (receiver->item)
    {
        case 0U:
            UbxReceiver_ReadbackStore(receiver, 3U, (uint32_t)payload[0] | ((uint32_t)payload[1] << 8U));
            UbxReceiver_ReadbackStore(receiver, 6U, (uint32_t)payload[2] | ((uint32_t)payload[3] << 8U));
            break;
        case 1U: UbxReceiver_ReadbackStore(receiver, 4U, payload[3]); break;
        case 2U: UbxReceiver_ReadbackStore(receiver, 5U, payload[2]); break;
        case 3U:
        {
            uint8_t offset;
            for (offset = 4U; offset + 8U <= length; offset += 8U)
            {
                uint8_t id = payload[offset];
                uint8_t item = (id == 0U) ? 7U : (id == 3U) ? 8U :
                    (id == 2U) ? 9U : (id == 6U) ? 10U : 0U;
                if (item != 0U) { UbxReceiver_ReadbackStore(receiver, item, payload[offset+4U] & 1U); }
            }
            break;
        }
        case 4U:
            UbxReceiver_ReadbackStore(receiver, 11U, UbxReceiver_U32Read(&payload[8]));
            UbxReceiver_ReadbackStore(receiver, 0U, payload[12] & 1U);
            UbxReceiver_ReadbackStore(receiver, 1U, payload[14] & 1U);
            UbxReceiver_ReadbackStore(receiver, 2U, (payload[14] >> 1U) & 1U);
            break;
        default: break;
    }
}

static UbxReceiverResult UbxReceiver_LegacyReceive(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    static const uint8_t ids[UBX_LEGACY_ITEM_COUNT] = {0x08U, 0x01U, 0x24U, 0x3EU, 0x00U};
    static const uint8_t lengths[UBX_LEGACY_ITEM_COUNT] = {6U, 8U, 36U, 0U, 20U};
    uint8_t expected[64];
    uint8_t length = lengths[receiver->item];
    uint8_t verify = (receiver->state == UBX_RECEIVER_VERIFY_RAM);
    if (((receiver->state != UBX_RECEIVER_READ_RAM) && (verify == 0U)) ||
        (receiver->msg_id != ids[receiver->item])) { return UBX_RECEIVER_BUSY; }
    if (receiver->item == 3U)
    {
        if (receiver->payload_length > sizeof(expected)) { return UBX_RECEIVER_BAD_FRAME; }
        length = (uint8_t)receiver->payload_length;
    }
    if (receiver->payload_length != length) { return UBX_RECEIVER_BAD_FRAME; }
    memcpy(expected, receiver->payload, length);
    switch (receiver->item)
    {
        case 0U:
            expected[0] = (uint8_t)receiver->profile->measurement_ms;
            expected[1] = (uint8_t)(receiver->profile->measurement_ms >> 8U);
            expected[2] = 1U; expected[3] = 0U; expected[4] = 1U; expected[5] = 0U;
            break;
        case 1U:
            if ((expected[0] != 1U) || (expected[1] != 7U)) { return UBX_RECEIVER_BAD_FRAME; }
            expected[3] = 1U;
            break;
        case 2U: expected[2] = receiver->profile->dynamic_model; break;
        case 3U:
        {
            UbxReceiverResult result = UbxReceiver_LegacySignalsResolve(receiver, expected, length);
            if (result != UBX_RECEIVER_OK) { return result; }
            break;
        }
        case 4U:
            if (expected[0] != 1U) { return UBX_RECEIVER_BAD_FRAME; }
            UbxReceiver_U32Write(&expected[8], receiver->profile->target_baud);
            expected[12] = 1U; expected[13] = 0U;
            expected[14] = 1U; expected[15] = 0U;
            break;
        default: return UBX_RECEIVER_INVALID_ARGUMENT;
    }
    receiver->waiting = 0U;
    receiver->retries = 0U;
    UbxReceiver_LegacyReadbackStore(receiver, length);
    if (memcmp(receiver->payload, expected, length) == 0) { UbxReceiver_NextItem(receiver); }
    else if ((verify != 0U) || (receiver->read_only != 0U))
    { return UbxReceiver_Fail(receiver, UBX_RECEIVER_VERIFY_FAILED); }
    else
    {
        if (receiver->item == 2U) { expected[0] = 1U; expected[1] = 0U; }
        memcpy(receiver->legacy_reply, expected, length);
        receiver->legacy_length = length;
        receiver->state = UBX_RECEIVER_WRITE_RAM;
    }
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_AckReceive(UbxReceiver *receiver)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((receiver->payload_length != 2U) || (receiver->msg_id > UBX_ACK_ACK))
    {
        receiver->malformed_frames++;
        return UBX_RECEIVER_BAD_FRAME;
    }
    if ((receiver->waiting == 0U) || (receiver->payload[0] != UBX_CFG_CLASS) ||
        (receiver->payload[1] != receiver->ack_id))
    {
        receiver->stale_ack_count++;
        return UBX_RECEIVER_BUSY;
    }
    if (receiver->msg_id == UBX_ACK_NAK) { return UbxReceiver_Fail(receiver, UBX_RECEIVER_NAK); }
    if (UbxReceiver_IsWrite(receiver->state) == 0U)
    {
        receiver->stale_ack_count++;
        return UBX_RECEIVER_BUSY;
    }
    receiver->state = (receiver->state == UBX_RECEIVER_WRITE_RAM) ?
        UBX_RECEIVER_VERIFY_RAM : UBX_RECEIVER_VERIFY_PERSISTENT;
    if ((receiver->state == UBX_RECEIVER_VERIFY_RAM) &&
        (((receiver->profile->legacy_configuration != 0U) && (receiver->item == 3U)) ||
         ((receiver->profile->legacy_configuration == 0U) &&
          (receiver->item >= 7U) && (receiver->item <= 10U))))
    { receiver->not_before_us = receiver->now_us + 500000U; }
    receiver->waiting = 0U;
    receiver->retries = 0U;
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_PvtReceive(UbxReceiver *receiver, uint64_t receive_us)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    UbxReceiverSample sample;
    uint32_t itow;
    uint64_t week_offset_ms = receiver->week_offset_ms;
    int32_t down;
    if (receiver->payload_length != UBX_PVT_LENGTH) { return UBX_RECEIVER_BAD_FRAME; }
    itow = UbxReceiver_U32Read(receiver->payload);
    if (itow >= UBX_GPS_WEEK_MS) { return UBX_RECEIVER_TIME_ERROR; }
    if (receiver->latest.sequence != 0U)
    {
        if (itow == receiver->latest.itow_ms) { return UBX_RECEIVER_DUPLICATE_EPOCH; }
        if (itow < receiver->latest.itow_ms)
        {
            if ((itow < UBX_WEEK_EDGE_MS) &&
                (receiver->latest.itow_ms > UBX_GPS_WEEK_MS - UBX_WEEK_EDGE_MS))
            {
                week_offset_ms += UBX_GPS_WEEK_MS;
            }
            else { receiver->epoch_errors++; return UBX_RECEIVER_TIME_ERROR; }
        }
    }
    memset(&sample, 0, sizeof(sample));
    sample.itow_ms = itow;
    sample.epoch_ms = week_offset_ms + itow;
    sample.receive_timestamp_us = receive_us;
    sample.sequence = receiver->latest.sequence + 1U;
    sample.source_generation = receiver->config_generation;
    sample.fix_type = receiver->payload[20]; sample.flags = receiver->payload[21];
    sample.satellites = receiver->payload[23];
    sample.longitude_e7 = UbxReceiver_I32Read(&receiver->payload[24]);
    sample.latitude_e7 = UbxReceiver_I32Read(&receiver->payload[28]);
    if ((sample.longitude_e7 < -1800000000L) || (sample.longitude_e7 > 1800000000L) ||
        (sample.latitude_e7 < -900000000L) || (sample.latitude_e7 > 900000000L))
    {
        return UBX_RECEIVER_BAD_FRAME;
    }
    sample.height_ellipsoid_mm = UbxReceiver_I32Read(&receiver->payload[32]);
    sample.height_msl_mm = UbxReceiver_I32Read(&receiver->payload[36]);
    sample.hacc_mm = UbxReceiver_U32Read(&receiver->payload[40]);
    sample.vacc_mm = UbxReceiver_U32Read(&receiver->payload[44]);
    sample.velocity_enu_mmps[0] = UbxReceiver_I32Read(&receiver->payload[52]);
    sample.velocity_enu_mmps[1] = UbxReceiver_I32Read(&receiver->payload[48]);
    down = UbxReceiver_I32Read(&receiver->payload[56]);
    if (down == INT32_MIN) { return UBX_RECEIVER_BAD_FRAME; }
    sample.velocity_enu_mmps[2] = -down;
    sample.sacc_mmps = UbxReceiver_U32Read(&receiver->payload[68]);
    sample.valid_solution = ((sample.flags & 1U) != 0U) &&
        ((sample.fix_type == 3U) || (sample.fix_type == 4U));
    receiver->week_offset_ms = week_offset_ms;
    receiver->latest = sample;
    if (receiver->state == UBX_RECEIVER_VERIFY_SAMPLE)
    {
        receiver->state = UBX_RECEIVER_READY;
        receiver->result = UBX_RECEIVER_OK;
        receiver->waiting = 0U;
    }
    return UBX_RECEIVER_OK;
}

static UbxReceiverResult UbxReceiver_Dispatch(UbxReceiver *receiver, uint64_t receive_us)
{
    if ((receiver->msg_class == UBX_MON_CLASS) && (receiver->msg_id == UBX_MON_VER))
    {
        return UbxReceiver_IdentityReceive(receiver);
    }
    if ((receiver->msg_class == UBX_NAV_CLASS) && (receiver->msg_id == UBX_NAV_PVT))
    {
        return UbxReceiver_PvtReceive(receiver, receive_us);
    }
    if (receiver->msg_class == UBX_ACK_CLASS) { return UbxReceiver_AckReceive(receiver); }
    if ((receiver->msg_class == UBX_CFG_CLASS) && (receiver->identified != 0U))
    {
        if (receiver->profile->legacy_configuration != 0U) { return UbxReceiver_LegacyReceive(receiver); }
        if (receiver->msg_id == UBX_CFG_VALGET) { return UbxReceiver_ValgetReceive(receiver); }
    }
    receiver->unknown_frames++;
    return UBX_RECEIVER_BUSY;
}

static UbxReceiverResult UbxReceiver_FrameFinish(UbxReceiver *receiver,
    uint8_t checksum_b, uint64_t receive_us)
{
    receiver->parser_state = 0U;
    if (receiver->payload_length > UBX_RECEIVER_PAYLOAD_MAX) { return UBX_RECEIVER_BAD_FRAME; }
    if ((receiver->checksum_a != receiver->received_checksum_a) ||
        (receiver->checksum_b != checksum_b))
    {
        receiver->checksum_errors++;
        return UBX_RECEIVER_BAD_FRAME;
    }
    return UbxReceiver_Dispatch(receiver, receive_us);
}

static UbxReceiverResult UbxReceiver_ByteReceive(UbxReceiver *receiver,
    uint8_t byte, uint64_t receive_us)
{
    SILVERSTAR_ASSERT_OBJECT(receiver, UbxReceiver, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (receiver->skip_remaining != 0U)
    {
        receiver->skip_remaining--;
        return UBX_RECEIVER_BUSY;
    }
    if (receiver->parser_state == 0U)
    {
        if (byte == UBX_SYNC1) { receiver->parser_state = 1U; }
        return UBX_RECEIVER_BUSY;
    }
    if (receiver->parser_state == 1U)
    {
        receiver->parser_state = (byte == UBX_SYNC2) ? 2U : ((byte == UBX_SYNC1) ? 1U : 0U);
        receiver->checksum_a = 0U; receiver->checksum_b = 0U;
        return UBX_RECEIVER_BUSY;
    }
    if (receiver->parser_state <= 6U)
    {
        receiver->checksum_a += byte;
        receiver->checksum_b += receiver->checksum_a;
    }
    switch (receiver->parser_state)
    {
        case 2U: receiver->msg_class = byte; receiver->parser_state = 3U; break;
        case 3U: receiver->msg_id = byte; receiver->parser_state = 4U; break;
        case 4U: receiver->payload_length = byte; receiver->parser_state = 5U; break;
        case 5U:
            receiver->payload_length |= (uint16_t)byte << 8U;
            receiver->payload_index = 0U;
            if (receiver->payload_length > UBX_RECEIVER_PAYLOAD_MAX)
            {
                receiver->malformed_frames++;
                receiver->skip_remaining = receiver->payload_length;
                receiver->parser_state = 7U;
                return UBX_RECEIVER_BAD_FRAME;
            }
            receiver->parser_state = (receiver->payload_length == 0U) ? 7U : 6U;
            break;
        case 6U:
            receiver->payload[receiver->payload_index++] = byte;
            if (receiver->payload_index == receiver->payload_length) { receiver->parser_state = 7U; }
            break;
        case 7U: receiver->received_checksum_a = byte; receiver->parser_state = 8U; break;
        case 8U: return UbxReceiver_FrameFinish(receiver, byte, receive_us);
        default: receiver->parser_state = 0U; return UBX_RECEIVER_BAD_STATE;
    }
    return UBX_RECEIVER_BUSY;
}

UbxReceiverResult UbxReceiver_Feed(UbxReceiver *receiver, const uint8_t *data,
    uint16_t length, uint64_t receive_us)
{
    uint16_t i;
    UbxReceiverResult result = UBX_RECEIVER_BUSY;
    if ((receiver == NULL) || (receiver->profile == NULL) || (data == NULL) ||
        (length > UBX_RECEIVER_INPUT_MAX)) { return UBX_RECEIVER_INVALID_ARGUMENT; }
    if (receive_us < receiver->now_us) { return UbxReceiver_Fail(receiver, UBX_RECEIVER_TIME_ERROR); }
    receiver->now_us = receive_us;
    for (i = 0U; i < length; i++)
    {
        UbxReceiverResult next = UbxReceiver_ByteReceive(receiver, data[i], receive_us);
        if (next != UBX_RECEIVER_BUSY) { result = next; }
        if (receiver->state == UBX_RECEIVER_FAILED) { return receiver->result; }
    }
    return result;
}
