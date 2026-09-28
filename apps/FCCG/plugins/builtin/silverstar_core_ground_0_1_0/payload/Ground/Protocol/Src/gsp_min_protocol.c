#include "gsp_min_protocol.h"
#include <stddef.h>

#include <string.h>
#include "protocol_crc16.h"

#define GSP_PARSE_WAIT_SOF1             0U
#define GSP_PARSE_WAIT_SOF2             1U
#define GSP_PARSE_READ_FIXED            2U
#define GSP_PARSE_READ_PAYLOAD          3U
#define GSP_PARSE_READ_CRC_LO           4U
#define GSP_PARSE_READ_CRC_HI           5U

static void GspMinParser_Reset(GspMinParser *parser)
{
    parser->state = GSP_PARSE_WAIT_SOF1;
    parser->fixed_index = 0U;
    parser->payload_index = 0U;
    parser->payload_len = 0U;
    parser->rx_crc = 0U;
}

static void GspMin_PutU16Le(uint8_t *buf, uint16_t value)
{
    buf[0] = (uint8_t)(value & 0xFFU);
    buf[1] = (uint8_t)((value >> 8) & 0xFFU);
}

static void GspMin_PutU32Le(uint8_t *buf, uint32_t value)
{
    buf[0] = (uint8_t)(value & 0xFFU);
    buf[1] = (uint8_t)((value >> 8) & 0xFFU);
    buf[2] = (uint8_t)((value >> 16) & 0xFFU);
    buf[3] = (uint8_t)((value >> 24) & 0xFFU);
}

void GspMinParser_Init(GspMinParser *parser)
{
    if (parser == NULL)
    {
        return;
    }

    memset(parser, 0, sizeof(*parser));
    GspMinParser_Reset(parser);
}

uint32_t GspMinParser_GetCrcErrorCount(const GspMinParser *parser)
{
    if (parser == NULL)
    {
        return 0U;
    }

    return parser->crc_error_count;
}

GspParserResult GspMinParser_InputByte(GspMinParser *parser, uint8_t byte, GspMinFrame *out_frame)
{
    uint16_t crc_calc;

    if ((parser == NULL) || (out_frame == NULL))
    {
        return GSP_PARSER_NO_FRAME;
    }

    switch (parser->state)
    {
    case GSP_PARSE_WAIT_SOF1:
        if (byte == GSP_MIN_SOF1)
        {
            parser->state = GSP_PARSE_WAIT_SOF2;
        }
        break;

    case GSP_PARSE_WAIT_SOF2:
        if (byte == GSP_MIN_SOF2)
        {
            parser->state = GSP_PARSE_READ_FIXED;
            parser->fixed_index = 0U;
        }
        else if (byte != GSP_MIN_SOF1)
        {
            parser->state = GSP_PARSE_WAIT_SOF1;
        }
        break;

    case GSP_PARSE_READ_FIXED:
        parser->crc_buf[parser->fixed_index] = byte;
        parser->fixed_index++;

        if (parser->fixed_index >= 2U)
        {
            parser->payload_len = parser->crc_buf[1];
            if (parser->payload_len > GSP_MIN_MAX_PAYLOAD_LEN)
            {
                GspMinParser_Reset(parser);
                return GSP_PARSER_BAD_LENGTH;
            }

            parser->payload_index = 0U;
            parser->state = (parser->payload_len == 0U) ? GSP_PARSE_READ_CRC_LO : GSP_PARSE_READ_PAYLOAD;
        }
        break;

    case GSP_PARSE_READ_PAYLOAD:
        parser->payload[parser->payload_index] = byte;
        parser->crc_buf[2U + parser->payload_index] = byte;
        parser->payload_index++;

        if (parser->payload_index >= parser->payload_len)
        {
            parser->state = GSP_PARSE_READ_CRC_LO;
        }
        break;

    case GSP_PARSE_READ_CRC_LO:
        parser->rx_crc = (uint16_t)byte;
        parser->state = GSP_PARSE_READ_CRC_HI;
        break;

    case GSP_PARSE_READ_CRC_HI:
        parser->rx_crc |= (uint16_t)((uint16_t)byte << 8);
        crc_calc = ProtocolCrc16_CcittFalse(parser->crc_buf, (uint16_t)(2U + parser->payload_len));

        if (crc_calc == parser->rx_crc)
        {
            out_frame->type = parser->crc_buf[0];
            out_frame->payload_len = parser->payload_len;
            if (parser->payload_len > 0U)
            {
                memcpy(out_frame->payload, parser->payload, parser->payload_len);
            }

            GspMinParser_Reset(parser);
            return GSP_PARSER_FRAME_READY;
        }

        parser->crc_error_count++;
        GspMinParser_Reset(parser);
        return GSP_PARSER_BAD_CRC;

    default:
        GspMinParser_Reset(parser);
        break;
    }

    return GSP_PARSER_NO_FRAME;
}

uint16_t GspMin_BuildFrame(uint8_t type,
                           const uint8_t *payload,
                           uint8_t payload_len,
                           uint8_t *out_buf,
                           uint16_t out_size)
{
    uint16_t total_len;
    uint16_t crc;

    if ((out_buf == NULL) || (payload_len > GSP_MIN_MAX_PAYLOAD_LEN))
    {
        return 0U;
    }

    if ((payload_len > 0U) && (payload == NULL))
    {
        return 0U;
    }

    total_len = (uint16_t)(6U + payload_len);
    if (out_size < total_len)
    {
        return 0U;
    }

    out_buf[0] = GSP_MIN_SOF1;
    out_buf[1] = GSP_MIN_SOF2;
    out_buf[2] = type;
    out_buf[3] = payload_len;

    if (payload_len > 0U)
    {
        memcpy(&out_buf[4], payload, payload_len);
    }

    crc = ProtocolCrc16_CcittFalse(&out_buf[2], (uint16_t)(2U + payload_len));
    GspMin_PutU16Le(&out_buf[4U + payload_len], crc);

    return total_len;
}

uint16_t GspMin_BuildAckFrame(uint8_t ack_type,
                              uint8_t result,
                              uint8_t detail,
                              uint8_t *out_buf,
                              uint16_t out_size)
{
    uint8_t payload[3];

    payload[0] = ack_type;
    payload[1] = result;
    payload[2] = detail;

    return GspMin_BuildFrame(GSP_TYPE_ACK, payload, sizeof(payload), out_buf, out_size);
}

uint16_t GspMin_BuildGsStatusFrame(const GspGsStatusPayload *status,
                                   uint8_t *out_buf,
                                   uint16_t out_size)
{
    uint8_t payload[12];

    if (status == NULL)
    {
        return 0U;
    }

    payload[0] = status->gs_state;
    payload[1] = status->radio_state;
    GspMin_PutU32Le(&payload[2], status->tx_cnt);
    GspMin_PutU32Le(&payload[6], status->rx_cnt);
    GspMin_PutU16Le(&payload[10], status->crc_err_cnt);

    return GspMin_BuildFrame(GSP_TYPE_GS_STATUS, payload, sizeof(payload), out_buf, out_size);
}

uint16_t GspMin_BuildAirRxFrame(int8_t rssi_dbm,
                                int8_t snr_q4,
                                const uint8_t *air_frame,
                                uint8_t air_len,
                                uint8_t *out_buf,
                                uint16_t out_size)
{
    uint8_t payload[GSP_MIN_MAX_PAYLOAD_LEN];
    uint8_t payload_len;

    if ((air_frame == NULL) || (air_len == 0U))
    {
        return 0U;
    }

    payload_len = (uint8_t)(3U + air_len);
    if (payload_len > GSP_MIN_MAX_PAYLOAD_LEN)
    {
        return 0U;
    }

    payload[0] = (uint8_t)rssi_dbm;
    payload[1] = (uint8_t)snr_q4;
    payload[2] = air_len;
    memcpy(&payload[3], air_frame, air_len);

    return GspMin_BuildFrame(GSP_TYPE_AIR_RX, payload, payload_len, out_buf, out_size);
}
