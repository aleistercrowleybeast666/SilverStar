#include "platform_gpio.h"

#include "platform_critical.h"
#include "platform_stm32f4_resources.h"
#include "stm32f4xx_hal.h"

typedef struct
{
    GPIO_TypeDef *port;
    uint16_t pin;
    volatile uint32_t irq_count;
    uint32_t consumed_irq_count;
    uint8_t irq_enabled;
    uint8_t resource_loaded;
} PlatformGpioContext;

static PlatformGpioContext s_gpio[PLATFORM_GPIO_COUNT];

static PlatformGpioContext *PlatformGpio_ContextGet(PlatformGpioId id)
{
    PlatformStm32f4GpioResource resource;
    PlatformGpioContext *context;

    if ((uint32_t)id >= (uint32_t)PLATFORM_GPIO_COUNT) { return NULL; }
    context = &s_gpio[id];
    if (context->resource_loaded == 0U)
    {
        if (PlatformStm32f4Resource_GpioGet(id, &resource) == 0U)
        {
            return NULL;
        }
        context->port = (GPIO_TypeDef *)resource.port;
        context->pin = resource.pin;
        context->irq_enabled = resource.irq_enabled;
        context->resource_loaded = 1U;
    }
    return (context->port != NULL) ? context : NULL;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t logical_high)
{
    PlatformGpioContext *context = PlatformGpio_ContextGet(id);

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    HAL_GPIO_WritePin(context->port, context->pin,
                      (logical_high != 0U) ? GPIO_PIN_SET : GPIO_PIN_RESET);
    return PLATFORM_OK;
}

PlatformResult PlatformGpio_Read(PlatformGpioId id, uint8_t *logical_high)
{
    PlatformGpioContext *context = PlatformGpio_ContextGet(id);

    if ((context == NULL) || (logical_high == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *logical_high = (HAL_GPIO_ReadPin(context->port, context->pin) ==
                     GPIO_PIN_SET) ? 1U : 0U;
    return PLATFORM_OK;
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    PlatformGpioContext *context = PlatformGpio_ContextGet(id);
    PlatformCriticalState state;
    uint8_t pending = 0U;

    if ((context == NULL) || (context->irq_enabled == 0U)) { return 0U; }
    state = PlatformCritical_Enter();
    if (context->consumed_irq_count != context->irq_count)
    {
        context->consumed_irq_count++;
        pending = 1U;
    }
    PlatformCritical_Exit(state);
    return pending;
}

void HAL_GPIO_EXTI_Callback(uint16_t gpio_pin)
{
    PlatformGpioContext *context;
    uint8_t index;

    for (index = 0U; index < (uint8_t)PLATFORM_GPIO_COUNT; index++)
    {
        context = PlatformGpio_ContextGet((PlatformGpioId)index);
        if ((context != NULL) && (context->irq_enabled != 0U) &&
            (context->pin == gpio_pin))
        {
            context->irq_count++;
        }
    }
}
