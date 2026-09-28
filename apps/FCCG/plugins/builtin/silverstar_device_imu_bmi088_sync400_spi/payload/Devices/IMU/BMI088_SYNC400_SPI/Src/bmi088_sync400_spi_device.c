#include "bmi088_sync400_spi_device.h"
#include "sensor_bmi088_sync.h"

const SensorImuProfile *Bmi088Sync400Spi_ProfileGet(void)
{
    return SensorBmi088Sync_ProfileGet();
}
