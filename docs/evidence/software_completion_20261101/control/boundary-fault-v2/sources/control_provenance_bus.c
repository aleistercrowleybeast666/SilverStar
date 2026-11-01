/* Actual bus implementation. Only its admission state is fault-injected after
 * successful real START; this is not an alternative target bus implementation. */
#include "D:/python_software/SilverStar/.work/0.1.3-software-completion-20261101/control/pytest-v5/control-research-pid0/Flight_Controller/APP/Src/estimator_bus.c"

void Test_ControlQueueNotReady(void)
{
    PlatformCriticalState lock = EstimatorBus_IrqLock();
    s_initialized = 0U;
    EstimatorBus_IrqUnlock(lock);
}
