#include "common_spsc_queue.h"

#include <stddef.h>
#include <stdatomic.h>
#include <string.h>

#include "silverstar_assert.h"

#define COMMON_SPSC_QUEUE_CAPACITY_MAX 32767U

CommonSpscQueueResult CommonSpscQueue_Init(CommonSpscQueue *queue,
                                            void *storage,
                                            uint16_t capacity,
                                            uint16_t item_size)
{
    if ((queue == NULL) || (storage == NULL) ||
        (capacity == 0U) || (capacity > COMMON_SPSC_QUEUE_CAPACITY_MAX) ||
        (item_size == 0U))
    {
        return COMMON_SPSC_QUEUE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(queue, CommonSpscQueue,
                             SILVERSTAR_ASSERT_MODULE_COMMON);

    queue->storage = (uint8_t *)storage;
    queue->capacity = capacity;
    queue->item_size = item_size;
    CommonSpscQueue_Reset(queue);

    return COMMON_SPSC_QUEUE_RESULT_OK;
}

CommonSpscQueueResult CommonSpscQueue_Push(CommonSpscQueue *queue,
                                            const void *item)
{
    uint16_t head;
    uint16_t tail;
    uint16_t index;

    if ((queue == NULL) || (item == NULL) || (queue->storage == NULL) ||
        (queue->capacity == 0U) || (queue->item_size == 0U))
    {
        return COMMON_SPSC_QUEUE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(queue, CommonSpscQueue,
                             SILVERSTAR_ASSERT_MODULE_COMMON);

    head = queue->head;
    tail = queue->tail;
    if ((uint16_t)(head - tail) >= queue->capacity)
    {
        queue->overflow_count++;
        return COMMON_SPSC_QUEUE_RESULT_FULL;
    }

    index = queue->head_index;
    memcpy(&queue->storage[(uint32_t)index * queue->item_size],
           item,
           queue->item_size);
    queue->head_index = (uint16_t)((index + 1U) % queue->capacity);
    atomic_thread_fence(memory_order_seq_cst);
    queue->head = (uint16_t)(head + 1U);
    queue->push_count++;

    return COMMON_SPSC_QUEUE_RESULT_OK;
}

CommonSpscQueueResult CommonSpscQueue_Pop(CommonSpscQueue *queue,
                                           void *item)
{
    uint16_t head;
    uint16_t tail;
    uint16_t index;

    if ((queue == NULL) || (item == NULL) || (queue->storage == NULL) ||
        (queue->capacity == 0U) || (queue->item_size == 0U))
    {
        return COMMON_SPSC_QUEUE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(queue, CommonSpscQueue,
                             SILVERSTAR_ASSERT_MODULE_COMMON);

    tail = queue->tail;
    head = queue->head;
    if (tail == head)
    {
        return COMMON_SPSC_QUEUE_RESULT_EMPTY;
    }

    atomic_thread_fence(memory_order_seq_cst);
    index = queue->tail_index;
    memcpy(item,
           &queue->storage[(uint32_t)index * queue->item_size],
           queue->item_size);
    queue->tail_index = (uint16_t)((index + 1U) % queue->capacity);
    atomic_thread_fence(memory_order_seq_cst);
    queue->tail = (uint16_t)(tail + 1U);
    queue->pop_count++;

    return COMMON_SPSC_QUEUE_RESULT_OK;
}

uint16_t CommonSpscQueue_Count(const CommonSpscQueue *queue)
{
    uint16_t count;

    if ((queue == NULL) || (queue->storage == NULL) || (queue->capacity == 0U))
    {
        return 0U;
    }

    count = (uint16_t)(queue->head - queue->tail);
    return (count > queue->capacity) ? queue->capacity : count;
}

void CommonSpscQueue_Reset(CommonSpscQueue *queue)
{
    if (queue == NULL)
    {
        return;
    }

    queue->head = 0U;
    queue->tail = 0U;
    queue->head_index = 0U;
    queue->tail_index = 0U;
    queue->push_count = 0U;
    queue->pop_count = 0U;
    queue->overflow_count = 0U;
    atomic_thread_fence(memory_order_seq_cst);
}
