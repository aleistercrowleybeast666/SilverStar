#include <stddef.h>
#include "system_device_types.h"
const unsigned layout[] = {
 sizeof(SystemNavigationProvenance), offsetof(SystemNavigationProvenance, valid),
 offsetof(SystemInertialIncrement, provenance), sizeof(SystemInertialIncrement),
#if SYSTEM_BUILD_ESKF15_ENABLED || SYSTEM_BUILD_AUGMENTED_ENABLED
 offsetof(SystemInertialIncrement, body_gyro_radps),
 offsetof(SystemInertialIncrement, body_accel_mps2),
 offsetof(SystemInertialIncrement, quality_flags),
#endif
#if SYSTEM_BUILD_AUGMENTED_ENABLED
 offsetof(SystemInertialIncrement, interval_start_timestamp_us),
#endif
};
