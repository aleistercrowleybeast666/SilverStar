#ifndef __SX1278_DEVICE_H
#define __SX1278_DEVICE_H

#include "sx1278_chip.h"

typedef struct
{
    uint64_t last_tx_us, last_rx_us;
    uint32_t tx_ok, rx_ok, tx_timeout, tx_dropped, rx_dropped, rx_crc_error;
    uint32_t transport_error, bus_timeout, recovery_attempts, last_tx_ms, last_rx_ms;
    uint8_t state, ready, initialized, started;
} Sx1278Stats;

/* Init/Start/Stop enqueue lifecycle requests. Process is the sole SPI/GPIO owner.
 * Call Process from one task only; never from EXTI. IRQ flags are also polled.
 * A successful Send accepts a bounded queue item; ReceiptGet reports RF TxDone.
 * Stop is latched across a later Start. Process must quiesce/discard the prior
 * session before restarting; IO failure during quiescence remains observable.
 * RSSI/SNR are deliberately unsupported until board measurements are verified. */
Sx1278Result Sx1278_Init(uint8_t instance);
Sx1278Result Sx1278_Start(uint8_t instance);
Sx1278Result Sx1278_Stop(uint8_t instance);
/* Busy until the Process owner confirms reset/RF-switch quiescence; Io
 * preserves a failed attempt. Continue the owner while a stop is pending. */
Sx1278Result Sx1278_StopStatusGet(uint8_t instance);
Sx1278Result Sx1278_Process(uint8_t instance);
Sx1278Result Sx1278_Send(uint8_t instance, const uint8_t *data,
    uint16_t length, uint8_t control, uint32_t *transaction_id);
Sx1278Result Sx1278_ReceiptGet(uint8_t instance, uint32_t transaction_id,
    uint32_t *age_ms);
Sx1278Result Sx1278_Receive(uint8_t instance, uint8_t *data,
    uint16_t capacity, uint16_t *length);
Sx1278Result Sx1278_StatsGet(uint8_t instance, Sx1278Stats *stats);

#endif /* __SX1278_DEVICE_H */
