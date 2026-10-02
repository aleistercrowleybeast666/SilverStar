#ifndef __SYSTEM_NAVIGATION_BACKEND_H
#define __SYSTEM_NAVIGATION_BACKEND_H

#include "system_device_types.h"
#include "system_gnss_if.h"
#include "estimator_task.h"
#include "platform_memory.h"

/* CPU-only output caches use the bank left by the selected backend.
 * Both placements are checked against the unchanged linked-ELF budgets. */
#if defined(SYSTEM_BUILD_ESKF15_ENABLED) && (SYSTEM_BUILD_ESKF15_ENABLED != 0U)
#define SYSTEM_NAVIGATION_OUTPUT_BSS
#else
#define SYSTEM_NAVIGATION_OUTPUT_BSS PLATFORM_CPU_FAST_BSS
#endif

/* Statically linked selected backend. No estimator-private type crosses this API. */
SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],
    const SystemGnssSample *origin, float barometer_origin_m,
    uint8_t barometer_origin_valid, uint32_t generation, uint8_t activate);
SystemDeviceResult SystemNavigationBackend_Predict(
    const SystemInertialIncrement *input, EstimatorOutputSnapshot *output);
SystemDeviceResult SystemNavigationBackend_SnapshotGet(EstimatorOutputSnapshot *output);
void SystemNavigationBackend_Reset(void);
void SystemNavigationBackend_BodyInputFill(SystemInertialIncrement *input,
    const float *gyro_pair, const float *accel_pair, uint32_t quality_flags);

#endif /* __SYSTEM_NAVIGATION_BACKEND_H */
