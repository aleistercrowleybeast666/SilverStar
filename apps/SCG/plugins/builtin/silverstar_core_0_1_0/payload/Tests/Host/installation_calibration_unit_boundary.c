/* Explicit descriptor/configuration facade for isolated CAL/ALIGN unit tests.
 * No active record, physical provider, maintenance transaction or storage is
 * represented here. installation_active_integration owns those real paths. */
#include <stddef.h>
#include <string.h>
#include "system_descriptor_if.h"
#include "system_source_selector.h"
#include "system_lifecycle.h"

uint32_t SystemDescriptor_ConfigDigestGet(void) { return 1U; }
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass kind, uint8_t instance,
                                               SystemDeviceDescriptor *descriptor)
{
    if (descriptor == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (kind != SYSTEM_DEVICE_CLASS_IMU || instance != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    (void)memset(descriptor, 0, sizeof(*descriptor));
    descriptor->descriptor_id = 1U; descriptor->physical_device_id = 1U;
    descriptor->driver_name_hash = 1U; descriptor->model_name_hash = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{
    if (instance == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *instance = 0U; return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemLifecycle_ConfigurationBegin(SystemConfigurationAction action)
{
    (void)action;
    return SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT ? SYSTEM_DEVICE_BAD_STATE : SYSTEM_DEVICE_OK;
}
void SystemLifecycle_ConfigurationEnd(SystemConfigurationAction action) { (void)action; }
