#ifndef __USB_MAIN_H
#define __USB_MAIN_H
#include <stdint.h>
extern uint32_t usb_test_mask;
static inline uint32_t __get_PRIMASK(void) { return usb_test_mask; }
static inline void __disable_irq(void) { usb_test_mask = 1U; }
static inline void __set_PRIMASK(uint32_t mask) { usb_test_mask = mask; }
static inline void __DMB(void) { }
#endif
