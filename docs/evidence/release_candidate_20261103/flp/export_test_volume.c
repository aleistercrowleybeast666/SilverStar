/* Host-only extraction of the real generated writer's in-memory FatFs volume. */
#include <stdlib.h>
#include <string.h>
#include "logger_bus.h"
#include "logger_task.h"
#include "silverstar_assert.h"
#include "system_calibration.h"
#include "generated_identity_builder.inc"

/* Both the SSLOG stimulus and the six-section snapshot read the same Host
 * calibration provider. The ordinary throughput stimulus remains all zero. */
static void Fixture_CalibrationRecordFill(FlightLogCalibrationResultRecord *record)
{
    SystemCalibrationStatus current;
    if (getenv("RC_HOST_VALID_INPUT") == NULL) { return; }
    if (SystemCalibration_StatusGet(&current) != SYSTEM_DEVICE_OK) { abort(); }
    record->mode = (uint8_t)current.mode;
    record->state = (uint8_t)current.state;
    record->ready = current.ready;
    record->start_sequence = SystemCalibration_GenerationGet();
    for (unsigned axis = 0U; axis < 3U; ++axis) {
        record->accel_bias_mps2[axis] = current.correction.accel_bias_mps2[axis];
        record->gyro_bias_radps[axis] = current.correction.gyro_bias_radps[axis];
        record->accel_scale[axis] = current.correction.accel_scale[axis];
        record->gyro_scale[axis] = current.correction.gyro_scale[axis];
    }
}

static void Fixture_ImuRecordFill(FlightLogImuCorrectedRecord *record)
{
    if (getenv("RC_HOST_VALID_INPUT") == NULL) { return; }
    SystemCalibrationImuCorrection current;
    if (SystemCalibration_ImuCorrectionGet(&current) != SYSTEM_DEVICE_OK) { abort(); }
    record->calibration_mode = (uint8_t)current.mode;
    record->correction_valid = current.ready;
}

static LoggerBusResult Fixture_CalibrationPush(uint64_t time, const FlightLogCalibrationResultRecord *input)
{
    FlightLogCalibrationResultRecord record = *input;
    Fixture_CalibrationRecordFill(&record);
    return LoggerBus_CalibrationResultPush(time, &record);
}

static LoggerBusResult Fixture_CorrectedPush(uint64_t time, uint32_t flags, const FlightLogImuCorrectedRecord *input)
{
    FlightLogImuCorrectedRecord record = *input;
    Fixture_ImuRecordFill(&record);
    return LoggerBus_ImuCorrectedPush(time, flags, &record);
}

static LoggerBusResult Fixture_EventPush(uint64_t time, FlightLogEventId event, uint32_t arg0, uint32_t arg1)
{
    if (getenv("RC_HOST_VALID_INPUT") != NULL && event == FLIGHT_LOG_EVENT_MISSION_START) {
        FlightLogMissionSnapshotIdentityRecord record;
        LoggerBusResult result = FlightTask_MissionSnapshotIdentityBuild(&record);
        if (result != LOGGER_BUS_RESULT_OK) { return result; }
        result = LoggerBus_MissionSnapshotIdentityPush(time, &record);
        if (result != LOGGER_BUS_RESULT_OK) { return result; }
    }
    return LoggerBus_EventPush(time, event, arg0, arg1);
}

#define LoggerBus_CalibrationResultPush Fixture_CalibrationPush
#define LoggerBus_ImuCorrectedPush Fixture_CorrectedPush
#define LoggerBus_EventPush Fixture_EventPush
#include "test_logger_storage_capture.inc"
#undef LoggerBus_EventPush
#undef LoggerBus_CalibrationResultPush
#undef LoggerBus_ImuCorrectedPush

static int SnapshotSlots_Export(void)
{
    char fat_name[80];
    char local_name[20];
    uint8_t buffer[1024];
    unsigned copied = 0U;
    for (unsigned object = 0U; object < 16U; ++object) {
        for (unsigned slot = 0U; slot < 2U; ++slot) {
            UINT count = 0U;
            snprintf(local_name, sizeof(local_name), "snap%02u.%u", object, slot);
            snprintf(fat_name, sizeof(fat_name), "0:/missions/000001/%s", local_name);
            FRESULT found = f_open(&s_file, fat_name, FA_READ);
            if (found == FR_NO_FILE || found == FR_NO_PATH) { continue; }
            if (found != FR_OK) { return 10; }
            if (f_size(&s_file) > sizeof(buffer) ||
                f_read(&s_file, buffer, sizeof(buffer), &count) != FR_OK ||
                count != f_size(&s_file) || f_close(&s_file) != FR_OK) { return 11; }
            FILE *out = fopen(local_name, "wb");
            if (out == NULL) { return 12; }
            size_t written = fwrite(buffer, 1U, count, out);
            if (fclose(out) != 0 || written != count) { return 13; }
            ++copied;
        }
    }
    printf("EXPORTED_SNAPSHOT_SLOTS=%u\n", copied);
    return 0;
}

int main(int argc, char **argv)
{
    int status = StorageFixture_Main(argc, argv);
    if (status != 0) { return status; }
    return SnapshotSlots_Export();
}
