#ifndef __PLATFORM_TIME_H
#define __PLATFORM_TIME_H

#include <stdint.h>

#include "platform_types.h"

typedef enum
{
    PLATFORM_TIME_1 = 0,
    PLATFORM_TIME_COUNT
} PlatformTimeId;

PlatformResult PlatformTime_Init(void);
uint32_t PlatformTime_Ms(void);
uint64_t PlatformTime_Us(void);
void PlatformTime_DelayMs(uint32_t delay_ms);

#endif /* __PLATFORM_TIME_H */
