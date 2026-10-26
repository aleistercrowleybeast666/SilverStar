#include "system_mag_calibration_storage_if.h"

#include <stdint.h>

#include "persistent_storage.h"
#include "platform_memory.h"
#include "project_device_instances.h"
#include "system_mag_calibration.h"
#include "silverstar_assert.h"
#include "system_installation_capture_if.h"

static uint8_t s_mag_calibration_load_instance;
static uint8_t s_mag_calibration_load_complete;
/* CPU-only envelope. PersistentStorage copies through its independent record
 * buffer before storage I/O; reads copy back only after verification. */
static PLATFORM_CPU_FAST_BSS uint8_t s_mag_calibration_record[SYSTEM_MAG_CAL_RECORD_BYTES];

static SystemDeviceResult MagCalibrationStorage_Mount(void)
{
    SystemDeviceResult result = SystemStorage_Init();
    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    { return result; }
    return SystemStorage_Mount();
}

static void MagCalibrationStorage_LoadFault(uint8_t instance_id,
    SystemMagCalibrationResult reason)
{
    SystemMagCalibrationResult result = SystemMagCalibration_LoadFaultSet(instance_id, reason);
    /* Generated descriptors cannot disappear during this owner's boot scan. */
    SILVERSTAR_ASSERT(result == SystemMagCalibrationResult_Ok,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

static void MagCalibrationStorage_Complete(uint8_t instance_id, uint32_t request_id,
    uint8_t success, uint32_t generation)
{
    SystemMagCalibrationResult result = SystemMagCalibration_SaveComplete(
        instance_id, request_id, success, generation);
    /* Card errors are encoded by success=0; completion rejection is an internal
     * descriptor/request contract failure, not an external-media error. */
    SILVERSTAR_ASSERT(result == SystemMagCalibrationResult_Ok,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
}

uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void)
{
    return s_mag_calibration_load_complete;
}

static void MagCalibrationStorage_OneLoadOwned(void)
{
    uint16_t length = 0U;
    uint32_t generation = 0U;
    PersistentStorageResult result;
    SystemDeviceResult mount_result;
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
    mount_result = MagCalibrationStorage_Mount();
    if ((mount_result != SYSTEM_DEVICE_OK) &&
        (mount_result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        MagCalibrationStorage_LoadFault(
            s_mag_calibration_load_instance, SystemMagCalibrationResult_StorageError);
        s_mag_calibration_load_instance++;
        return;
    }
    result = PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        s_mag_calibration_load_instance, s_mag_calibration_record,
        sizeof(s_mag_calibration_record), &length, &generation);
    if (result == PERSISTENT_STORAGE_OK)
    {
        SystemMagCalibrationResult load_result =
            SystemMagCalibration_RecordLoadOwned(
                s_mag_calibration_load_instance, s_mag_calibration_record,
                length, generation);
        if (load_result != SystemMagCalibrationResult_Ok)
        {
            MagCalibrationStorage_LoadFault(
                s_mag_calibration_load_instance, load_result);
        }
    }
    else if (result != PERSISTENT_STORAGE_NOT_FOUND)
    {
        MagCalibrationStorage_LoadFault(
            s_mag_calibration_load_instance,
            SystemMagCalibrationResult_StorageError);
    }
    s_mag_calibration_load_instance++;
}

static void MagCalibrationStorage_OneLoad(void)
{
    if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_MagWrite,0U)!=SYSTEM_DEVICE_OK)
    {return;}
    MagCalibrationStorage_OneLoadOwned();
    SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);
}

void SystemMagCalibrationStorage_Service(void)
{
    uint8_t instance_id = UINT8_MAX;
    uint32_t request_id = 0U;
    uint32_t generation = 0U;
    PersistentStorageResult result;
    SystemMagCalibrationResult pending_result;
    SystemDeviceResult mount_result;
    if (s_mag_calibration_load_complete == 0U)
    { MagCalibrationStorage_OneLoad(); return; }
    pending_result = SystemMagCalibration_PendingRecordGet(
        &instance_id, s_mag_calibration_record, &request_id);
    if (instance_id == UINT8_MAX) { return; }
    if (pending_result != SystemMagCalibrationResult_Ok)
    {
        MagCalibrationStorage_Complete(instance_id, request_id, 0U, 0U);
        return;
    }
    mount_result = MagCalibrationStorage_Mount();
    result = PERSISTENT_STORAGE_NOT_READY;
    if ((mount_result == SYSTEM_DEVICE_OK) ||
        (mount_result == SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        result = PersistentStorage_ObjectWriteAtomic(
            PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, instance_id,
            s_mag_calibration_record, sizeof(s_mag_calibration_record),
            &generation);
    }
    MagCalibrationStorage_Complete(
        instance_id, request_id, (uint8_t)(result == PERSISTENT_STORAGE_OK),
        generation);
}
