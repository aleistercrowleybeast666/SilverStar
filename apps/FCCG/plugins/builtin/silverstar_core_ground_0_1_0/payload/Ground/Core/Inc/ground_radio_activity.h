#ifndef __GROUND_RADIO_ACTIVITY_H
#define __GROUND_RADIO_ACTIVITY_H

#include <stdint.h>

void GroundRadioActivity_Init(uint32_t tx_ok, uint32_t rx_ok);
void GroundRadioActivity_Process(uint32_t now_ms, uint32_t tx_ok, uint32_t rx_ok);
uint32_t GroundRadioActivity_ErrorCountGet(void);

#endif /* __GROUND_RADIO_ACTIVITY_H */
