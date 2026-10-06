/* Host-only terminal boundary. Execute the real fault-record publication,
 * then terminate this process instead of invoking Windows crash reporting.
 * This is neither recovery nor code compiled into the MCU image. */
#include <assert.h>
#include <stdlib.h>
#include "silverstar_assert.h"
static _Noreturn void Test_TerminalTrap(void);
#define __builtin_trap Test_TerminalTrap
#include "silverstar_assert.c"
#undef __builtin_trap

static _Noreturn void Test_TerminalTrap(void)
{
    SilverStarAssertFaultRecord record;
    assert(SilverStarAssert_FaultRecordGet(&record) != 0U);
    assert(record.module_id == SILVERSTAR_ASSERT_MODULE_SYSTEM);
    assert(record.reason_id == SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    _Exit(86);
}
