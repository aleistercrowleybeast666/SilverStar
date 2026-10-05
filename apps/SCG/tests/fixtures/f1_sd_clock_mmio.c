/* Actual F1 HAL_SD_InitCard and SDIO_Init; no MCU execution.
 * Host-only longjmp samples initialization CLKCR before card command traffic. */
#define _GNU_SOURCE
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
/* Windows ERROR collides with the ST ErrorStatus enumerator. Include Windows
 * before CMSIS __I/__O/CRC macros reach the host intrinsic headers. */
#undef ERROR
#else
#include <sys/mman.h>
#endif
#include "stm32f1xx_hal.h"
#include "platform_sd_clock.h"
#include "silverstar_assert.h"

static jmp_buf s_initialization_sample;
static uint32_t s_clock_hz;
static unsigned s_delay_count;
#define s_registers (*SDIO)
static SD_HandleTypeDef s_handle;
uint32_t SystemCoreClock = 64000000U;

static void Test_Check(int condition, unsigned line)
{
    if (!condition) { fprintf(stderr, "FAIL line=%u\n", line); exit(1); }
}
#undef assert
#define assert(condition_) Test_Check((condition_) != 0, __LINE__)

/* Link-only DMA dependencies of the full vendor module: outside this clock
 * fixture. Any execution is a test failure, rather than fabricated success. */
HAL_StatusTypeDef HAL_DMA_Start_IT(DMA_HandleTypeDef *h, uint32_t source,
    uint32_t destination, uint32_t length)
{
    (void)h; (void)source; (void)destination; (void)length;
    assert(0 && "unexpected DMA in SD clock fixture"); return HAL_ERROR;
}
HAL_StatusTypeDef HAL_DMA_Abort_IT(DMA_HandleTypeDef *h)
{ (void)h; assert(0 && "unexpected DMA abort"); return HAL_ERROR; }
HAL_StatusTypeDef HAL_DMA_Abort(DMA_HandleTypeDef *h)
{ (void)h; assert(0 && "unexpected DMA abort"); return HAL_ERROR; }

uint32_t HAL_RCC_GetHCLKFreq(void) { return s_clock_hz; }
uint32_t HAL_GetTick(void) { return 0U; }
void HAL_Delay(uint32_t delay)
{
    assert(delay == 2U);
    s_delay_count++;
    longjmp(s_initialization_sample, 1);
}
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    assert(condition != 0U);
}

static void Test_InitializationClock(uint32_t nominal_hz, uint32_t expected)
{
    uint32_t upper_hz = nominal_hz + (nominal_hz + 9U) / 10U;
    memset(&s_registers, 0, sizeof(s_registers));
    memset(&s_handle, 0, sizeof(s_handle));
    s_handle.Instance = &s_registers;
    s_handle.Init.ClockDiv = 2U;
    s_clock_hz = nominal_hz;
    s_delay_count = 0U;
    if (setjmp(s_initialization_sample) == 0)
    {
        (void)HAL_SD_InitCard(&s_handle);
        assert(0 && "initialization did not reach power-up sample");
    }
    assert(s_delay_count == 1U);
    printf("SD_INIT_REG nominal_hz=%lu upper_hz=%lu divider=%lu expected=%lu\n",
        (unsigned long)nominal_hz, (unsigned long)upper_hz,
        (unsigned long)(s_registers.CLKCR & SDIO_CLKCR_CLKDIV), (unsigned long)expected);
    fflush(stdout);
    assert((s_registers.CLKCR & SDIO_CLKCR_CLKDIV) == expected);
    assert((s_registers.CLKCR & SDIO_CLKCR_BYPASS) == 0U);
    /* Host mappings do not emulate ARM bit-band aliases. Verify the actual
     * enable write separately, without pretending it updates CLKCR here. */
    assert(*(volatile uint32_t *)(uintptr_t)CLKCR_CLKEN_BB == 1U);
    assert(upper_hz <= 350000U * (expected + 2U));
}

int main(void)
{
    uint32_t divider = UINT32_MAX;
    const uint32_t bad_clocks[] = {0U, 72000001U, UINT32_MAX};
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    void *mapped = VirtualAlloc((void *)(uintptr_t)0x40010000U, 65536U,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(mapped == (void *)(uintptr_t)0x40010000U);
    mapped = VirtualAlloc((void *)(uintptr_t)0x42300000U, 65536U,
        MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    assert(mapped == (void *)(uintptr_t)0x42300000U);
#else
    void *mapped = mmap((void *)(uintptr_t)0x40010000U, 65536U,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void *)(uintptr_t)0x40010000U);
    mapped = mmap((void *)(uintptr_t)0x42300000U, 65536U,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
    assert(mapped == (void *)(uintptr_t)0x42300000U);
#endif
    assert(PlatformSdClock_InitializationDividerResolve(64000000U, NULL) ==
        PlatformSdClockResult_InvalidArgument);
    Test_InitializationClock(64000000U, 200U);
    Test_InitializationClock(48000000U, 149U);
    Test_InitializationClock(72000000U, 225U);
    for (unsigned i=0U; i<sizeof(bad_clocks)/sizeof(bad_clocks[0]); i++)
    {
        divider = UINT32_MAX;
        assert(PlatformSdClock_InitializationDividerResolve(bad_clocks[i], &divider) ==
            PlatformSdClockResult_UnsupportedClock && divider == 0U);
        memset(&s_handle, 0, sizeof(s_handle));
        memset(&s_registers, 0xA5, sizeof(s_registers));
        s_handle.Instance = &s_registers;
        s_clock_hz = bad_clocks[i];
        s_delay_count = 0U;
        assert(HAL_SD_InitCard(&s_handle) == HAL_ERROR);
        assert(s_handle.ErrorCode == HAL_SD_ERROR_PARAM && s_delay_count == 0U);
        assert(s_registers.CLKCR == 0xA5A5A5A5U);
    }
    s_handle.Init.ClockDiv = 0U;
    s_handle.Init.ClockBypass = SDIO_CLOCK_BYPASS_DISABLE;
    s_clock_hz = 64000000U;
    s_registers.CLKCR = 0xA5A5A5A5U;
    s_delay_count = 0U;
    assert(HAL_SD_InitCard(&s_handle) == HAL_ERROR);
    assert(s_delay_count == 0U && s_registers.CLKCR == 0xA5A5A5A5U);
    assert(PlatformSdClock_TransferValidate(64000000U, 2U, 0U) == PlatformSdClockResult_Ok);
    assert(PlatformSdClock_TransferValidate(64000000U, 256U, 0U) == PlatformSdClockResult_InvalidArgument);
    assert(PlatformSdClock_TransferValidate(64000000U, 2U, SDIO_CLOCK_BYPASS_ENABLE) == PlatformSdClockResult_InvalidArgument);
    assert(PlatformSdClock_TransferValidate(72000000U, 1U, 0U) == PlatformSdClockResult_UnsupportedClock);
    s_handle.Init.ClockDiv = 2U;
    s_handle.Init.ClockBypass = SDIO_CLOCK_BYPASS_DISABLE;
    s_handle.Init.ClockEdge = SDIO_CLOCK_EDGE_RISING;
    s_handle.Init.ClockPowerSave = SDIO_CLOCK_POWER_SAVE_DISABLE;
    s_handle.Init.BusWide = SDIO_BUS_WIDE_1B;
    s_handle.Init.HardwareFlowControl = SDIO_HARDWARE_FLOW_CONTROL_DISABLE;
    assert(SDIO_Init(&s_registers, s_handle.Init) == HAL_OK);
    assert((s_registers.CLKCR & SDIO_CLKCR_CLKDIV) == 2U);
    assert((s_registers.CLKCR & SDIO_CLKCR_BYPASS) == 0U);
    printf("SD_TRANSFER_REG divider=2 nominal_hz=16000000 upper_hz=17600000\n");
    puts("SD_CLOCK_MMIO PASS; card commands and MCU timing NOT RUN");
    return 0;
}
