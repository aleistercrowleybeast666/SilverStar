#ifndef __PROTOCOL_CRC16_H
#define __PROTOCOL_CRC16_H

#include <stdint.h>

uint16_t ProtocolCrc16_CcittFalse(const uint8_t *data, uint16_t len);

#endif