/* Storage/log task projection input fixture, not a replacement for START's
 * storage admission: actual LoggerTask_DiagnosticsGet and FlightTask's complete
 * snapshot/generation/mount/health checks execute against these stored fields.
 * This does not claim a new on-disk snapshot transaction or SD qualification. */
#include "../../APP/Src/logger_task.c"
#include "optional_start_inputs.h"

void Test_StorageProjectionSet(void)
{
    memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    s_diagnostics.snapshot_ready = 1U;
    s_diagnostics.snapshot_mission_id = 1U;
    s_diagnostics.snapshot_commit_generation = 1U;
    s_diagnostics.snapshot_calibration_generation = SystemCalibration_GenerationGet();
    s_diagnostics.snapshot_mag_calibration_set_hash = SystemMagCalibration_GenerationHashGet();
}
