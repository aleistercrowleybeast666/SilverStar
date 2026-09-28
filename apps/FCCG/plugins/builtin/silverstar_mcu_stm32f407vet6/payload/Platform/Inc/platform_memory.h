#ifndef __PLATFORM_MEMORY_H
#define __PLATFORM_MEMORY_H

#include <stddef.h>
#include <stdint.h>

#ifndef PLATFORM_CPU_FAST_DATA
#define PLATFORM_CPU_FAST_DATA
#endif

#ifndef PLATFORM_CPU_FAST_BSS
#define PLATFORM_CPU_FAST_BSS
#endif

#ifndef PLATFORM_DMA_ACCESSIBLE
#define PLATFORM_DMA_ACCESSIBLE
#endif

uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length);

#endif /* __PLATFORM_MEMORY_H */
