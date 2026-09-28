#ifndef __SYSTEM_GNSS_QUALITY_H
#define __SYSTEM_GNSS_QUALITY_H

#include <stdint.h>

#include "system_gnss_if.h"

SystemDeviceResult SystemGnssQuality_Evaluate(SystemGnssSample *sample,
                                               uint64_t now_us);

#endif /* __SYSTEM_GNSS_QUALITY_H */
