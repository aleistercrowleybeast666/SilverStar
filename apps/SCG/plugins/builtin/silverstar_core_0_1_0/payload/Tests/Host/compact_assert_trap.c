/* Actual fault capture, with only its terminal trap intercepted on Host.
 * No target build includes this file or the setjmp/longjmp harness. */
void TestCompact_TerminalTrap(void);
#define __builtin_trap TestCompact_TerminalTrap
#include "../../Common/Src/silverstar_assert.c"
