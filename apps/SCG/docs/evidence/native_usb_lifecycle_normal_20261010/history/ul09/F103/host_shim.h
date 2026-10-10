#ifndef __HOST_USB_SHIM_H
#define __HOST_USB_SHIM_H
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#define __ALIGN_BEGIN
#define __ALIGN_END __attribute__((aligned(4)))
#define __PACKED __attribute__((packed))
#define __IO volatile
#define __STATIC_INLINE static inline
#define UNUSED(x) ((void)(x))
#define UID_BASE 0x1FFFF000U
#define __DMB() ((void)0)
extern uint32_t host_mask;
static inline uint32_t __get_PRIMASK(void) { return host_mask; }
static inline void __disable_irq(void) { host_mask=1U; }
static inline void __set_PRIMASK(uint32_t v) { host_mask=v; }
typedef struct {struct {uint32_t maxpacket;} IN_ep[8];} PCD_HandleTypeDef;
static inline void HAL_Delay(uint32_t v) { (void)v; }
#endif
