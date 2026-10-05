#ifndef __PC_BYTE_STREAM_H
#define __PC_BYTE_STREAM_H

#include <stdint.h>

/* UART and USB CDC implementations expose the same bounded byte stream. */
typedef enum
{
    PC_BYTE_STREAM_INIT_OK = 0,
    PC_BYTE_STREAM_INIT_HARDWARE_ERROR
} PcByteStreamInitResult;

typedef enum
{
    PC_BYTE_STREAM_WRITE_OK = 0,
    PC_BYTE_STREAM_WRITE_BUSY,
    PC_BYTE_STREAM_WRITE_ERROR
} PcByteStreamWriteResult;

PcByteStreamInitResult PcByteStream_Init(void);
uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity);
PcByteStreamWriteResult PcByteStream_Write(const uint8_t *data,
                                          uint16_t length);
void PcByteStream_OnUsbReceive(const uint8_t *data, uint16_t length);
uint32_t PcByteStream_OverflowCount_Get(void);

#endif /* __PC_BYTE_STREAM_H */
