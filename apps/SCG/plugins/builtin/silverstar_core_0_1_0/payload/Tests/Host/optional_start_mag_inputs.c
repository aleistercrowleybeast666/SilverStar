#include "../../Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c"
#include "optional_start_inputs.h"

/* Raw persistent-object input: no saved magnetic calibration in this fixture. */
uint8_t ProjectMagnetometerInstance_CountGet(void) { return 1U; }

/* Match the raw, enabled magnetic endpoint declared by this fixture. No saved
 * calibration is supplied and no installation qualification is invented. */
SystemDeviceResult ProjectDeviceInstance_DescriptorGet(SystemDeviceClass device_class,
    uint8_t instance_id, SystemDeviceDescriptor *descriptor)
{
    if (descriptor == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((device_class != SYSTEM_DEVICE_CLASS_MAGNETOMETER) || (instance_id != 0U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *descriptor = (SystemDeviceDescriptor){13U, 6U, SYSTEM_DEVICE_CLASS_MAGNETOMETER,
        0U, 1U, SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 200U, 1U, 1U};
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capabilities)
{
    if (capabilities == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *capabilities = SYSTEM_MAG_CAP_PHYSICAL_UNIT;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_Init(void)
{
    SystemStorageHealth health;
    SystemDeviceResult result = SystemStorage_HealthGet(&health);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    return (health.initialized != 0U) ? SYSTEM_DEVICE_ALREADY_MATCHED : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemStorage_Mount(void)
{
    SystemStorageHealth health;
    SystemDeviceResult result = SystemStorage_HealthGet(&health);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    return ((health.mounted != 0U) && (health.healthy != 0U)) ?
        SYSTEM_DEVICE_ALREADY_MATCHED : SYSTEM_DEVICE_NOT_READY;
}

PersistentStorageResult PersistentStorage_ObjectRead(PersistentStorageObjectKind kind,
    uint8_t instance, uint8_t *data, uint16_t capacity, uint16_t *length, uint32_t *generation)
{
    (void)kind; (void)instance; (void)data; (void)capacity;
    *length = 0U; *generation = 0U; return PERSISTENT_STORAGE_NOT_FOUND;
}
PersistentStorageResult PersistentStorage_ObjectWriteAtomic(PersistentStorageObjectKind kind,
    uint8_t instance, const uint8_t *data, uint16_t length, uint32_t *generation)
{
    (void)kind; (void)instance; (void)data; (void)length; (void)generation;
    return PERSISTENT_STORAGE_NOT_READY;
}
void Test_MagStorageInputsLoad(void)
{
    SystemMagCalibrationStorage_Service();
    SystemMagCalibrationStorage_Service();
}
