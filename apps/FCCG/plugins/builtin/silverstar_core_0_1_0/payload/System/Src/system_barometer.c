#include "system_barometer.h"

#include <math.h>
#include <stddef.h>

#include "silverstar_assert.h"

#define SYSTEM_BAROMETER_SEA_LEVEL_PRESSURE_PA 101325.0f
#define SYSTEM_BAROMETER_STANDARD_HEIGHT_M     44330.0f
#define SYSTEM_BAROMETER_PRESSURE_EXPONENT     0.19029495f

SystemDeviceResult SystemBarometer_AltitudeResolve(
    const SystemBarometerSample *sample,
    float *altitude_m)
{
    if ((sample == NULL) || (altitude_m == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemBarometerSample,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (((sample->supported_fields & SYSTEM_BARO_FIELD_ALTITUDE) != 0U) &&
        ((sample->valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) != 0U) &&
        isfinite(sample->altitude_m))
    {
        *altitude_m = sample->altitude_m;
        return SYSTEM_DEVICE_OK;
    }
    if (((sample->supported_fields & SYSTEM_BARO_FIELD_PRESSURE) != 0U) &&
        ((sample->valid_fields & SYSTEM_BARO_FIELD_PRESSURE) != 0U) &&
        isfinite(sample->pressure_pa) && (sample->pressure_pa > 0.0f))
    {
        *altitude_m = SYSTEM_BAROMETER_STANDARD_HEIGHT_M *
            (1.0f - powf(sample->pressure_pa /
                         SYSTEM_BAROMETER_SEA_LEVEL_PRESSURE_PA,
                         SYSTEM_BAROMETER_PRESSURE_EXPONENT));
        return isfinite(*altitude_m) ? SYSTEM_DEVICE_OK :
                                      SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_NOT_READY;
}
