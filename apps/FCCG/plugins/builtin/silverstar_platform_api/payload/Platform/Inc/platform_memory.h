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

/* Link-time opt-in only. Each private CPU-only BSS group has a reviewed owner.
 * Legacy expands to the original placement. No data or DMA section is eligible. */
#ifndef SILVERSTAR_MEMORY_LAYOUT_AUTO
#define SILVERSTAR_MEMORY_LAYOUT_AUTO 0
#endif
#if (SILVERSTAR_MEMORY_LAYOUT_AUTO == 1)
#if defined(__GNUC__) || defined(__clang__)
#define PLATFORM_ESKF_WORK_BSS __attribute__((section(".bss.silverstar_auto_eskf_work"), aligned(8)))
#define PLATFORM_ESKF_HISTORY_BSS __attribute__((section(".bss.silverstar_auto_eskf_history"), aligned(8)))
#define PLATFORM_KF_REPLAY_BSS __attribute__((section(".bss.silverstar_auto_kf_replay"), aligned(8)))
#define PLATFORM_NAV_HEALTH_BSS __attribute__((section(".bss.silverstar_auto_nav_health"), aligned(8)))
#else
#error "Auto memory layout requires a supported compiler"
#endif
#elif (SILVERSTAR_MEMORY_LAYOUT_AUTO == 0)
#define PLATFORM_ESKF_WORK_BSS PLATFORM_CPU_FAST_BSS
#define PLATFORM_ESKF_HISTORY_BSS PLATFORM_CPU_FAST_BSS
#define PLATFORM_KF_REPLAY_BSS PLATFORM_CPU_FAST_BSS
#define PLATFORM_NAV_HEALTH_BSS PLATFORM_CPU_FAST_BSS
#else
#error "Invalid auto memory layout"
#endif

/* One audited CPU-only object; the target owns its section and alignment.
 * An old target header cannot silently accept the experimental layout. */
#ifndef SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM
#define SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM 0
#endif
#ifndef PLATFORM_ESKF_WINDOW_BSS
#if (SILVERSTAR_MEMORY_LAYOUT_AUTO == 1)
#define PLATFORM_ESKF_WINDOW_BSS __attribute__((section(".bss.silverstar_auto_eskf_window"), aligned(8)))
#else
#if (SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM != 0)
#error "The selected target does not support ESKF consistency window SRAM placement"
#endif
#define PLATFORM_ESKF_WINDOW_BSS PLATFORM_CPU_FAST_BSS
#endif
#endif

#ifndef PLATFORM_DMA_ACCESSIBLE
#define PLATFORM_DMA_ACCESSIBLE
#endif

uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length);

#endif /* __PLATFORM_MEMORY_H */
