#include "system_mag_calibration_storage_if.h"

void SystemMagCalibrationStorage_Service(void)
{
    /* No MAG endpoint exists; do not mount or touch the calibration files. */
}

uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void)
{
    /* Absence is resolved at generation, so no optional load can block boot. */
    return 1U;
}
