#include "pc_byte_stream.h"
#include <stddef.h>

uint32_t PcByteStream_Session_Get(void) { return 0U; }
uint8_t PcByteStream_Session_Check(uint32_t session) { return (session == 0U) ? 1U : 0U; }
uint8_t PcByteStream_Session_Enter(uint32_t session, uint32_t *token)
{
    if (token == NULL) { return 0U; }
    *token = 0U;
    return PcByteStream_Session_Check(session);
}
void PcByteStream_Session_Exit(uint32_t token) { (void)token; }
uint16_t PcByteStream_ReadSession(uint8_t *buffer, uint16_t capacity, uint32_t *session)
{
    if (session == NULL) { return 0U; }
    *session = 0U;
    return PcByteStream_Read(buffer, capacity);
}
PcByteStreamWriteResult PcByteStream_WriteSession(const uint8_t *data,
    uint16_t length, uint32_t session)
{
    if (session != 0U) { return PC_BYTE_STREAM_WRITE_BUSY; }
    return PcByteStream_Write(data, length);
}
