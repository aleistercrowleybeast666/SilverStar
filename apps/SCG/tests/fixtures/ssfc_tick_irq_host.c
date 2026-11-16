/* Host dispatch test only: the actual complete board IRQ translation unit is linked. */
#include "main.h"
#include <assert.h>

SD_HandleTypeDef hsd1;
DMA_HandleTypeDef hdma_usart1_rx;
DMA_HandleTypeDef hdma_usart1_tx;
DMA_HandleTypeDef hdma_usart2_rx;
DMA_HandleTypeDef hdma_usart2_tx;
UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;
TIM_HandleTypeDef htim6;
static unsigned int s_tick_dispatch_count;

void HAL_SD_IRQHandler(SD_HandleTypeDef *handle) { (void)handle; }
void HAL_DMA_IRQHandler(DMA_HandleTypeDef *handle) { (void)handle; }
void HAL_UART_IRQHandler(UART_HandleTypeDef *handle) { (void)handle; }
void HAL_GPIO_EXTI_IRQHandler(uint16_t pin) { (void)pin; }
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *handle)
{
    assert(handle == &htim6);
    s_tick_dispatch_count++;
}

int main(void)
{
    TIM6_DAC_IRQHandler();
    assert(s_tick_dispatch_count == 1U);
    return 0;
}
