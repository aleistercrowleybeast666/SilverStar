#ifndef __PLATFORM_ADC_H
#define __PLATFORM_ADC_H

#include <stdint.h>

#include "platform_types.h"

typedef enum
{
    PLATFORM_ADC_1 = 0,
    PLATFORM_ADC_COUNT = 3
} PlatformAdcId;

PlatformResult PlatformAdc_Read(PlatformAdcId id,
                                uint32_t timeout_ms,
                                uint32_t *raw_count);

#endif /* __PLATFORM_ADC_H */
