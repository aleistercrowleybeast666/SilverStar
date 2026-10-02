#include "ground_radio.h"

#include <string.h>
#include <stddef.h>

#include "sx1281_device.h"

#define GROUND_RADIO_INSTANCE 0U

GroundRadioResult GroundRadio_Init(void)
{
    if (Lora_Init(GROUND_RADIO_INSTANCE) != LORA_INIT_OK)
    {
        return GROUND_RADIO_ERROR;
    }
    if (Lora_ApplyDefaultConfig(GROUND_RADIO_INSTANCE) != LORA_CONFIG_OK)
    {
        return GROUND_RADIO_ERROR;
    }
    if (Lora_ScheduleRoleSet(GROUND_RADIO_INSTANCE, LoraScheduleRole_Ground) !=
        LoraScheduleRoleResult_Ok)
    {
        return GROUND_RADIO_ERROR;
    }
    Lora_StartRx(GROUND_RADIO_INSTANCE);
    return GROUND_RADIO_OK;
}

void GroundRadio_Process(void)
{
    Lora_Process(GROUND_RADIO_INSTANCE);
}

GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{
    LoraTxEnqueueResult result = Lora_TxEnqueue(GROUND_RADIO_INSTANCE, data, length);
    if (result == LORA_TX_ENQUEUE_OK)
    {
        return GROUND_RADIO_OK;
    }
    return (result == LORA_TX_ENQUEUE_QUEUE_FULL) ? GROUND_RADIO_BUSY : GROUND_RADIO_ERROR;
}

GroundRadioResult GroundRadio_RxDequeue(
    uint8_t *data, uint8_t *length, int8_t *rssi_dbm, int8_t *snr_db)
{
    LoraRxDequeueResult result = Lora_RxDequeue(
        GROUND_RADIO_INSTANCE, data, length, rssi_dbm, snr_db);
    if (result == LORA_RX_DEQUEUE_OK)
    {
        return GROUND_RADIO_OK;
    }
    return (result == LORA_RX_DEQUEUE_EMPTY) ? GROUND_RADIO_EMPTY : GROUND_RADIO_ERROR;
}

void GroundRadio_StatsGet(GroundRadioStats *stats)
{
    LoraStats source;
    if (stats == NULL)
    {
        return;
    }
    memset(&source, 0, sizeof(source));
    Lora_GetStats(GROUND_RADIO_INSTANCE, &source);
    stats->radio_state = (uint8_t)source.radio_state;
    stats->tx_ok = source.tx_ok;
    stats->rx_ok = source.rx_ok;
    stats->rx_crc_error = source.rx_crc_error;
    stats->tx_timeout = source.tx_timeout;
    stats->rx_timeout = source.rx_timeout;
    stats->tx_dropped = source.tx_dropped;
    stats->rx_dropped = source.rx_dropped;
}
