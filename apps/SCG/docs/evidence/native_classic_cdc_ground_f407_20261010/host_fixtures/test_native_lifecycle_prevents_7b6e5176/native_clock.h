#include <stdint.h>
typedef enum { NativeClockResult_Ok, NativeClockResult_Stopped } NativeClockResult;
NativeClockResult NativeClock_StatusGet(void);
NativeClockResult NativeClock_DelayUs(uint32_t delay);
NativeClockResult NativeClock_Read(uint64_t *time);
