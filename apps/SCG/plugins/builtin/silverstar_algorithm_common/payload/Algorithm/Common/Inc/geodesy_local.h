#ifndef __GEODESY_LOCAL_H
#define __GEODESY_LOCAL_H

#include <stdint.h>

#define GEO_WGS84_A_M   6378137.0
#define GEO_WGS84_INV_F 298.257223563

typedef struct
{
    int32_t origin_lat_e7;
    int32_t origin_lon_e7;
    int32_t origin_height_mm;

    double origin_lat_rad;
    double origin_height_m;

    double meridian_radius_m;
    double prime_vertical_radius_m;

    double east_m_per_e7;
    double north_m_per_e7;

    uint8_t valid;
} GeoLocalFrame;

uint8_t GeoLocalFrame_Init(GeoLocalFrame *frame,
                           int32_t lat_e7,
                           int32_t lon_e7,
                           int32_t height_mm);
uint8_t GeoLocalFrame_ToEnu(const GeoLocalFrame *frame,
                            int32_t lat_e7,
                            int32_t lon_e7,
                            int32_t height_mm,
                            float enu_m[3]);

#endif /* __GEODESY_LOCAL_H */
