#ifndef __COMMON_RINGBUF_H
#define __COMMON_RINGBUF_H

#include <stdint.h>

typedef struct
{
    uint8_t  *buffer;
    uint16_t  size;
    volatile uint16_t head;
    volatile uint16_t tail;
    volatile uint16_t discarded;  // 记录丢弃的数据数量
} ringbuf_t;

void RingBuf_Init(ringbuf_t *rb, uint8_t *buffer, uint16_t size);
void RingBuf_Reset(ringbuf_t *rb);

uint16_t RingBuf_GetUsed(const ringbuf_t *rb);
uint16_t RingBuf_GetFree(const ringbuf_t *rb);

uint16_t RingBuf_Push(ringbuf_t *rb, const uint8_t *data, uint16_t len);
uint16_t RingBuf_Pop(ringbuf_t *rb, uint8_t *data, uint16_t len);

uint16_t RingBuf_GetLinearReadLen(const ringbuf_t *rb);
uint8_t *RingBuf_GetLinearReadPtr(ringbuf_t *rb);
void RingBuf_Skip(ringbuf_t *rb, uint16_t len);

uint16_t RingBuf_GetDiscarded(const ringbuf_t *rb);  // 获取丢弃的字节数
void RingBuf_ResetDiscarded(ringbuf_t *rb);  // 置零丢弃字节数

#endif /* __COMMON_RINGBUF_H */
