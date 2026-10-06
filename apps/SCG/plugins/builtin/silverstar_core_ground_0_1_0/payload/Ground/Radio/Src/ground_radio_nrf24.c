#include "ground_radio.h"

#include <stddef.h>
#include <string.h>
#include "ground_radio_activity.h"
#include "ground_radio_config.h"
#include "gsp_min_protocol.h"
#include "nrf24_device.h"
#include "platform_time.h"

/* One bare-metal owner. No multi-node/family switching, ISR SPI or replay. */
uint8_t GroundRadio_MetricsSupportedGet(void) { return 0U; }

GroundRadioResult GroundRadio_Init(void)
{
    Nrf24Result result = Nrf24_Init(0U);
    if ((result != Nrf24Result_Ok) && (result != Nrf24Result_Busy))
    { return GROUND_RADIO_ERROR; }
    if (Nrf24_Start(0U) != Nrf24Result_Ok) { return GROUND_RADIO_ERROR; }
    if (GROUND_ACTIVITY_ENABLED != 0U) { GroundRadioActivity_Init(0U, 0U); }
    return GROUND_RADIO_OK; /* Context accepted; READY remains asynchronous. */
}

void GroundRadio_Process(void)
{
    Nrf24Stats stats;
    Nrf24_Process(0U);
    if ((GROUND_ACTIVITY_ENABLED != 0U) &&
        (Nrf24_StatsGet(0U, &stats) == Nrf24Result_Ok))
    { GroundRadioActivity_Process(PlatformTime_Ms(), stats.tx_ok, stats.rx_ok); }
}

uint8_t GroundRadio_ActiveInstanceGet(void) { return 0U; }

GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{
    Nrf24Result result = Nrf24_Send(0U, data, length, 1U, NULL);
    if (result == Nrf24Result_Ok) { return GROUND_RADIO_OK; }
    if ((result == Nrf24Result_Busy) || (result == Nrf24Result_Offline))
    { return GROUND_RADIO_BUSY; }
    return GROUND_RADIO_ERROR;
}

GroundRadioResult GroundRadio_RxDequeue(uint8_t *data, uint8_t *length,
    int8_t *rssi_dbm, int8_t *snr_db)
{
    uint16_t received = 0U;
    Nrf24Result result;
    if (length == NULL) { return GROUND_RADIO_ERROR; }
    *length = 0U;
    /* Legacy pointer slots have no meaning on NRF; the typed GSP output has
     * no numeric fields. Do not manufacture measurements through these slots. */
    (void)rssi_dbm; (void)snr_db;
    result = Nrf24_Receive(0U, data, 61U, &received);
    if (result == Nrf24Result_Empty) { return GROUND_RADIO_EMPTY; }
    if ((result != Nrf24Result_Ok) || (received > 61U)) { return GROUND_RADIO_ERROR; }
    *length = (uint8_t)received;
    return GROUND_RADIO_OK;
}

void GroundRadio_StatsGet(GroundRadioStats *stats)
{
    Nrf24Stats source;
    if (stats == NULL) { return; }
    (void)memset(stats, 0, sizeof(*stats));
    if (Nrf24_StatsGet(0U, &source) != Nrf24Result_Ok) { return; }
    stats->radio_state = (source.ready == 0U) ? GSP_RADIO_STATE_NOT_INIT : GSP_RADIO_STATE_READY;
    stats->tx_ok = source.tx_ok; stats->rx_ok = source.rx_ok;
    stats->rx_crc_error = source.rx_crc_error; stats->tx_timeout = source.tx_timeout;
    stats->tx_dropped = source.tx_dropped; stats->rx_dropped = source.rx_dropped;
}
