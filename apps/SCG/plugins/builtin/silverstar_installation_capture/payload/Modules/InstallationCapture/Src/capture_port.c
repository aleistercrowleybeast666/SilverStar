#include "capture_port.h"
#include "platform_critical.h"

uint8_t CapturePort_Try(volatile uint8_t *gate)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint8_t accepted=(uint8_t)(*gate==0U);
    if(accepted!=0U){*gate=1U;}
    PlatformCritical_Exit(lock);
    __atomic_signal_fence(__ATOMIC_ACQUIRE);
    return accepted;
}

void CapturePort_Leave(volatile uint8_t *gate)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    __atomic_signal_fence(__ATOMIC_RELEASE);
    *gate=0U;
    PlatformCritical_Exit(lock);
}

uint8_t CapturePort_LostTake(volatile uint8_t *flag)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint8_t lost=*flag;*flag=0U;
    PlatformCritical_Exit(lock);
    return lost;
}

void CapturePort_LostSet(volatile uint8_t *flag)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    *flag=1U;
    PlatformCritical_Exit(lock);
}

uint32_t CapturePort_WordTake(volatile uint32_t *value)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint32_t result=*value;*value=0U;
    PlatformCritical_Exit(lock);
    __atomic_signal_fence(__ATOMIC_ACQUIRE);
    return result;
}

uint32_t CapturePort_WordRead(const volatile uint32_t *value)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint32_t result=*value;
    PlatformCritical_Exit(lock);
    __atomic_signal_fence(__ATOMIC_ACQUIRE);
    return result;
}

uint8_t CapturePort_WordPublish(volatile uint32_t *value,uint32_t token)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint8_t accepted=(uint8_t)(*value==0U||*value==token);
    __atomic_signal_fence(__ATOMIC_RELEASE);
    if(accepted!=0U){*value=token;}
    PlatformCritical_Exit(lock);
    return accepted;
}

void CapturePort_WordSet(volatile uint32_t *value,uint32_t token)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    __atomic_signal_fence(__ATOMIC_RELEASE);
    *value=token;
    PlatformCritical_Exit(lock);
}
