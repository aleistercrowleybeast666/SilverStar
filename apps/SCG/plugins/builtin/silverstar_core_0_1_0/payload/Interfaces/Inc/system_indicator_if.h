#ifndef __SYSTEM_INDICATOR_IF_H
#define __SYSTEM_INDICATOR_IF_H

#include <stdint.h>

#include "system_device_types.h"

SystemDeviceResult SystemIndicatorDevice_Set(uint8_t channel,
                                             uint8_t logical_on);

#endif /* __SYSTEM_INDICATOR_IF_H */
