#include "platform_memory.h"

#include <stdint.h>
#include "stm32h7xx.h"

#include "platform_memory_target.h"

#define PLATFORM_MEMORY_DMA_START ((uintptr_t)PLATFORM_MEMORY_DMA_SRAM_START)
#define PLATFORM_MEMORY_DMA_END   ((uintptr_t)PLATFORM_MEMORY_DMA_SRAM_END)

uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length)
{
    const uintptr_t start = (uintptr_t)data;

    if (((SCB->CCR & SCB_CCR_DC_Msk) != 0U) ||
        (data == NULL) || (length == 0U) ||
        (start < PLATFORM_MEMORY_DMA_START) ||
        (start >= PLATFORM_MEMORY_DMA_END))
    {
        return 0U;
    }
    return (uint8_t)(length <= (size_t)(PLATFORM_MEMORY_DMA_END - start));
}
