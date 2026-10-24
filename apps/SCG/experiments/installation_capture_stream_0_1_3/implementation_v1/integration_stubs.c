/* Link/test boundary only. No vector table, hardware I/O or firmware startup. */
#include "system_console_if.h"
#include "silverstar_assert.h"
#include <stddef.h>
#include <stdint.h>

void SilverStarAssert_Check(uint8_t condition,SilverStarAssertModuleId module,
    const char *file,uint32_t line,SilverStarAssertReasonId reason)
{ if(condition==0U){SilverStarAssert_Fail(module,file,line,reason);} }

void SilverStarAssert_ObjectCheck(const volatile void *object,uint32_t alignment,
    SilverStarAssertModuleId module,const char *file,uint32_t line)
{
    if(object==NULL||alignment==0U||((uintptr_t)object%alignment)!=0U){
        SilverStarAssert_Fail(module,file,line,SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    }
}

SystemDeviceResult SystemConsoleDevice_Write(const uint8_t *data,uint16_t length)
{
    if(data==NULL||length==0U){return SYSTEM_DEVICE_INVALID_ARGUMENT;}
    return SYSTEM_DEVICE_NOT_READY;
}

_Noreturn void SilverStarAssert_Fail(SilverStarAssertModuleId module,
    const char *file,uint32_t line,SilverStarAssertReasonId reason)
{
    (void)module;(void)reason;(void)file;(void)line;
#if defined(__arm__) || defined(__thumb__)
    for(;;){__asm__ volatile("wfi");}
#else
    __builtin_trap();
#endif
}
