/* Actual bus implementation. Only its admission state is fault-injected after
 * successful real START; this is not an alternative target bus implementation. */
#include "../../APP/Src/estimator_bus.c"

void Test_ControlQueueNotReady(void)
{
    PlatformCriticalState lock = EstimatorBus_IrqLock();
    s_initialized = 0U;
    EstimatorBus_IrqUnlock(lock);
}
