/* Fault injection into the real owner; only the terminal trap is intercepted.
 * This Host-only harness never enters target firmware or demonstrates recovery. */
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static jmp_buf s_fault_return;
static _Noreturn void RotationReview_TerminalTrap(void)
{
    longjmp(s_fault_return, 1);
}
#define __builtin_trap() RotationReview_TerminalTrap()
#include "silverstar_assert.c"
#undef __builtin_trap
#define main RotationReview_NominalMain
#include "test_mag_rotation_runtime.c"
#undef main
#include "mag_rotation_runtime.c"

static RotationHistory s_history_before[ROTATION_HISTORY_COUNT];

int main(int argc, char *argv[])
{
    assert(argc == 2);
    s_now = 100000ULL;
    s_rotation.qualified = 1U;
    s_rotation.valid = 1U;
    s_rotation.edge_us = s_now;
    (void)memset(s_rotation.history, 0xa5, sizeof(s_rotation.history));
    (void)memcpy(s_history_before, s_rotation.history, sizeof(s_history_before));
    if (strcmp(argv[1], "head") == 0)
    {
        s_rotation.head = ROTATION_HISTORY_COUNT;
    }
    else
    {
        assert(strcmp(argv[1], "count") == 0);
        s_rotation.count = ROTATION_HISTORY_COUNT + 1U;
    }
    if (setjmp(s_fault_return) == 0)
    {
        if (strcmp(argv[1], "head") == 0)
        {
            const float gyro[3] = {0.1f, 0.2f, 0.3f};
            SystemMagRotation_ImuObserve(0U, 1U, 1U, 1U, s_now, gyro, 1U);
        }
        else
        {
            SystemMagRotation_Service(s_now);
        }
        assert(!"corrupt history state returned without the required fail-stop");
    }
    SilverStarAssertFaultRecord fault;
    assert(SilverStarAssert_FaultRecordGet(&fault) == 1U && fault.active == 1U);
    assert(fault.module_id == SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    assert(fault.reason_id == (strcmp(argv[1], "head") == 0 ?
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE : SILVERSTAR_ASSERT_REASON_STATE_INVARIANT));
    assert(s_rotation.qualified == 0U && s_rotation.valid == 0U);
    assert(memcmp(s_history_before, s_rotation.history, sizeof(s_history_before)) == 0);
    assert(s_adopted == 0U && s_fallback == 0U && s_locked == 0U);
    puts("PASS corrupt owner history traps before access/publication and revokes qualification");
    return 0;
}
