#ifndef __PLATFORM_MEMORY_TARGET_H
#define __PLATFORM_MEMORY_TARGET_H

#if defined(__GNUC__) || defined(__clang__)
#define PLATFORM_CPU_FAST_DATA \
    __attribute__((section(".ccmram_data"), aligned(8)))
#define PLATFORM_CPU_FAST_BSS \
    __attribute__((section(".ccmram_bss"), aligned(8)))
#define PLATFORM_DMA_ACCESSIBLE \
    __attribute__((section(".dma_bss"), aligned(8)))
#else
#define PLATFORM_CPU_FAST_DATA
#define PLATFORM_CPU_FAST_BSS
#define PLATFORM_DMA_ACCESSIBLE
#endif

#endif /* __PLATFORM_MEMORY_TARGET_H */
