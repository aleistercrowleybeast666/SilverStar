#include "platform_critical.h"
#include "main.h"
#include "silverstar_assert.h"

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState saved = __get_PRIMASK();
    __disable_irq();
    __DMB();
    return saved;
}

void PlatformCritical_Exit(PlatformCriticalState saved)
{
    SILVERSTAR_ASSERT(saved <= 1U, SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    __DMB();
    __set_PRIMASK(saved);
}
