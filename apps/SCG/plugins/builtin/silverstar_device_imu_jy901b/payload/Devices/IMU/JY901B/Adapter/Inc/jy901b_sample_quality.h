#ifndef __JY901B_SAMPLE_QUALITY_H
#define __JY901B_SAMPLE_QUALITY_H

#include "system_imu_if.h"

SystemDeviceResult Jy901bSample_QualityEvaluate(SystemImuSample *sample,
    const SystemImuConfig *verified_config, uint64_t previous_epoch_us,
    uint64_t pair_skew_us);

#endif /* __JY901B_SAMPLE_QUALITY_H */
