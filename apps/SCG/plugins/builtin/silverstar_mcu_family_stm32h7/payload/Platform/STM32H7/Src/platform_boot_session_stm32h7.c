#include "platform_boot_session.h"
#include "stm32h7xx_hal.h"

#define PLATFORM_BOOT_SESSION_POLL_BOUND 100000U
#define PLATFORM_BOOT_SESSION_SAMPLE_BOUND 4U

static uint32_t s_boot_session;

static PlatformResult PlatformBootSession_ClockStart(void)
{
    __HAL_RCC_HSI48_ENABLE();
    for (uint32_t poll = 0U; poll < PLATFORM_BOOT_SESSION_POLL_BOUND; poll++)
    {
        if ((RCC->CR & RCC_CR_HSI48RDY) != 0U) { break; }
    }
    if ((RCC->CR & RCC_CR_HSI48RDY) == 0U) { return PLATFORM_TIMEOUT; }
    /* Dedicated RNG kernel clock; never change SYSCLK or radio clocks. */
    MODIFY_REG(RCC->D2CCIP2R, RCC_D2CCIP2R_RNGSEL, RCC_RNGCLKSOURCE_HSI48);
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
