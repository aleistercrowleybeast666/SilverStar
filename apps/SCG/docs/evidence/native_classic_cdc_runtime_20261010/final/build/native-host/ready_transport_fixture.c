#include "native_runtime.h"
#include "native_clock.h"
#include <assert.h>
extern uint32_t usb_test_mask;
/* Existing transport regression cases are scoped to an already-ready runtime.
 * Initialization/fault lifecycle is exercised separately with the real runtime. */
uint8_t NativeRuntime_ReadyGet(void) { return 1U; }
uint8_t NativeClock_ContextAllowedGet(void) { return usb_test_mask == 0U ? 1U : 0U; }
NativeClockResult NativeClock_DelayUs(uint32_t delay)
{ assert(delay == 1U && usb_test_mask == 0U); return NativeClockResult_Ok; }
