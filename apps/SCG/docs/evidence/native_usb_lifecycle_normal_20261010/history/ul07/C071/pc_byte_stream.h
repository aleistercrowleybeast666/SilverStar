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
/* USB ISR publishes lifecycle changes; bridge parser/queues reset in main context. */
void PcByteStream_OnUsbReset(void);
uint8_t PcByteStream_ResetPending_Get(void);
uint32_t PcByteStream_OverflowCount_Get(void);
/* A session labels copied bytes and queued frames. Enter atomically validates
 * it and excludes lifecycle IRQs only across a bounded queue publication. */
uint32_t PcByteStream_Session_Get(void);
uint8_t PcByteStream_Session_Check(uint32_t session);
uint8_t PcByteStream_Session_Enter(uint32_t session, uint32_t *token);
void PcByteStream_Session_Exit(uint32_t token);
uint16_t PcByteStream_ReadSession(uint8_t *buffer, uint16_t capacity, uint32_t *session);
PcByteStreamWriteResult PcByteStream_WriteSession(const uint8_t *data,
    uint16_t length, uint32_t session);

#endif /* __PC_BYTE_STREAM_H */
