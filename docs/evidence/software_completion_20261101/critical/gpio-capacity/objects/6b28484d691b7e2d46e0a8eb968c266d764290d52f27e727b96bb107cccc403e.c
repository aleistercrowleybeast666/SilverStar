#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include "platform_gpio_stm32f4.c"
static GPIO_TypeDef port;
static uint32_t mask;
static unsigned highest_lookup;
uint8_t PlatformStm32f4Resource_GpioGet(PlatformGpioId id, PlatformStm32f4GpioResource *out)
{
    assert((unsigned)id < PLATFORM_GPIO_COUNT);
    if ((unsigned)id > highest_lookup) { highest_lookup = (unsigned)id; }
    if ((id != PLATFORM_GPIO_0) && ((unsigned)id != SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U)) { return 0U; }
    *out = (PlatformStm32f4GpioResource){&port, 4U, (uint8_t)(id != PLATFORM_GPIO_0)};
    return 1U;
}
PlatformCriticalState PlatformCritical_Enter(void) { PlatformCriticalState previous = mask; mask = 1U; return previous; }
void PlatformCritical_Exit(PlatformCriticalState previous) { assert(mask == 1U); mask = previous; }
void HAL_GPIO_WritePin(GPIO_TypeDef *p, uint16_t pin, GPIO_PinState state)
{ assert(p == &port && pin == 4U); p->value = (state == GPIO_PIN_SET) ? pin : 0U; }
GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *p, uint16_t pin)
{ assert(p == &port && pin == 4U); return p->value ? GPIO_PIN_SET : GPIO_PIN_RESET; }
int main(void)
{
    uint8_t value = 77U;
    PlatformGpioId last = (PlatformGpioId)(SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U);
    assert(PlatformGpio_Write(PLATFORM_GPIO_0, 1U) == PLATFORM_OK);
    assert(PlatformGpio_Read(PLATFORM_GPIO_0, &value) == PLATFORM_OK && value == 1U);
    assert(PlatformGpio_Write(last, 0U) == PLATFORM_OK);
    assert(PlatformGpio_Write(PLATFORM_GPIO_1, 1U) == PLATFORM_INVALID_ARGUMENT);
    value = 77U;
    assert(PlatformGpio_Read((PlatformGpioId)SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT, &value) == PLATFORM_INVALID_ARGUMENT && value == 77U);
    assert(PlatformGpio_Write((PlatformGpioId)-1, 1U) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_Read(PLATFORM_GPIO_0, NULL) == PLATFORM_INVALID_ARGUMENT);
    HAL_GPIO_EXTI_Callback(8U);
    assert(PlatformGpio_IrqConsume(last) == 0U);
    HAL_GPIO_EXTI_Callback(4U); HAL_GPIO_EXTI_Callback(4U);
    mask = 1U;
    assert(PlatformGpio_IrqConsume(last) == 1U && mask == 1U);
    mask = 0U;
    assert(PlatformGpio_IrqConsume(last) == 1U && mask == 0U);
    assert(PlatformGpio_IrqConsume(last) == 0U);
    assert(PlatformGpio_IrqConsume(PLATFORM_GPIO_0) == 0U);
    assert(PlatformGpio_IrqConsume((PlatformGpioId)-1) == 0U);
    printf("allocated=%zu configured=%u highest_lookup=%u\n", sizeof(s_gpio)/sizeof(s_gpio[0]), SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT, highest_lookup);
    fflush(stdout);
    assert(sizeof(s_gpio)/sizeof(s_gpio[0]) == SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT);
    assert(highest_lookup < SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT);
    return 0;
}
