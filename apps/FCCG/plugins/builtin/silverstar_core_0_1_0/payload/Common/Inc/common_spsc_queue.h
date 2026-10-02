#ifndef __COMMON_SPSC_QUEUE_H
#define __COMMON_SPSC_QUEUE_H

#include <stdint.h>

typedef struct
{
    uint8_t *storage;
    uint16_t capacity;
    uint16_t item_size;

    volatile uint16_t head;
    volatile uint16_t tail;
    /* Slot cursors wrap at capacity, independently of sequence counter wrap. */
    uint16_t head_index;
    uint16_t tail_index;

    volatile uint32_t push_count;
    volatile uint32_t pop_count;
    volatile uint32_t overflow_count;
} CommonSpscQueue;

typedef enum
{
    COMMON_SPSC_QUEUE_RESULT_OK = 0U,
    COMMON_SPSC_QUEUE_RESULT_EMPTY,
    COMMON_SPSC_QUEUE_RESULT_FULL,
    COMMON_SPSC_QUEUE_RESULT_BAD_PARAM
} CommonSpscQueueResult;

/* The caller owns at least capacity * item_size storage bytes. The storage,
 * capacity and item size remain immutable until an exclusive reinitialization.
 * Exactly one producer owns head/head_index; one consumer owns tail/tail_index.
 * Reset is exclusive. Count is a bounded advisory snapshot, not a reservation.
 * Target ports must provide ordered, atomic 16-bit sequence accesses; this
 * volatile/fence implementation is not a portable multi-threaded C queue. */
CommonSpscQueueResult CommonSpscQueue_Init(CommonSpscQueue *queue,
                                            void *storage,
                                            uint16_t capacity,
                                            uint16_t item_size);
CommonSpscQueueResult CommonSpscQueue_Push(CommonSpscQueue *queue,
                                            const void *item);
CommonSpscQueueResult CommonSpscQueue_Pop(CommonSpscQueue *queue,
                                           void *item);
uint16_t CommonSpscQueue_Count(const CommonSpscQueue *queue);
void CommonSpscQueue_Reset(CommonSpscQueue *queue);

#endif /* __COMMON_SPSC_QUEUE_H */
