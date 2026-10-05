#include "bmi088_sync400_device.h"
#include "sensor_bmi088_sync.h"

const SensorImuProfile *Bmi088Sync400_ProfileGet(void)
{
    return SensorBmi088Sync_ProfileGet();
}
