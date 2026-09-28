#ifndef __PC_BYTE_STREAM_H
#define __PC_BYTE_STREAM_H

#include <stdint.h>

/* UART and USB CDC implementations expose the same bounded byte stream. */
uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity);
uint16_t PcByteStream_Write(const uint8_t *data, uint16_t length);
void PcByteStream_OnUsbReceive(const uint8_t *data, uint16_t length);

#endif /* __PC_BYTE_STREAM_H */
