#ifndef __NRF24_DEVICE_H
#define __NRF24_DEVICE_H

#include "nrf24_fragment.h"

typedef enum
{
    Nrf24Result_Ok = 0,
    Nrf24Result_Busy,
    Nrf24Result_Empty,
    Nrf24Result_Invalid,
    Nrf24Result_Offline,
    Nrf24Result_Timeout,
    Nrf24Result_Io,
    Nrf24Result_NotPresent
} Nrf24Result;

typedef struct
{
    uint32_t tx_ok;
    uint32_t rx_ok;
    uint32_t tx_timeout;
    uint32_t tx_dropped;
    uint32_t rx_dropped;
    uint32_t integrity_error;
    uint32_t rx_crc_error; /* Complete logical CRC failures, not width/SPI/TX faults. */
    uint32_t spi_error;
    uint32_t spi_timeout;
    uint32_t recovery_attempts;
    uint32_t last_tx_ms;
    uint32_t last_rx_ms;
    uint8_t state;
    uint8_t ready;
} Nrf24Stats;

Nrf24Result Nrf24_Init(uint8_t instance);
Nrf24Result Nrf24_Start(uint8_t instance);
Nrf24Result Nrf24_Stop(uint8_t instance);
void Nrf24_Process(uint8_t instance);
Nrf24Result Nrf24_Send(uint8_t instance, const uint8_t *data,
    uint16_t length, uint8_t control, uint32_t *transaction_id);
Nrf24Result Nrf24_ReceiptGet(uint8_t instance, uint32_t transaction_id,
    uint32_t *age_ms);
Nrf24Result Nrf24_Receive(uint8_t instance, uint8_t *data,
    uint16_t capacity, uint16_t *length);
Nrf24Result Nrf24_StatsGet(uint8_t instance, Nrf24Stats *stats);

#endif /* __NRF24_DEVICE_H */
