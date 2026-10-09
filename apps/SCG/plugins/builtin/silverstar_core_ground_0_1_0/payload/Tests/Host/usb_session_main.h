#ifndef __USB_MAIN_H
#define __USB_MAIN_H
#include <stdint.h>
extern uint32_t usb_test_mask;
void usb_guard_before_mask_hook(void);
static inline uint32_t __get_PRIMASK(void) { usb_guard_before_mask_hook(); return usb_test_mask; }
static inline void __disable_irq(void) { usb_test_mask = 1U; }
void usb_irq_after_restore_hook(void);
static inline void __set_PRIMASK(uint32_t mask) { usb_test_mask = mask; if (mask == 0U) { usb_irq_after_restore_hook(); } }
static inline void __DMB(void) { }
#endif
