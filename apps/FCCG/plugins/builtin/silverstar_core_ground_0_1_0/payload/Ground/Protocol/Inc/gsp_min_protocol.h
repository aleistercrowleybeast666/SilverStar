#ifndef __GSP_MIN_PROTOCOL_H
#define __GSP_MIN_PROTOCOL_H

#include <stdint.h>

#define GSP_MIN_SOF1                     0xA5U
#define GSP_MIN_SOF2                     0x5AU

#define GSP_MIN_MAX_PAYLOAD_LEN          64U
#define GSP_MIN_MAX_FRAME_LEN            (6U + GSP_MIN_MAX_PAYLOAD_LEN)

typedef enum
{
    GSP_TYPE_GS_STATUS = 0x01U,
    GSP_TYPE_AIR_RX    = 0x02U,
    GSP_TYPE_AIR_TX    = 0x03U,
    GSP_TYPE_ACK       = 0x04U
} GspMinType;

typedef enum
{
    GSP_ACK_OK        = 0x00U,
    GSP_ACK_BAD_CRC   = 0x01U,
    GSP_ACK_BAD_LEN   = 0x02U,
    GSP_ACK_BAD_TYPE  = 0x03U,
    GSP_ACK_BAD_PARAM = 0x04U,
    GSP_ACK_BUSY      = 0x05U
} GspAckResult;

typedef enum
{
    GSP_GS_STATE_IDLE    = 0x00U,
    GSP_GS_STATE_INIT_OK = 0x01U,
    GSP_GS_STATE_RX_MODE = 0x02U,
    GSP_GS_STATE_TX_MODE = 0x03U,
    GSP_GS_STATE_ERROR   = 0x04U
} GspGsState;

typedef enum
{
    GSP_RADIO_STATE_NOT_INIT = 0x00U,
    GSP_RADIO_STATE_READY    = 0x01U,
    GSP_RADIO_STATE_RX       = 0x02U,
    GSP_RADIO_STATE_TX       = 0x03U,
    GSP_RADIO_STATE_BUSY     = 0x04U
} GspRadioState;

typedef struct
{
    uint8_t type;
    uint8_t payload_len;
    uint8_t payload[GSP_MIN_MAX_PAYLOAD_LEN];
} GspMinFrame;

typedef struct
{
    uint8_t gs_state;
    uint8_t radio_state;
    uint32_t tx_cnt;
    uint32_t rx_cnt;
    uint16_t crc_err_cnt;
} GspGsStatusPayload;

typedef struct
{
    uint8_t state;
    uint8_t fixed_index;
    uint8_t payload_index;
    uint8_t payload_len;
    uint16_t rx_crc;
    uint32_t crc_error_count;
    uint8_t payload[GSP_MIN_MAX_PAYLOAD_LEN];
    uint8_t crc_buf[2U + GSP_MIN_MAX_PAYLOAD_LEN];
} GspMinParser;

typedef enum
{
    GSP_PARSER_NO_FRAME = 0U,
    GSP_PARSER_FRAME_READY,
    GSP_PARSER_BAD_LENGTH,
    GSP_PARSER_BAD_CRC
} GspParserResult;

void GspMinParser_Init(GspMinParser *parser);
GspParserResult GspMinParser_InputByte(GspMinParser *parser, uint8_t byte, GspMinFrame *out_frame);
uint32_t GspMinParser_GetCrcErrorCount(const GspMinParser *parser);

uint16_t GspMin_BuildFrame(uint8_t type,
                           const uint8_t *payload,
                           uint8_t payload_len,
                           uint8_t *out_buf,
                           uint16_t out_size);

uint16_t GspMin_BuildAckFrame(uint8_t ack_type,
                              uint8_t result,
                              uint8_t detail,
                              uint8_t *out_buf,
                              uint16_t out_size);

uint16_t GspMin_BuildGsStatusFrame(const GspGsStatusPayload *status,
                                   uint8_t *out_buf,
                                   uint16_t out_size);

uint16_t GspMin_BuildAirRxFrame(int8_t rssi_dbm,
                                int8_t snr_q4,
                                const uint8_t *air_frame,
                                uint8_t air_len,
                                uint8_t *out_buf,
                                uint16_t out_size);

#endif
