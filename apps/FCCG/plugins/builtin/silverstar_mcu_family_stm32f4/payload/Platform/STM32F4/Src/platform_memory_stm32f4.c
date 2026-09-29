#include "platform_memory.h"

#include <stdint.h>

#define PLATFORM_MEMORY_DMA_START ((uintptr_t)0x20000000UL)
#define PLATFORM_MEMORY_DMA_END   ((uintptr_t)0x20020000UL)

uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length)
{
    const uintptr_t start = (uintptr_t)data;

    if ((data == NULL) || (length == 0U) ||
        (start < PLATFORM_MEMORY_DMA_START) ||
        (start >= PLATFORM_MEMORY_DMA_END))
    {
        return 0U;
    }
    return (uint8_t)(length <= (size_t)(PLATFORM_MEMORY_DMA_END - start));
}
