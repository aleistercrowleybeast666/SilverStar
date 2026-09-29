#include "system_mag_calibration_storage_if.h"

#include <stdint.h>

#include "persistent_storage.h"
#include "project_device_instances.h"
#include "system_mag_calibration.h"
#include "silverstar_assert.h"

static uint8_t s_mag_calibration_load_instance;
static uint8_t s_mag_calibration_load_complete;
static uint8_t s_mag_calibration_packet[SYSTEM_MAG_CAL_PACKET_BYTES];

uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void)
{
    return s_mag_calibration_load_complete;
}

static void MagCalibrationStorage_OneLoad(void)
{
    uint16_t length = 0U;
    uint32_t generation = 0U;
    PersistentStorageResult result;
    SILVERSTAR_ASSERT(s_mag_calibration_load_complete == 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_mag_calibration_load_instance <=
        PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_mag_calibration_load_instance >=
        ProjectMagnetometerInstance_CountGet())
    { s_mag_calibration_load_complete = 1U; return; }
    result = PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        s_mag_calibration_load_instance, s_mag_calibration_packet,
        sizeof(s_mag_calibration_packet), &length, &generation);
    if (result == PERSISTENT_STORAGE_OK)
    {
        SystemMagCalibrationResult load_result =
            (length == SYSTEM_MAG_CAL_PACKET_BYTES) ?
            SystemMagCalibration_StoredLoad(
                s_mag_calibration_load_instance, s_mag_calibration_packet,
                generation) : SystemMagCalibrationResult_InvalidObject;
        if (load_result != SystemMagCalibrationResult_Ok)
        {
            (void)SystemMagCalibration_LoadFaultSet(
                s_mag_calibration_load_instance, load_result);
        }
    }
    else if ((result != PERSISTENT_STORAGE_NOT_FOUND) &&
             (result != PERSISTENT_STORAGE_NOT_READY))
    {
        (void)SystemMagCalibration_LoadFaultSet(
            s_mag_calibration_load_instance,
            SystemMagCalibrationResult_StorageError);
    }
    if (result != PERSISTENT_STORAGE_NOT_READY)
    { s_mag_calibration_load_instance++; }
}

void SystemMagCalibrationStorage_Service(void)
{
    uint8_t instance_id;
    uint32_t request_id;
    uint32_t generation = 0U;
    PersistentStorageResult result;
    if (s_mag_calibration_load_complete == 0U)
    { MagCalibrationStorage_OneLoad(); return; }
    if (SystemMagCalibration_PendingGet(
            &instance_id, s_mag_calibration_packet,
            &request_id) != SystemMagCalibrationResult_Ok)
    { return; }
    result = PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, instance_id,
        s_mag_calibration_packet, sizeof(s_mag_calibration_packet),
        &generation);
    (void)SystemMagCalibration_SaveComplete(
        instance_id, request_id, (uint8_t)(result == PERSISTENT_STORAGE_OK),
        generation);
}
