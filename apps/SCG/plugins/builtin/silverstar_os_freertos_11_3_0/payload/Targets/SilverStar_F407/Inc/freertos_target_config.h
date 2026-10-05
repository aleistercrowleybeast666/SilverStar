#ifndef __FREERTOS_TARGET_CONFIG_H
#define __FREERTOS_TARGET_CONFIG_H

#include "stm32f4xx.h"

extern uint32_t SystemCoreClock;

#define configCPU_CLOCK_HZ                              \
    ((uint32_t)SystemCoreClock)
#define configPRIO_BITS                                 \
    ((uint8_t)__NVIC_PRIO_BITS)
#define configLIBRARY_LOWEST_INTERRUPT_PRIORITY        15U
#define configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY   5U
#define configKERNEL_INTERRUPT_PRIORITY \
    (configLIBRARY_LOWEST_INTERRUPT_PRIORITY << (8U - configPRIO_BITS))
#define configMAX_SYSCALL_INTERRUPT_PRIORITY \
    (configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY << \
     (8U - configPRIO_BITS))

#define vPortSVCHandler    SVC_Handler
#define xPortPendSVHandler PendSV_Handler

#endif /* __FREERTOS_TARGET_CONFIG_H */
