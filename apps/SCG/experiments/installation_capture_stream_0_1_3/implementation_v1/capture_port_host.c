/* Host port only. The target uses the existing PlatformCritical interface. */
#include <capture_port.h>
uint8_t CapturePort_Try(volatile uint8_t *gate)
{
    uint8_t expected=0U;
    return (uint8_t)__atomic_compare_exchange_n(gate,&expected,1U,1,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED);
}
void CapturePort_Leave(volatile uint8_t *gate)
{ __atomic_store_n(gate,0U,__ATOMIC_RELEASE); }
uint8_t CapturePort_LostTake(volatile uint8_t *flag)
{ return __atomic_exchange_n(flag,0U,__ATOMIC_ACQUIRE); }
void CapturePort_LostSet(volatile uint8_t *flag)
{ __atomic_store_n(flag,1U,__ATOMIC_RELEASE); }

uint32_t CapturePort_WordTake(volatile uint32_t *value)
{ return __atomic_exchange_n(value,0U,__ATOMIC_ACQUIRE); }
uint32_t CapturePort_WordRead(const volatile uint32_t *value)
{ return __atomic_load_n(value,__ATOMIC_ACQUIRE); }
uint8_t CapturePort_WordPublish(volatile uint32_t *value,uint32_t token)
{
    uint32_t expected=0U;
    if(__atomic_compare_exchange_n(value,&expected,token,0,__ATOMIC_RELEASE,__ATOMIC_RELAXED)){return 1U;}
    return (uint8_t)(expected==token);
}
void CapturePort_WordSet(volatile uint32_t *value,uint32_t token)
{__atomic_store_n(value,token,__ATOMIC_RELEASE);}
