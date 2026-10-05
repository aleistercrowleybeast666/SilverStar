#ifndef __PLATFORM_MEMORY_TARGET_H
#define __PLATFORM_MEMORY_TARGET_H

/* RET6 has no CCM. All CPU and DMA state remains in the only SRAM region. */
#define PLATFORM_CPU_FAST_DATA
#define PLATFORM_CPU_FAST_BSS
#define PLATFORM_DMA_ACCESSIBLE __attribute__((aligned(8)))
#define PLATFORM_ESKF_WINDOW_BSS

#endif /* __PLATFORM_MEMORY_TARGET_H */
