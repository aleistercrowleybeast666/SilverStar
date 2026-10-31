#include "ground_radio_tm.h"
#include "silverstar_assert.h"
#include <stddef.h>

#define GROUND_TM_RETIRED_BOUND 16U
static uint32_t s_tm_session;
static uint32_t s_tm_retired[GROUND_TM_RETIRED_BOUND];
static uint8_t s_tm_retired_next;
static uint64_t s_tm_phase_floor_us;
/* Until a current preflight CAP is received, a late joining GS is passive. */
static uint8_t s_tm_passive = 1U;

static uint64_t GroundRadio_TmUnsignedGet(const uint8_t *data, uint8_t width)
{
    uint64_t value = 0ULL;
    SILVERSTAR_ASSERT((data != NULL) && (width > 0U) && (width <= 8U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (uint8_t index = 0U; index < width; index++)
    { value |= (uint64_t)data[index] << (8U * index); }
    return value;
}

void GroundRadioTm_Observe(const uint8_t *data, uint8_t length)
{
    uint32_t session;
    uint64_t occurred_us = 0ULL;
    uint8_t type;
    if ((length < 8U) || (data[0] != 1U) || ((data[1] & 0x80U) != 0U)) { return; }
    session = (uint32_t)GroundRadio_TmUnsignedGet(&data[4], 4U);
    if (session == 0U) { return; }
    type = data[1];
    /* Transport policy only, not a second decoder. Exact qualifying message
     * lengths/fields are explicit; opaque raw forwarding remains unchanged. */
    if (!(((type == 0x12U) && (length == 24U) && (data[8] == 0U) &&
           (data[9] == 1U) && ((data[10] & 0xF8U) == 0U) &&
           ((data[11] & 0xF0U) == 0U) && (data[12] != 0U) &&
           (GroundRadio_TmUnsignedGet(&data[13], 2U) != 0U) && (data[15] == 1U)) ||
          ((type == 0x10U) && (length == 56U)) ||
          ((type == 0x40U) && (length == 16U) && (data[10] == 1U) && (data[11] == 0U)) ||
          ((type == 0x20U) && (length == 32U) &&
           (GroundRadio_TmUnsignedGet(&data[8], 4U) != 0U)))) { return; }
    if (session != s_tm_session)
    {
        for (uint8_t index = 0U; index < GROUND_TM_RETIRED_BOUND; index++)
        { if (s_tm_retired[index] == session) { return; } }
        s_tm_retired[s_tm_retired_next] = s_tm_session;
        s_tm_retired_next = (uint8_t)((s_tm_retired_next + 1U) % GROUND_TM_RETIRED_BOUND);
        s_tm_session = session; s_tm_passive = 1U; s_tm_phase_floor_us = 0ULL;
    }
    if (type == 0x12U)
    {
        if (GroundRadio_TmUnsignedGet(&data[16], 8U) > s_tm_phase_floor_us)
        { s_tm_passive = 0U; }
        return;
    }
    if (type == 0x20U)
    {
        uint16_t code = (uint16_t)GroundRadio_TmUnsignedGet(&data[20], 2U);
        if ((code != 3U) && (code != 4U) && (code != 5U) && (code != 6U) &&
            (code != 0x100U) && (code != 0x101U)) { return; }
        occurred_us = GroundRadio_TmUnsignedGet(&data[12], 8U);
    }
    else { occurred_us = GroundRadio_TmUnsignedGet(&data[(type == 0x40U) ? 12U : 8U], 4U) * 1000ULL; }
    if (occurred_us > s_tm_phase_floor_us) { s_tm_phase_floor_us = occurred_us; }
    s_tm_passive = 1U;
}

uint8_t GroundRadioTm_PassiveGet(void) { return s_tm_passive; }
