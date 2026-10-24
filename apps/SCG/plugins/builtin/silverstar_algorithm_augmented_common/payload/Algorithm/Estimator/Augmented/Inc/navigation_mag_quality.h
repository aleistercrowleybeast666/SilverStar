#ifndef __NAVIGATION_MAG_QUALITY_H
#define __NAVIGATION_MAG_QUALITY_H

#include <stdint.h>

#define NAVIGATION_MAG_QUALITY_REVISION 1U
#define NAVIGATION_MAG_QUALITY_SAMPLES_MAX 256U
#define NAVIGATION_MAG_Q_CONFIG       (1UL<<0)
#define NAVIGATION_MAG_Q_PROXY        (1UL<<1)
#define NAVIGATION_MAG_Q_COMPENSATED  (1UL<<2)
#define NAVIGATION_MAG_Q_TIME         (1UL<<3)
#define NAVIGATION_MAG_Q_TRANSPORT    (1UL<<4)
#define NAVIGATION_MAG_Q_DUPLICATE    (1UL<<5)
#define NAVIGATION_MAG_Q_SEQUENCE     (1UL<<6)
#define NAVIGATION_MAG_Q_MOTION       (1UL<<7)
#define NAVIGATION_MAG_Q_FIELD        (1UL<<8)
#define NAVIGATION_MAG_Q_WARMUP       (1UL<<9)
#define NAVIGATION_MAG_Q_COVARIANCE   (1UL<<10)
#define NAVIGATION_MAG_Q_NUMERIC      (1UL<<11)
#define NAVIGATION_MAG_Q_CALIBRATION  (1UL<<12)
#define NAVIGATION_MAG_Q_INPUT        (1UL<<13)
#define NAVIGATION_MAG_Q_UNVERIFIED   (1UL<<14)
#define NAVIGATION_MAG_Q_SKIPPED      (1UL<<15)

typedef struct {
    uint32_t minimum_samples,minimum_duration_us,maximum_gap_us,maximum_sequence_step;
    float variance_floor_uT2,maximum_std_uT,maximum_span_uT;
    float gyro_max_radps,accel_tolerance_mps2,accel_span_mps2,gravity_mps2;
    float field_reference_uT,field_min_ratio,field_max_ratio;
    uint32_t delay_us,uncertainty_us,maximum_time_uncertainty_us,maximum_queue_bytes;
    uint32_t delay_bound_verified;
} NavigationMagQualityConfig;

typedef struct {
    uint64_t decode_us,now_us,accel_decode_us,gyro_decode_us;
    uint32_t sequence,transport_epoch,queue_bytes,calibration_generation,decode_span_us;
    float sensor_uT[3],corrected_uT[3],accel_mps2[3],gyro_radps[3];
    uint32_t transport_valid,imu_valid;
} NavigationMagQualityInput;

typedef struct {
    uint64_t sample_us;
    uint32_t flags,uncertainty_us,sample_count,calibration_generation;
    float covariance_sensor_uT2[9];
    uint32_t covariance_valid,time_admitted;
} NavigationMagQualityOutput;

/* Caller-owned, one EstimatorTask. No heap, callbacks, or adapter shared state. */
typedef struct {
    uint64_t previous_us,window_start_us;
    uint32_t previous_sequence,transport_epoch,calibration_generation,seen,count,frozen;
    double mean[3],scatter[9];
    float minimum[3],maximum[3],accel_anchor[3],covariance[9];
} NavigationMagQuality;

typedef enum {
    NavigationMagQualityResult_Ok=0,
    NavigationMagQualityResult_Duplicate,
    NavigationMagQualityResult_Unconfigured,
    NavigationMagQualityResult_InvalidInput,
    NavigationMagQualityResult_InvalidState
} NavigationMagQualityResult;

void NavigationMagQuality_Reset(NavigationMagQuality *state);
NavigationMagQualityResult NavigationMagQuality_Process(NavigationMagQuality *state,
    const NavigationMagQualityConfig *config,const NavigationMagQualityInput *input,
    NavigationMagQualityOutput *output);

#endif
