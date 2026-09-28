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
