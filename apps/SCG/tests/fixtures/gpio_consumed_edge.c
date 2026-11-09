/* Real platform backend, synthetic GPIO/clock/interrupt exclusion ports. */
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include GPIO_BACKEND_SOURCE

static GPIO_TypeDef s_port;
static uint32_t s_mask;
static uint8_t s_inject;
static uint64_t s_now;

uint8_t TEST_GPIO_RESOURCE_GET(PlatformGpioId id, TEST_GPIO_RESOURCE *out)
{
    assert((unsigned)id < SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT);
    if (id != PLATFORM_GPIO_0 && (unsigned)id != SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U)
    {
        return 0U;
    }
    *out = (TEST_GPIO_RESOURCE){&s_port, 4U, (uint8_t)(id != PLATFORM_GPIO_0)};
    return 1U;
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_mask;
    if (s_inject != 0U && s_mask == 0U)
    {
        s_inject = 0U;
        s_now++;
        HAL_GPIO_EXTI_Callback(4U);
    }
    s_mask = 1U;
    return previous;
}

void PlatformCritical_Exit(PlatformCriticalState previous)
{
    assert(s_mask == 1U);
    s_mask = previous;
}

uint64_t PlatformTime_Us(void)
{
    return s_now;
}

void HAL_GPIO_WritePin(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState state)
{
    assert(port == &s_port && pin == 4U);
    port->value = state == GPIO_PIN_SET ? pin : 0U;
}

GPIO_PinState HAL_GPIO_ReadPin(GPIO_TypeDef *port, uint16_t pin)
{
    assert(port == &s_port && pin == 4U);
    return port->value != 0U ? GPIO_PIN_SET : GPIO_PIN_RESET;
}

int main(void)
{
    PlatformGpioId last = (PlatformGpioId)(SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT - 1U);
    uint32_t number = 777U;
    uint64_t timestamp = 888ULL;
    assert(PlatformGpio_ConsumedEdgeGet((PlatformGpioId)-1, &number, &timestamp) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_ConsumedEdgeGet((PlatformGpioId)SILVERSTAR_PLATFORM_GPIO_CONTEXT_COUNT,
                                      &number, &timestamp) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_ConsumedEdgeGet(last, NULL, &timestamp) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, NULL) == PLATFORM_INVALID_ARGUMENT);
    assert(PlatformGpio_ConsumedEdgeGet(PLATFORM_GPIO_0, &number, &timestamp) == PLATFORM_NOT_READY);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_NOT_READY);
    assert(number == 777U && timestamp == 888ULL && s_mask == 0U);

    s_now = 0xffffffffULL;
    HAL_GPIO_EXTI_Callback(4U);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_NOT_READY);
    assert(number == 777U && timestamp == 888ULL);
    assert(PlatformGpio_IrqConsume(last) == 1U);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_OK);
    assert(number == 1U && timestamp == 0xffffffffULL);

    /* A pending IRQ immediately before the snapshot lock cannot publish a
     * new timestamp paired with the previously consumed sequence. */
    s_inject = 1U;
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_NOT_READY);
    assert(number == 1U && timestamp == 0xffffffffULL && s_mask == 0U);
    assert(PlatformGpio_IrqConsume(last) == 1U);
    s_mask = 1U;
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_OK);
    assert(number == 2U && timestamp == 0x100000000ULL && s_mask == 1U);
    s_mask = 0U;
    s_now++;
    HAL_GPIO_EXTI_Callback(4U);
    s_now++;
    HAL_GPIO_EXTI_Callback(4U);
    assert(PlatformGpio_IrqConsume(last) == 1U);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_NOT_READY);
    assert(number == 2U && timestamp == 0x100000000ULL);
    assert(PlatformGpio_IrqConsume(last) == 1U);
    assert(PlatformGpio_ConsumedEdgeGet(last, &number, &timestamp) == PLATFORM_OK);
    assert(number == 4U && timestamp == s_now && s_mask == 0U);
    puts("PASS invalid/missing/unconsumed inputs, coherent 64-bit edge, pending IRQ, nested lock, backlog");
    return 0;
}
