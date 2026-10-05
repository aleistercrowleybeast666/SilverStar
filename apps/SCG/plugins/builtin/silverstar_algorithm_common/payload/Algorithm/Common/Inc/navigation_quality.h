#ifndef __NAVIGATION_QUALITY_H
#define __NAVIGATION_QUALITY_H

#include <stdint.h>

#define NAV_QUALITY_REVISION 3U
#define NAV_QUALITY_WINDOW_COUNT 2U

typedef enum
{
    NAV_QUALITY_OK = 0,
    NAV_QUALITY_INVALID,
    NAV_QUALITY_DUPLICATE,
    NAV_QUALITY_DISCONTINUITY
} NavigationQualityResult;

typedef struct
{
    uint64_t length_us;
    uint64_t offset_us;
    uint64_t ttl_us;
    uint32_t maximum_gap_us;
    float error_threshold_m;
    float maximum_variance_scale;
} NavigationWindowConfig;

typedef struct
{
    uint64_t epoch_us;
    uint32_t sequence;
    uint32_t source;
    uint32_t generation;
    float position_en[2];
    float velocity_en[2];
    uint8_t position_valid;
    uint8_t velocity_valid;
} NavigationWindowSample;

typedef struct
{
    uint64_t start_us;
    float position_en[2];
    float integral_en[2];
    uint32_t covered_position_epochs;
    uint32_t covered_velocity_epochs;
    uint8_t started;
    uint8_t start_position_valid;
} NavigationWindowState;

typedef struct
{
    NavigationWindowState window[NAV_QUALITY_WINDOW_COUNT];
    NavigationWindowSample previous;
    uint64_t completed_us;
    float closure_en[2];
    float closure_norm_m;
    float variance_scale;
    uint32_t completed_count;
    uint32_t unavailable_count;
    uint8_t previous_valid;
    uint8_t evidence_valid;
    /* Provenance of the last usable completed window, retained across an
       unavailable completion until its TTL expires. */
    uint64_t completed_start_us;
    uint32_t completed_covered_us;
    uint32_t completed_position_epochs;
    uint32_t completed_velocity_epochs;
    uint8_t completed_window_index;
} NavigationWindowContext;

NavigationQualityResult NavigationWindow_Reset(NavigationWindowContext *context);
NavigationQualityResult NavigationWindow_ConfigValidate(const NavigationWindowConfig *config);
NavigationQualityResult NavigationWindow_Receive(NavigationWindowContext *context,
    const NavigationWindowConfig *config, const NavigationWindowSample *sample);
float NavigationWindow_VarianceScale(const NavigationWindowContext *context,
    const NavigationWindowConfig *config, uint64_t epoch_us);
float NavigationQuality_SatelliteVarianceScale(uint8_t satellites, uint8_t count_valid);

#endif /* __NAVIGATION_QUALITY_H */
