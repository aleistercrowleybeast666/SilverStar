#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H
#include "platform_i2c.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_MPU6050_INSTANCE_COUNT 1U
typedef struct { PlatformI2cId i2c; PlatformTimeId time; int8_t axis_map[3]; } ProjectMpu6050Resources;
SystemDeviceResult ProjectMpu6050Resources_Get(uint8_t instance, ProjectMpu6050Resources *resources);
#endif
