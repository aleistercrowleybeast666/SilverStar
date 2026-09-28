#ifndef __GROUND_RADIO_H
#define __GROUND_RADIO_H

#include <stdint.h>

typedef enum
{
    GROUND_RADIO_OK = 0U,
    GROUND_RADIO_EMPTY,
    GROUND_RADIO_BUSY,
    GROUND_RADIO_ERROR
} GroundRadioResult;

typedef struct
{
    uint8_t radio_state;
    uint32_t tx_ok;
    uint32_t rx_ok;
    uint32_t rx_crc_error;
    uint32_t tx_timeout;
    uint32_t rx_timeout;
    uint32_t tx_dropped;
    uint32_t rx_dropped;
} GroundRadioStats;

GroundRadioResult GroundRadio_Init(void);
void GroundRadio_Process(void);
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length);
GroundRadioResult GroundRadio_RxDequeue(
    uint8_t *data, uint8_t *length, int8_t *rssi_dbm, int8_t *snr_db);
void GroundRadio_StatsGet(GroundRadioStats *stats);

#endif /* __GROUND_RADIO_H */
