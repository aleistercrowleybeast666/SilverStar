#include "nrf24_fragment.h"

#include <stddef.h>
#include <string.h>
#include "silverstar_assert.h"

static uint16_t Nrf24Fragment_U16(const uint8_t *data)
{
    return (uint16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8U));
}

uint16_t Nrf24Fragment_Crc(const uint8_t *data, uint8_t length)
{
    uint16_t crc = 0xFFFFU;
    uint8_t i;
    uint8_t bit;
    if ((data == NULL) || (length > NRF24_LOGICAL_MTU)) { return 0U; }
    for (i = 0U; i < NRF24_LOGICAL_MTU; i++)
    {
        if (i >= length) { break; }
        crc ^= (uint16_t)((uint16_t)data[i] << 8U);
        for (bit = 0U; bit < 8U; bit++)
        {
            crc = ((crc & 0x8000U) != 0U) ?
                (uint16_t)((crc << 1U) ^ 0x1021U) : (uint16_t)(crc << 1U);
        }
    }
    return crc;
}

Nrf24FragmentResult Nrf24Fragment_Encode(const uint8_t *data, uint8_t length,
    uint16_t session, uint16_t sequence, uint8_t index,
    uint8_t *packet, uint8_t *packet_length)
{
    uint8_t offset = (uint8_t)(index * NRF24_FRAGMENT_DATA);
    uint8_t chunk;
    uint16_t crc;
    if ((data == NULL) || (packet == NULL) || (packet_length == NULL) ||
        (length == 0U) || (length > NRF24_LOGICAL_MTU) ||
        (index >= NRF24_FRAGMENT_COUNT_MAX) || (offset >= length))
    { return Nrf24FragmentResult_Invalid; }
    chunk = (uint8_t)(length - offset);
    if (chunk > NRF24_FRAGMENT_DATA) { chunk = NRF24_FRAGMENT_DATA; }
    crc = Nrf24Fragment_Crc(data, length);
    packet[0] = 0xD6U; packet[1] = 1U;
    packet[2] = (uint8_t)session; packet[3] = (uint8_t)(session >> 8U);
    packet[4] = (uint8_t)sequence; packet[5] = (uint8_t)(sequence >> 8U);
    packet[6] = length; packet[7] = index;
    packet[8] = (uint8_t)crc; packet[9] = (uint8_t)(crc >> 8U);
    (void)memcpy(&packet[NRF24_FRAGMENT_HEADER], &data[offset], chunk);
    *packet_length = (uint8_t)(NRF24_FRAGMENT_HEADER + chunk);
    return Nrf24FragmentResult_Ok;
}

void Nrf24Fragment_Expire(Nrf24FragmentRx *rx, uint32_t now_ms)
{
    if (rx == NULL) { return; }
    /* Volatile tags may repeat after peer reboot. Silence expires duplicate
     * history as well as assembly. This is not authenticated anti-replay. */
    if ((rx->last_valid != 0U) &&
        ((uint32_t)(now_ms - rx->completed_ms) >= NRF24_ASSEMBLY_TIMEOUT_MS))
    { rx->last_valid = 0U; }
    if ((rx->active != 0U) &&
        (((uint32_t)(now_ms - rx->started_ms) >= NRF24_ASSEMBLY_TOTAL_TIMEOUT_MS) ||
         ((uint32_t)(now_ms - rx->last_activity_ms) >= NRF24_ASSEMBLY_TIMEOUT_MS)))
    { rx->active = 0U; rx->mask = 0U; }
}

static Nrf24FragmentResult Nrf24Fragment_KeyAccept(Nrf24FragmentRx *rx,
    const uint8_t *packet, uint32_t now_ms)
{
    uint16_t session = Nrf24Fragment_U16(&packet[2]);
    uint16_t sequence = Nrf24Fragment_U16(&packet[4]);
    uint16_t crc = Nrf24Fragment_U16(&packet[8]);
    if ((rx->last_valid != 0U) && (session == rx->last_session) &&
        ((uint16_t)(sequence - rx->last_sequence) >= 0x8000U ||
         sequence == rx->last_sequence))
    { return Nrf24FragmentResult_Duplicate; }
    if ((rx->active != 0U) && (session == rx->session) &&
        (sequence == rx->sequence))
    {
        if ((rx->length != packet[6]) || (rx->crc != crc))
        { rx->active = 0U; rx->mask = 0U; return Nrf24FragmentResult_Conflict; }
        return Nrf24FragmentResult_Ok;
    }
    /* An in-progress different frame can be replaced only by its first fragment.
     * This bounds interleaving; an idle receiver accepts out-of-order starts. */
    if ((rx->active != 0U) && (packet[7] != 0U))
    { return Nrf24FragmentResult_Conflict; }
    rx->session = session; rx->sequence = sequence; rx->crc = crc;
    rx->length = packet[6]; rx->mask = 0U; rx->active = 1U;
    rx->started_ms = now_ms; rx->last_activity_ms = now_ms;
    return Nrf24FragmentResult_Ok;
}

Nrf24FragmentResult Nrf24Fragment_Accept(Nrf24FragmentRx *rx,
    const uint8_t *packet, uint8_t length, uint32_t now_ms)
{
    uint8_t offset;
    uint8_t chunk;
    uint8_t count;
    uint8_t bit;
    Nrf24FragmentResult result;
    if ((rx == NULL) || (packet == NULL) || (length <= NRF24_FRAGMENT_HEADER) ||
        (length > NRF24_PHYSICAL_MTU)) { return Nrf24FragmentResult_Invalid; }
    if ((packet[0] != 0xD6U) || (packet[1] != 1U) || (packet[6] == 0U) ||
        (packet[6] > NRF24_LOGICAL_MTU) || (packet[7] >= NRF24_FRAGMENT_COUNT_MAX))
    { return Nrf24FragmentResult_Invalid; }
    offset = (uint8_t)(packet[7] * NRF24_FRAGMENT_DATA);
    if (offset >= packet[6]) { return Nrf24FragmentResult_Invalid; }
    chunk = (uint8_t)(packet[6] - offset);
    if (chunk > NRF24_FRAGMENT_DATA) { chunk = NRF24_FRAGMENT_DATA; }
    if (length != NRF24_FRAGMENT_HEADER + chunk) { return Nrf24FragmentResult_Invalid; }
    SILVERSTAR_ASSERT((rx->active <= 1U) && (rx->ready <= 1U) &&
        (rx->mask < 8U), SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (rx->ready != 0U) { return Nrf24FragmentResult_Busy; }
    Nrf24Fragment_Expire(rx, now_ms);
    result = Nrf24Fragment_KeyAccept(rx, packet, now_ms);
    if (result != Nrf24FragmentResult_Ok) { return result; }
    bit = (uint8_t)(1U << packet[7]);
    if ((rx->mask & bit) != 0U)
    {
        if (memcmp(&rx->data[offset], &packet[NRF24_FRAGMENT_HEADER], chunk) == 0)
        { return Nrf24FragmentResult_Duplicate; }
        rx->active = 0U; rx->mask = 0U; return Nrf24FragmentResult_Conflict;
    }
    (void)memcpy(&rx->data[offset], &packet[NRF24_FRAGMENT_HEADER], chunk);
    rx->mask |= bit; rx->last_activity_ms = now_ms;
    count = (uint8_t)((rx->length + NRF24_FRAGMENT_DATA - 1U) / NRF24_FRAGMENT_DATA);
    if (rx->mask != (uint8_t)((1U << count) - 1U)) { return Nrf24FragmentResult_Pending; }
    rx->active = 0U;
    if (Nrf24Fragment_Crc(rx->data, rx->length) != rx->crc)
    { rx->mask = 0U; return Nrf24FragmentResult_Integrity; }
    rx->last_session = rx->session; rx->last_sequence = rx->sequence;
    rx->last_valid = 1U; rx->ready = 1U; rx->completed_ms = now_ms;
    return Nrf24FragmentResult_Ok;
}

Nrf24FragmentResult Nrf24Fragment_Read(Nrf24FragmentRx *rx,
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    if ((rx == NULL) || (data == NULL) || (length == NULL))
    { return Nrf24FragmentResult_Invalid; }
    *length = 0U;
    SILVERSTAR_ASSERT((rx->ready <= 1U) && (rx->active <= 1U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (rx->ready == 0U) { return Nrf24FragmentResult_Empty; }
    SILVERSTAR_ASSERT((rx->length > 0U) && (rx->length <= NRF24_LOGICAL_MTU),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (capacity < rx->length) { return Nrf24FragmentResult_Invalid; }
    (void)memcpy(data, rx->data, rx->length);
    *length = rx->length; rx->ready = 0U; rx->mask = 0U;
    return Nrf24FragmentResult_Ok;
}
