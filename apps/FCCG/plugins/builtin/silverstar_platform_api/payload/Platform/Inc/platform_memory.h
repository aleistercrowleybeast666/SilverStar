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

/* One audited CPU-only object; the target owns its section and alignment.
 * An old target header cannot silently accept the experimental layout. */
#ifndef SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM
#define SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM 0
#endif
#ifndef PLATFORM_ESKF_WINDOW_BSS
#if (SILVERSTAR_MEMORY_LAYOUT_ESKF_WINDOW_SRAM != 0)
#error "The selected target does not support ESKF consistency window SRAM placement"
#endif
#define PLATFORM_ESKF_WINDOW_BSS PLATFORM_CPU_FAST_BSS
#endif

#ifndef PLATFORM_DMA_ACCESSIBLE
#define PLATFORM_DMA_ACCESSIBLE
#endif

uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length);

#endif /* __PLATFORM_MEMORY_H */
