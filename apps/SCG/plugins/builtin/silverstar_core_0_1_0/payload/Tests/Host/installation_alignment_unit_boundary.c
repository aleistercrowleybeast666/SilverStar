/* Isolated CAL unit has no running ALIGN owner to yield. */
#include "system_alignment.h"
SystemDeviceResult SystemAlignment_CalibrationYield(void) { return SYSTEM_DEVICE_BUSY; }
