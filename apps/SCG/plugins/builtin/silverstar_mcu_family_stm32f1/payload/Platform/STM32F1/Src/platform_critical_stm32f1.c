#include "platform_critical.h"

#include "cmsis_gcc.h"

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState state = __get_PRIMASK();

    __disable_irq();
    return state;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    if (state == 0U)
    {
        __enable_irq();
    }
}
