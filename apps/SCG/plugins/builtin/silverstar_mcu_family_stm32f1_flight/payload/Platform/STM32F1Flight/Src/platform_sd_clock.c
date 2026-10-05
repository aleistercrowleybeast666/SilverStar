#include "platform_sd_clock.h"

#include <stddef.h>

#include "silverstar_assert.h"

/* DS5792 Rev 13 table 25 gives factory HSI +2.5% at 3.3 V, -40..105 C.
 * A 10% upper clock allowance and 350 kHz target provide further headroom;
 * this calculation is not a measurement or qualification outside that domain.
 * F103 SDIO clock is HCLK; divider field is 8 bits, clock = HCLK/(div+2). */
#define SD_CLOCK_NOMINAL_MAX_HZ 72000000U
#define SD_CLOCK_INIT_TARGET_HZ 350000U
#define SD_CLOCK_INIT_LIMIT_HZ 400000U
#define SD_CLOCK_DIVIDER_MAX 255U

PlatformSdClockResult PlatformSdClock_InitializationDividerResolve(
    uint32_t nominal_sdioclk_hz, uint32_t *divider)
{
    uint32_t upper_hz;
    uint32_t denominator;
    uint32_t selected;

    if (divider == NULL) { return PlatformSdClockResult_InvalidArgument; }
    *divider = 0U;
    if ((nominal_sdioclk_hz == 0U) ||
        (nominal_sdioclk_hz > SD_CLOCK_NOMINAL_MAX_HZ))
    { return PlatformSdClockResult_UnsupportedClock; }
    upper_hz = nominal_sdioclk_hz + (nominal_sdioclk_hz + 9U) / 10U;
    denominator = (upper_hz + SD_CLOCK_INIT_TARGET_HZ - 1U) /
                  SD_CLOCK_INIT_TARGET_HZ;
    if (denominator < 2U) { denominator = 2U; }
    selected = denominator - 2U;
    if (selected > SD_CLOCK_DIVIDER_MAX)
    { return PlatformSdClockResult_UnsupportedClock; }
    SILVERSTAR_ASSERT(upper_hz <= SD_CLOCK_INIT_LIMIT_HZ * denominator,
        SILVERSTAR_ASSERT_MODULE_PLATFORM, SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    *divider = selected;
    return PlatformSdClockResult_Ok;
}

PlatformSdClockResult PlatformSdClock_TransferValidate(
    uint32_t nominal_sdioclk_hz, uint32_t divider, uint32_t bypass_enabled)
{
    uint32_t upper_hz;
    if ((divider > SD_CLOCK_DIVIDER_MAX) || (bypass_enabled != 0U))
    { return PlatformSdClockResult_InvalidArgument; }
    if ((nominal_sdioclk_hz == 0U) ||
        (nominal_sdioclk_hz > SD_CLOCK_NOMINAL_MAX_HZ))
    { return PlatformSdClockResult_UnsupportedClock; }
    upper_hz = nominal_sdioclk_hz + (nominal_sdioclk_hz + 9U) / 10U;
    if ((uint64_t)upper_hz > 25000000ULL * (divider + 2U))
    { return PlatformSdClockResult_UnsupportedClock; }
    return PlatformSdClockResult_Ok;
}
