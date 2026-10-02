#include "../../Devices/Storage/SdSdioFatFs/Src/mag_calibration_storage.c"
#include "optional_start_inputs.h"

/* Raw persistent-object input: no saved magnetic calibration in this fixture. */
uint8_t ProjectMagnetometerInstance_CountGet(void) { return 1U; }
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
