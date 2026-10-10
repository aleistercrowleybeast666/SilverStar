#ifndef __GROUND_RADIO_CONFIG_H
#define __GROUND_RADIO_CONFIG_H
#include "platform_gpio.h"

/* Ordered cold replacement only; no aggregation or command replay. */
#define GROUND_RADIO_INITIAL_INSTANCE 0U
#define GROUND_RADIO_FAILOVER_HOLD_MS 250U
#define GROUND_ACTIVITY_ENABLED 0U
#define GROUND_ACTIVITY_TX_GPIO ((PlatformGpioId)96U)
#define GROUND_ACTIVITY_RX_GPIO ((PlatformGpioId)96U)
#define GROUND_ACTIVITY_TX_ACTIVE_HIGH 0U
#define GROUND_ACTIVITY_RX_ACTIVE_HIGH 0U
#define GROUND_ACTIVITY_PULSE_MS 40U
#endif /* __GROUND_RADIO_CONFIG_H */
