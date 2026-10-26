#include "platform_boot_session.h"
#include "stm32f4xx_hal.h"

#define PLATFORM_BOOT_SESSION_POLL_BOUND 100000U
#define PLATFORM_BOOT_SESSION_SAMPLE_BOUND 4U

static uint32_t s_boot_session;

static PlatformResult PlatformBootSession_ClockStart(void)
{
    uint64_t input_hz;
    uint64_t rng_hz;
    RCC_OscInitTypeDef oscillator;
    HAL_RCC_GetOscConfig(&oscillator);
    if ((oscillator.PLL.PLLM == 0U) || (oscillator.PLL.PLLQ == 0U) ||
        ((RCC->CR & RCC_CR_PLLRDY) == 0U)) { return PLATFORM_NOT_READY; }
    input_hz = (oscillator.PLL.PLLSource == RCC_PLLSOURCE_HSE) ? HSE_VALUE : HSI_VALUE;
    rng_hz = input_hz * oscillator.PLL.PLLN /
        ((uint64_t)oscillator.PLL.PLLM * oscillator.PLL.PLLQ);
    if (rng_hz != 48000000ULL) { return PLATFORM_UNSUPPORTED; }
    __HAL_RCC_RNG_CLK_ENABLE();
    return PLATFORM_OK;
}

PlatformResult PlatformBootSession_Get(uint32_t *session)
{
    PlatformResult result;
    if (session == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    *session = 0U;
    if (s_boot_session != 0U) { *session = s_boot_session; return PLATFORM_OK; }
    result = PlatformBootSession_ClockStart();
    if (result != PLATFORM_OK) { return result; }
    RNG->CR |= RNG_CR_RNGEN;
    for (uint32_t sample = 0U; sample < PLATFORM_BOOT_SESSION_SAMPLE_BOUND; sample++)
    {
        for (uint32_t poll = 0U; poll < PLATFORM_BOOT_SESSION_POLL_BOUND; poll++)
        {
            uint32_t status = RNG->SR;
            if ((status & (RNG_SR_CECS | RNG_SR_SECS)) != 0U)
            { RNG->CR &= ~RNG_CR_RNGEN; return PLATFORM_IO_ERROR; }
            if ((status & RNG_SR_DRDY) != 0U)
            { s_boot_session = RNG->DR; break; }
        }
        if (s_boot_session != 0U)
        { RNG->CR &= ~RNG_CR_RNGEN; *session = s_boot_session; return PLATFORM_OK; }
    }
    RNG->CR &= ~RNG_CR_RNGEN;
    return PLATFORM_TIMEOUT;
}
