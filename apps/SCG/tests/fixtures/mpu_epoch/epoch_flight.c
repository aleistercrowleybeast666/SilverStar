#define SystemLifecycleBackend_PrepareStart Test_RealPrepareStart
#define SystemLifecycleBackend_FreezeOrigins Test_RealFreezeOrigins
#define SystemLifecycleBackend_InitializeNavigation Test_RealInitializeNavigation
#define SystemLifecycleBackend_ResetFlightQueues Test_RealResetFlightQueues
#include "flight_task.c"
#undef SystemLifecycleBackend_PrepareStart
#undef SystemLifecycleBackend_FreezeOrigins
#undef SystemLifecycleBackend_InitializeNavigation
#undef SystemLifecycleBackend_ResetFlightQueues
void Test_InjectStartStage(unsigned stage);
SystemDeviceResult SystemLifecycleBackend_PrepareStart(void)
{ SystemDeviceResult result = Test_RealPrepareStart(); Test_InjectStartStage(1U); return result; }
SystemDeviceResult SystemLifecycleBackend_FreezeOrigins(void)
{ SystemDeviceResult result = Test_RealFreezeOrigins(); Test_InjectStartStage(2U); return result; }
SystemDeviceResult SystemLifecycleBackend_InitializeNavigation(void)
{ SystemDeviceResult result = Test_RealInitializeNavigation(); Test_InjectStartStage(3U); return result; }
SystemDeviceResult SystemLifecycleBackend_ResetFlightQueues(void)
{ SystemDeviceResult result = Test_RealResetFlightQueues(); Test_InjectStartStage(4U); return result; }
