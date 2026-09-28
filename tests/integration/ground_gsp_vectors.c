#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gsp_min_protocol.h"
#include "protocol_crc16.h"

static int Hex_Parse(const char *hex, uint8_t *bytes, uint16_t capacity)
{
    size_t length = strlen(hex);
    size_t index;
    unsigned int value;
    if (((length & 1U) != 0U) || (length / 2U > capacity))
    {
        return -1;
    }
    for (index = 0U; index < length / 2U; index++)
    {
        if (sscanf(&hex[index * 2U], "%2x", &value) != 1)
        {
            return -1;
        }
        bytes[index] = (uint8_t)value;
    }
    return (int)(length / 2U);
}

static void Hex_Print(const uint8_t *bytes, uint16_t length)
{
    uint16_t index;
    for (index = 0U; index < length; index++)
    {
        printf("%02x", bytes[index]);
    }
    putchar('\n');
}

int main(int argc, char **argv)
{
    uint8_t payload[GSP_MIN_MAX_PAYLOAD_LEN];
    uint8_t frame[GSP_MIN_MAX_FRAME_LEN];
    GspMinParser parser;
    GspMinFrame parsed;
    int payload_length;
    uint16_t frame_length = 0U;
    uint16_t index;
    unsigned long type;

    if (argc != 4)
    {
        return 2;
    }
    type = strtoul(argv[2], NULL, 0);
    payload_length = Hex_Parse(argv[3], payload, sizeof(payload));
    if ((type > 255UL) || (payload_length < 0))
    {
        return 3;
    }
    if (strcmp(argv[1], "crc") == 0)
    {
        printf("%04x\n", ProtocolCrc16_CcittFalse(payload, (uint16_t)payload_length));
        return 0;
    }
    if (strcmp(argv[1], "build") == 0)
    {
        frame_length = GspMin_BuildFrame(
            (uint8_t)type, payload, (uint8_t)payload_length, frame, sizeof(frame));
    }
    else if (strcmp(argv[1], "ack") == 0 && payload_length == 3)
    {
        frame_length = GspMin_BuildAckFrame(
            payload[0], payload[1], payload[2], frame, sizeof(frame));
    }
    else if (strcmp(argv[1], "status") == 0 && payload_length == 12)
    {
        GspGsStatusPayload status;
        status.gs_state = payload[0];
        status.radio_state = payload[1];
        status.tx_cnt = (uint32_t)payload[2] | ((uint32_t)payload[3] << 8)
            | ((uint32_t)payload[4] << 16) | ((uint32_t)payload[5] << 24);
        status.rx_cnt = (uint32_t)payload[6] | ((uint32_t)payload[7] << 8)
            | ((uint32_t)payload[8] << 16) | ((uint32_t)payload[9] << 24);
        status.crc_err_cnt = (uint16_t)payload[10] | (uint16_t)((uint16_t)payload[11] << 8);
        frame_length = GspMin_BuildGsStatusFrame(&status, frame, sizeof(frame));
    }
    else if (strcmp(argv[1], "airrx") == 0 && payload_length >= 4
             && payload[2] == (uint8_t)(payload_length - 3))
    {
        frame_length = GspMin_BuildAirRxFrame(
            (int8_t)payload[0], (int8_t)payload[1], &payload[3], payload[2],
            frame, sizeof(frame));
    }
    else if (strcmp(argv[1], "parse") == 0)
    {
        GspMinParser_Init(&parser);
        for (index = 0U; index < (uint16_t)payload_length; index++)
        {
            if (GspMinParser_InputByte(&parser, payload[index], &parsed)
                == GSP_PARSER_FRAME_READY)
            {
                printf("%u:", (unsigned int)parsed.type);
                Hex_Print(parsed.payload, parsed.payload_len);
                return 0;
            }
        }
        return 5;
    }
    else
    {
        return 4;
    }
    if (frame_length == 0U)
    {
        return 6;
    }
    Hex_Print(frame, frame_length);
    return 0;
}
