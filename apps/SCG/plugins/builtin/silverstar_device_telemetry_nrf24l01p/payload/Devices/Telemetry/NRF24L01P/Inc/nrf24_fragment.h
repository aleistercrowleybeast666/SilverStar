#ifndef __NRF24_FRAGMENT_H
#define __NRF24_FRAGMENT_H

#include <stdint.h>

#define NRF24_PHYSICAL_MTU 32U
#define NRF24_LOGICAL_MTU 61U
#define NRF24_FRAGMENT_HEADER 10U
#define NRF24_FRAGMENT_DATA 22U
#define NRF24_FRAGMENT_COUNT_MAX 3U
#define NRF24_ASSEMBLY_TIMEOUT_MS 250U
#define NRF24_ASSEMBLY_TOTAL_TIMEOUT_MS (NRF24_ASSEMBLY_TIMEOUT_MS * NRF24_FRAGMENT_COUNT_MAX)

typedef enum
{
    Nrf24FragmentResult_Ok = 0,
    Nrf24FragmentResult_Pending,
    Nrf24FragmentResult_Duplicate,
    Nrf24FragmentResult_Invalid,
    Nrf24FragmentResult_Conflict,
    Nrf24FragmentResult_Integrity,
    Nrf24FragmentResult_Busy,
    Nrf24FragmentResult_Empty
} Nrf24FragmentResult;

/* One owner; callers supply static storage. Publication uses ready only. */
typedef struct
{
    uint8_t data[NRF24_LOGICAL_MTU];
    uint32_t started_ms;
    uint32_t last_activity_ms;
    uint32_t completed_ms;
    uint16_t session;
    uint16_t sequence;
    uint16_t crc;
    uint16_t last_session;
    uint16_t last_sequence;
    uint8_t length;
    uint8_t mask;
    uint8_t active;
    uint8_t ready;
    uint8_t last_valid;
} Nrf24FragmentRx;

uint16_t Nrf24Fragment_Crc(const uint8_t *data, uint8_t length);
Nrf24FragmentResult Nrf24Fragment_Encode(const uint8_t *data, uint8_t length,
    uint16_t session, uint16_t sequence, uint8_t index,
    uint8_t *packet, uint8_t *packet_length);
Nrf24FragmentResult Nrf24Fragment_Accept(Nrf24FragmentRx *rx,
    const uint8_t *packet, uint8_t length, uint32_t now_ms);
Nrf24FragmentResult Nrf24Fragment_Read(Nrf24FragmentRx *rx,
    uint8_t *data, uint16_t capacity, uint16_t *length);
void Nrf24Fragment_Expire(Nrf24FragmentRx *rx, uint32_t now_ms);

#endif /* __NRF24_FRAGMENT_H */
