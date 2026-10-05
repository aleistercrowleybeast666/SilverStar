#include "FreeRTOS.h"
#include "task.h"
#include "stm32f4xx_it.h"

extern void xPortSysTickHandler(void);
void SysTick_Handler(void);

void SysTick_Handler(void)
{
    if (xTaskGetSchedulerState() != taskSCHEDULER_NOT_STARTED)
    {
        xPortSysTickHandler();
    }
}
