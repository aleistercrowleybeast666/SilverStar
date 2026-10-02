#ifndef __SYSTEM_BAROMETER_COLD_H
#define __SYSTEM_BAROMETER_COLD_H

#include "system_barometer_if.h"

#define SYSTEM_BAROMETER_COLD_INSTANCE_NONE 0xFFU
#define SYSTEM_BAROMETER_COLD_FAILURE_TIMEOUT_US 250000ULL

/* Init/Start/Stop/Process have one owner: startup and runtime in DeviceTask.
 * Readers receive coherent cached snapshots. Shared IMU transports retain
 * their IMU owner; cold barometer selection does not stop a shared IMU. */
SystemDeviceResult SystemBarometerCold_Init(void);
SystemDeviceResult SystemBarometerCold_Start(void);
SystemDeviceResult SystemBarometerCold_Stop(void);
SystemDeviceResult SystemBarometerCold_Process(void);
uint8_t SystemBarometerCold_ActiveGet(void);
SystemDeviceResult SystemBarometerCold_SampleGet(SystemBarometerSample *sample);
SystemDeviceResult SystemBarometerCold_HealthGet(SystemDeviceHealth *health);

#endif /* __SYSTEM_BAROMETER_COLD_H */
