#ifndef __PROJECT_DEVICE_INSTANCES_H
#define __PROJECT_DEVICE_INSTANCES_H

/* Synthetic Host port, not a generated project or hardware evidence. */
#include "system_descriptor_if.h"

#define PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX 4U
uint8_t ProjectMagnetometerInstance_CountGet(void);

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor);
SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask);

#endif /* __PROJECT_DEVICE_INSTANCES_H */
