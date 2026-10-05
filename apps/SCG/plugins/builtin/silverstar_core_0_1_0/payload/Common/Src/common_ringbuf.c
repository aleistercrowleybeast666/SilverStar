#include "common_ringbuf.h"
#include "silverstar_assert.h"

static uint16_t RingBuf_NextIndex(const ringbuf_t *rb, uint16_t index)
{
    index++;
    if (index >= rb->size)
    {
        index = 0U;
    }
    return index;
}

void RingBuf_Init(ringbuf_t *rb, uint8_t *buffer, uint16_t size)
{
    if ((rb == 0) || (buffer == 0) || (size < 2U))
    {
        return;
    }

    rb->buffer = buffer;
    rb->size   = size;
    rb->head   = 0U;
    rb->tail   = 0U;
    rb->discarded = 0U;
}

void RingBuf_Reset(ringbuf_t *rb)
{
    if (rb == 0)
    {
        return;
    }

    rb->head = 0U;
    rb->tail = 0U;
    rb->discarded = 0U;
}

uint16_t RingBuf_GetUsed(const ringbuf_t *rb)
{
    if (rb == 0)
    {
        return 0U;
    }

    if (rb->head >= rb->tail)
    {
        return (uint16_t)(rb->head - rb->tail);
    }
    else
    {
        return (uint16_t)(rb->size - rb->tail + rb->head);
    }
}

uint16_t RingBuf_GetFree(const ringbuf_t *rb)
{
    if (rb == 0)
    {
        return 0U;
    }

    return (uint16_t)(rb->size - RingBuf_GetUsed(rb) - 1U);
}

uint16_t RingBuf_Push(ringbuf_t *rb, const uint8_t *data, uint16_t len)
{
    uint16_t i;
    uint16_t free_len;
    uint16_t push_len;
    uint16_t discarded_len;

    if ((rb == 0) || (data == 0) || (len == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(rb, ringbuf_t, SILVERSTAR_ASSERT_MODULE_COMMON);

    free_len = RingBuf_GetFree(rb);
    push_len = len;

    if (push_len > free_len)
    {
        discarded_len = (uint16_t)(push_len - free_len);
        rb->discarded += discarded_len;
        push_len = free_len;
    }

    for (i = 0U; i < push_len; i++)
    {
        rb->buffer[rb->head] = data[i];
        rb->head = RingBuf_NextIndex(rb, rb->head);
    }

    return push_len;
}

uint16_t RingBuf_Pop(ringbuf_t *rb, uint8_t *data, uint16_t len)
{
    uint16_t i;
    uint16_t used_len;

    if ((rb == 0) || (data == 0) || (len == 0U))
    {
        return 0U;
    }

    used_len = RingBuf_GetUsed(rb);
    if (len > used_len)
    {
        len = used_len;
    }

    for (i = 0U; i < len; i++)
    {
        data[i] = rb->buffer[rb->tail];
        rb->tail = RingBuf_NextIndex(rb, rb->tail);
    }

    return len;
}

uint16_t RingBuf_GetLinearReadLen(const ringbuf_t *rb)
{
    if (rb == 0)
    {
        return 0U;
    }

    if (rb->head >= rb->tail)
    {
        return (uint16_t)(rb->head - rb->tail);
    }
    else
    {
        return (uint16_t)(rb->size - rb->tail);
    }
}

uint8_t *RingBuf_GetLinearReadPtr(ringbuf_t *rb)
{
    if (rb == 0)
    {
        return 0;
    }

    return &rb->buffer[rb->tail];
}

void RingBuf_Skip(ringbuf_t *rb, uint16_t len)
{
    uint16_t used_len;
    uint16_t i;

    if ((rb == 0) || (len == 0U))
    {
        return;
    }

    used_len = RingBuf_GetUsed(rb);
    if (len > used_len)
    {
        len = used_len;
    }

    for (i = 0U; i < len; i++)
    {
        rb->tail = RingBuf_NextIndex(rb, rb->tail);
    }
}

uint16_t RingBuf_GetDiscarded(const ringbuf_t *rb)
{
    if (rb == 0)
    {
        return 0U;
    }

    return rb->discarded;
}

void RingBuf_ResetDiscarded(ringbuf_t *rb)
{
    if (rb == 0)
    {
        return;
    }

    rb->discarded = 0U;
}
