#ifndef __PLATFORM_MEMORY_TARGET_H
#define __PLATFORM_MEMORY_TARGET_H

#ifndef SILVERSTAR_MEMORY_LAYOUT_AUTO
#define SILVERSTAR_MEMORY_LAYOUT_AUTO 0
#endif

#ifndef SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM
#define SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM 0
#endif
#if ((SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM != 0) && \
     (SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM != 1))
#error "Invalid ESKF consistency window memory layout"
#endif

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

/* .bss.* remains inside _sbss/_ebss and uses the unchanged startup clear.
 * SRAM is a deliberate CCM relief tradeoff, not a timing qualification. */
#if (SILVERSTAR_MEMORY_LAYOUT_AUTO == 1)
#if (SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM != 0)
#error "Auto and manual ESKF window layouts are mutually exclusive"
#endif
#define PLATFORM_ESKF_WINDOW_BSS \
    __attribute__((section(".bss.silverstar_auto_eskf_window"), aligned(8)))
#elif (SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM == 1)
#if defined(__GNUC__) || defined(__clang__)
#define PLATFORM_ESKF_WINDOW_BSS \
    __attribute__((section(".bss.silverstar_eskf_window"), aligned(8)))
#else
#error "ESKF consistency window SRAM placement requires a supported compiler"
#endif
#else
#define PLATFORM_ESKF_WINDOW_BSS PLATFORM_CPU_FAST_BSS
#endif

#endif /* __PLATFORM_MEMORY_TARGET_H */
