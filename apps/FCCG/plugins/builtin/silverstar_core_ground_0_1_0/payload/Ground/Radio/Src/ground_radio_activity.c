#include "ground_radio_activity.h"

#include <string.h>

#include "ground_radio_config.h"
#include "platform_gpio.h"
#include "silverstar_assert.h"

typedef struct
{
    uint32_t started_ms;
    uint8_t active;
    uint8_t used;
} GroundRadioActivityState;

static GroundRadioActivityState s_leds[2];
static uint32_t s_last_tx;
static uint32_t s_last_rx;
static uint32_t s_errors;
static const PlatformGpioId s_gpio[2] =
    {GROUND_ACTIVITY_TX_GPIO, GROUND_ACTIVITY_RX_GPIO};
static const uint8_t s_active_high[2] =
    {GROUND_ACTIVITY_TX_ACTIVE_HIGH, GROUND_ACTIVITY_RX_ACTIVE_HIGH};

static uint8_t GroundRadioActivity_Write(uint8_t channel, uint8_t on)
{
    PlatformResult result;
    SILVERSTAR_ASSERT(channel < 2U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(on <= 1U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_gpio[channel] == PLATFORM_GPIO_COUNT) { return 1U; }
    result = PlatformGpio_Write(s_gpio[channel], on != 0U ?
        s_active_high[channel] : (uint8_t)(1U - s_active_high[channel]));
    if (result == PLATFORM_OK) { return 1U; }
    if (s_errors < UINT32_MAX) { s_errors++; }
    return 0U;
}

void GroundRadioActivity_Init(uint32_t tx_ok, uint32_t rx_ok)
{
    uint8_t channel;
    memset(s_leds, 0, sizeof(s_leds));
    s_last_tx = tx_ok;
    s_last_rx = rx_ok;
    if (GROUND_ACTIVITY_ENABLED == 0U) { return; }
    for (channel = 0U; channel < 2U; channel++)
    {
        if ((channel == 1U) && (s_gpio[0] == s_gpio[1])) { continue; }
        /* A failed off-write stays pending and is retried once per loop. */
        if (GroundRadioActivity_Write(channel, 0U) == 0U)
        { s_leds[channel].active = 1U; }
    }
}

static void GroundRadioActivity_ChannelProcess(uint8_t channel,
    uint32_t now_ms, uint8_t event)
{
    SILVERSTAR_ASSERT(channel < 2U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_leds[channel].active <= 1U) &&
        (s_leds[channel].used <= 1U), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_gpio[channel] == PLATFORM_GPIO_COUNT) { return; }
    if (s_leds[channel].active != 0U)
    {
        if ((s_leds[channel].used == 0U) ||
            ((uint32_t)(now_ms - s_leds[channel].started_ms) >= GROUND_ACTIVITY_PULSE_MS))
        {
            if (GroundRadioActivity_Write(channel, 0U) != 0U)
            { s_leds[channel].active = 0U; s_leds[channel].started_ms = now_ms; }
        }
        return; /* New events never extend an existing pulse. */
    }
    if ((event != 0U) && ((s_leds[channel].used == 0U) ||
        ((uint32_t)(now_ms - s_leds[channel].started_ms) >= 1U)))
    {
        if (GroundRadioActivity_Write(channel, 1U) != 0U)
        {
            s_leds[channel].started_ms = now_ms;
            s_leds[channel].active = 1U;
            s_leds[channel].used = 1U;
        }
    }
}

void GroundRadioActivity_Process(uint32_t now_ms, uint32_t tx_ok, uint32_t rx_ok)
{
    uint8_t tx_event;
    uint8_t rx_event;
    if (GROUND_ACTIVITY_ENABLED == 0U) { return; }
    tx_event = (uint8_t)(tx_ok != s_last_tx);
    rx_event = (uint8_t)(rx_ok != s_last_rx);
    s_last_tx = tx_ok;
    s_last_rx = rx_ok;
    if (s_gpio[0] == s_gpio[1])
    { GroundRadioActivity_ChannelProcess(0U, now_ms, (uint8_t)(tx_event | rx_event)); }
    else
    {
        GroundRadioActivity_ChannelProcess(0U, now_ms, tx_event);
        GroundRadioActivity_ChannelProcess(1U, now_ms, rx_event);
    }
}

uint32_t GroundRadioActivity_ErrorCountGet(void) { return s_errors; }
