#ifndef __SYSTEM_NAVIGATION_BACKEND_H
#define __SYSTEM_NAVIGATION_BACKEND_H

#include "system_device_types.h"
#include "system_gnss_if.h"
#include "estimator_task.h"
#include "platform_memory.h"

/* Enum constants are C expressions, not preprocessor macros. The selected
 * plugin declares linkage capability; validate it against the typed build ID. */
#if (defined(SYSTEM_BUILD_ESKF15_ENABLED) && (SYSTEM_BUILD_ESKF15_ENABLED != 0U)) || \
    (defined(SYSTEM_BUILD_SF6_ENABLED) && (SYSTEM_BUILD_SF6_ENABLED != 0U)) || \
    (defined(SYSTEM_BUILD_AUGMENTED_ENABLED) && (SYSTEM_BUILD_AUGMENTED_ENABLED != 0U))
#define SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED 1U
#else
#define SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED 0U
#endif
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
/* Augmented single-owner journal closure; no change to navigation/lifecycle. */
void SystemNavigationBackend_RecordedSeal(uint32_t reason);
/* Augmented capability only. Old builds eliminate the constant-false caller. */
void SystemNavigationBackend_IntervalStartSet(SystemInertialIncrement *input, uint64_t start_us);

void SystemNavigationBackend_BodyInputFill(SystemInertialIncrement *input,
    const float *gyro_pair, const float *accel_pair, uint32_t quality_flags);

#endif /* __SYSTEM_NAVIGATION_BACKEND_H */
