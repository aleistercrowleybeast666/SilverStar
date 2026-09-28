#include "geodesy_local.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define GEO_PI                     3.14159265358979323846
#define GEO_E7_PER_DEGREE          10000000LL
#define GEO_LONGITUDE_HALF_TURN_E7 1800000000LL
#define GEO_LONGITUDE_FULL_TURN_E7 3600000000LL

static uint8_t GeoLocalFrame_ScalesValid(const GeoLocalFrame *frame)
{
    return (uint8_t)(isfinite(frame->meridian_radius_m) &&
        isfinite(frame->prime_vertical_radius_m) &&
        isfinite(frame->east_m_per_e7) && isfinite(frame->north_m_per_e7) &&
        (frame->east_m_per_e7 > 0.0) && (frame->north_m_per_e7 > 0.0));
}

uint8_t GeoLocalFrame_Init(GeoLocalFrame *frame,
                           int32_t lat_e7,
                           int32_t lon_e7,
                           int32_t height_mm)
{
    double flattening;
    double eccentricity_squared;
    double sine_latitude;
    double denominator;
    double radians_per_e7;

    if ((frame == NULL) ||
        (lat_e7 < -900000000) || (lat_e7 > 900000000) ||
        (lon_e7 < -1800000000) || (lon_e7 > 1800000000))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(frame, GeoLocalFrame,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    memset(frame, 0, sizeof(*frame));
    flattening = 1.0 / GEO_WGS84_INV_F;
    eccentricity_squared = flattening * (2.0 - flattening);
    radians_per_e7 = GEO_PI / (180.0 * (double)GEO_E7_PER_DEGREE);

    frame->origin_lat_e7 = lat_e7;
    frame->origin_lon_e7 = lon_e7;
    frame->origin_height_mm = height_mm;
    frame->origin_lat_rad = (double)lat_e7 * radians_per_e7;
    frame->origin_height_m = (double)height_mm * 0.001;

    sine_latitude = sin(frame->origin_lat_rad);
    denominator = 1.0 - eccentricity_squared * sine_latitude * sine_latitude;
    if ((!isfinite(denominator)) || (denominator <= 0.0))
    {
        return 0U;
    }

    frame->prime_vertical_radius_m = GEO_WGS84_A_M / sqrt(denominator);
    frame->meridian_radius_m = GEO_WGS84_A_M *
        (1.0 - eccentricity_squared) / pow(denominator, 1.5);
    frame->east_m_per_e7 =
        (frame->prime_vertical_radius_m + frame->origin_height_m) *
        cos(frame->origin_lat_rad) * radians_per_e7;
    frame->north_m_per_e7 =
        (frame->meridian_radius_m + frame->origin_height_m) * radians_per_e7;

    if (GeoLocalFrame_ScalesValid(frame) == 0U)
    {
        memset(frame, 0, sizeof(*frame));
        return 0U;
    }

    frame->valid = 1U;
    return 1U;
}

uint8_t GeoLocalFrame_ToEnu(const GeoLocalFrame *frame,
                            int32_t lat_e7,
                            int32_t lon_e7,
                            int32_t height_mm,
                            float enu_m[3])
{
    int64_t delta_lat_e7;
    int64_t delta_lon_e7;
    double east_m;
    double north_m;
    double up_m;

    if ((frame == NULL) || (frame->valid == 0U) || (enu_m == NULL) ||
        (lat_e7 < -900000000) || (lat_e7 > 900000000) ||
        (lon_e7 < -1800000000) || (lon_e7 > 1800000000))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(frame, GeoLocalFrame,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(enu_m, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    delta_lat_e7 = (int64_t)lat_e7 - (int64_t)frame->origin_lat_e7;
    delta_lon_e7 = (int64_t)lon_e7 - (int64_t)frame->origin_lon_e7;
    if (delta_lon_e7 > GEO_LONGITUDE_HALF_TURN_E7)
    {
        delta_lon_e7 -= GEO_LONGITUDE_FULL_TURN_E7;
    }
    else if (delta_lon_e7 < -GEO_LONGITUDE_HALF_TURN_E7)
    {
        delta_lon_e7 += GEO_LONGITUDE_FULL_TURN_E7;
    }

    east_m = (double)delta_lon_e7 * frame->east_m_per_e7;
    north_m = (double)delta_lat_e7 * frame->north_m_per_e7;
    up_m = ((double)height_mm - (double)frame->origin_height_mm) * 0.001;
    if ((!isfinite(east_m)) || (!isfinite(north_m)) || (!isfinite(up_m)))
    {
        return 0U;
    }

    enu_m[0] = (float)east_m;
    enu_m[1] = (float)north_m;
    enu_m[2] = (float)up_m;
    if ((!isfinite(enu_m[0])) || (!isfinite(enu_m[1])) ||
        (!isfinite(enu_m[2])))
    {
        return 0U;
    }

    return 1U;
}
