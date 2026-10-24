#include "ground_radio.h"
#include "sx1278_device.h"
#include "ground_radio_activity.h"
#include "ground_radio_config.h"
#include "gsp_min_protocol.h"
#include "platform_time.h"
#include <stddef.h>
#include <string.h>

uint8_t GroundRadio_MetricsSupportedGet(void) { return 0U; }
uint8_t GroundRadio_ActiveInstanceGet(void) { return 0U; }

GroundRadioResult GroundRadio_Init(void)
{
    Sx1278Result result = Sx1278_Init(0U);
    if ((result != Sx1278Result_Ok) && (result != Sx1278Result_Busy)) { return GROUND_RADIO_ERROR; }
    if (Sx1278_Start(0U) != Sx1278Result_Ok) { return GROUND_RADIO_ERROR; }
    if (GROUND_ACTIVITY_ENABLED != 0U) { GroundRadioActivity_Init(0U, 0U); }
    return GROUND_RADIO_OK;
}

void GroundRadio_Process(void)
{
    Sx1278Stats stats;
    Sx1278Result result = Sx1278_Process(0U);
    if ((result != Sx1278Result_Ok) && (result != Sx1278Result_Offline)) { return; }
    if ((GROUND_ACTIVITY_ENABLED != 0U) && (Sx1278_StatsGet(0U, &stats) == Sx1278Result_Ok))
    { GroundRadioActivity_Process(PlatformTime_Ms(), stats.tx_ok, stats.rx_ok); }
}

GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{
    Sx1278Result result = Sx1278_Send(0U, data, length, 1U, NULL);
    if (result == Sx1278Result_Ok) { return GROUND_RADIO_OK; }
    return ((result == Sx1278Result_Busy) || (result == Sx1278Result_Offline)) ? GROUND_RADIO_BUSY : GROUND_RADIO_ERROR;
}

GroundRadioResult GroundRadio_RxDequeue(uint8_t *data, uint8_t *length,
    int8_t *rssi_dbm, int8_t *snr_db)
{
    uint16_t received = 0U;
    Sx1278Result result;
    if (length == NULL) { return GROUND_RADIO_ERROR; }
    *length = 0U;
    /* Unsupported measurements: typed GSP response omits numeric metrics. */
    (void)rssi_dbm; (void)snr_db;
    result = Sx1278_Receive(0U, data, SX1278_PACKET_CAPACITY, &received);
    if (result == Sx1278Result_Empty) { return GROUND_RADIO_EMPTY; }
    if (result != Sx1278Result_Ok) { return GROUND_RADIO_ERROR; }
    *length = (uint8_t)received;
    return GROUND_RADIO_OK;
}

void GroundRadio_StatsGet(GroundRadioStats *stats)
{
    Sx1278Stats source;
    if (stats == NULL) { return; }
    (void)memset(stats, 0, sizeof(*stats));
    if (Sx1278_StatsGet(0U, &source) != Sx1278Result_Ok) { return; }
    stats->radio_state = (source.ready == 0U) ? GSP_RADIO_STATE_NOT_INIT : GSP_RADIO_STATE_READY;
    stats->tx_ok = source.tx_ok; stats->rx_ok = source.rx_ok;
    stats->rx_crc_error = source.rx_crc_error; stats->tx_timeout = source.tx_timeout;
    stats->tx_dropped = source.tx_dropped; stats->rx_dropped = source.rx_dropped;
}
