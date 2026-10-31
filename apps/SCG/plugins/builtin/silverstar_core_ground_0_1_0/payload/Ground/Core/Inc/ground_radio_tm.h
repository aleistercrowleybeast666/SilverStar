#ifndef __GROUND_RADIO_TM_H
#define __GROUND_RADIO_TM_H
#include <stdint.h>
/* One direction/session owner, shared by the exact physical radio backends.
 * Passive persists across PC reconnect and driver reset within this MCU boot. */
void GroundRadioTm_Observe(const uint8_t *data, uint8_t length);
uint8_t GroundRadioTm_PassiveGet(void);
#endif /* __GROUND_RADIO_TM_H */
