#ifndef __PLATFORM_MEMORY_H
#define __PLATFORM_MEMORY_H
#include <stddef.h>
#include <stdint.h>
uint8_t PlatformMemory_IsDmaAccessible(const void *buffer, size_t length);
#endif
