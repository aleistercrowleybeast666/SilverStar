#ifndef __SYSTEM_BAROMETER_H
#define __SYSTEM_BAROMETER_H

#include "system_barometer_if.h"

SystemDeviceResult SystemBarometer_AltitudeResolve(
    const SystemBarometerSample *sample,
    float *altitude_m);

#endif /* __SYSTEM_BAROMETER_H */
