#ifndef __SYSTEM_DESCRIPTOR_IF_H
#define __SYSTEM_DESCRIPTOR_IF_H

#include <stdint.h>

#include "system_device_types.h"

#define SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX    32U
#define SYSTEM_DESCRIPTOR_ALGORITHM_COUNT_MAX 16U

#define SYSTEM_DESCRIPTOR_FLAG_ENABLED         (1U << 0)
#define SYSTEM_DESCRIPTOR_FLAG_REQUIRED        (1U << 1)
#define SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL (1U << 2)
#define SYSTEM_DESCRIPTOR_FLAG_PRIMARY         (1U << 3)

typedef enum
{
    SYSTEM_DEVICE_CLASS_IMU = 1U,
    SYSTEM_DEVICE_CLASS_GNSS,
    SYSTEM_DEVICE_CLASS_BAROMETER,
    SYSTEM_DEVICE_CLASS_MAGNETOMETER,
    SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION,
    SYSTEM_DEVICE_CLASS_TELEMETRY,
    SYSTEM_DEVICE_CLASS_CONSOLE,
    SYSTEM_DEVICE_CLASS_POWER,
    SYSTEM_DEVICE_CLASS_STORAGE,
    SYSTEM_DEVICE_CLASS_LOG_SINK,
    SYSTEM_DEVICE_CLASS_OUTPUT,
    SYSTEM_DEVICE_CLASS_MISSION_ACTION,
    SYSTEM_DEVICE_CLASS_TIME
} SystemDeviceClass;

typedef enum
{
    SYSTEM_ALGORITHM_CLASS_ALIGNMENT = 1U,
    SYSTEM_ALGORITHM_CLASS_ATTITUDE,
    SYSTEM_ALGORITHM_CLASS_MECHANIZATION,
    SYSTEM_ALGORITHM_CLASS_FUSION
} SystemAlgorithmClass;

typedef struct
{
    uint16_t descriptor_id;
    uint16_t physical_device_id;
    SystemDeviceClass device_class;
    uint8_t instance_id;
    uint16_t driver_id;
    uint16_t flags;
    uint32_t capability_mask;
    uint32_t configured_rate_hz;
    uint32_t driver_name_hash;
    uint32_t model_name_hash;
} SystemDeviceDescriptor;

typedef struct
{
    uint16_t descriptor_id;
    SystemAlgorithmClass algorithm_class;
    uint8_t instance_id;
    uint16_t algorithm_id;
    uint16_t flags;
    uint32_t config_digest;
    uint32_t name_hash;
} SystemAlgorithmDescriptor;

uint16_t SystemDescriptor_DeviceCountGet(void);
SystemDeviceResult SystemDescriptor_DeviceGet(
    uint16_t index, SystemDeviceDescriptor *descriptor);
uint8_t SystemDescriptor_DeviceClassInstanceCountGet(
    SystemDeviceClass device_class);
SystemDeviceResult SystemDescriptor_DeviceFind(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor);
uint16_t SystemDescriptor_AlgorithmCountGet(void);
SystemDeviceResult SystemDescriptor_AlgorithmGet(
    uint16_t index, SystemAlgorithmDescriptor *descriptor);
uint32_t SystemDescriptor_ConfigDigestGet(void);

#endif /* __SYSTEM_DESCRIPTOR_IF_H */
