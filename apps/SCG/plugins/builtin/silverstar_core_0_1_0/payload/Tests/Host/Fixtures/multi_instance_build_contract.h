#ifndef __MULTI_INSTANCE_BUILD_CONTRACT_H
#define __MULTI_INSTANCE_BUILD_CONTRACT_H

/* The source-selector unit fixture supplies multiple logical instances, not
 * the compact single physical MPU recovery provider. Keep its ordinary-mode
 * contract explicit even when the selected project's production mode is compact.
 * This header never enters target firmware. */
#include "project_flight_config.h"
#include "project_device_instances.h"
#undef SILVERSTAR_BUILD_COMPACT_ENABLED
#define SILVERSTAR_BUILD_COMPACT_ENABLED 0U
/* This existing fixture injects three instances and tests invalid fourth IDs.
 * Use the ordinary four-slot bounds, while retaining real interface types. */
#undef PROJECT_IMU_INSTANCE_COUNT_MAX
#define PROJECT_IMU_INSTANCE_COUNT_MAX 4U
#undef PROJECT_GNSS_INSTANCE_COUNT_MAX
#define PROJECT_GNSS_INSTANCE_COUNT_MAX 4U
#undef PROJECT_BAROMETER_INSTANCE_COUNT_MAX
#define PROJECT_BAROMETER_INSTANCE_COUNT_MAX 4U
#undef PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX
#define PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX 4U
#undef PROJECT_ATTITUDE_INSTANCE_COUNT_MAX
#define PROJECT_ATTITUDE_INSTANCE_COUNT_MAX 4U
#undef PROJECT_TELEMETRY_INSTANCE_COUNT_MAX
#define PROJECT_TELEMETRY_INSTANCE_COUNT_MAX 4U
#undef PROJECT_POWER_INSTANCE_COUNT_MAX
#define PROJECT_POWER_INSTANCE_COUNT_MAX 4U

#endif /* __MULTI_INSTANCE_BUILD_CONTRACT_H */
