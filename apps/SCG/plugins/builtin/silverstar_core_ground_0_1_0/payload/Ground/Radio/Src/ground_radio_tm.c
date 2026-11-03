#include "ground_radio_tm.h"
#include "silverstar_assert.h"
#include <stddef.h>

#define GROUND_TM_RETIRED_BOUND 16U
static uint32_t s_tm_session;
static uint32_t s_tm_retired[GROUND_TM_RETIRED_BOUND];
static uint8_t s_tm_retired_next;
typedef enum
{
    GroundTmDirection_AwaitingCapability = 0,
    GroundTmDirection_Preflight,
    GroundTmDirection_MissionReceiveOnly
} GroundTmDirection;

static GroundTmDirection s_tm_direction = GroundTmDirection_AwaitingCapability;

static uint64_t GroundRadio_TmUnsignedGet(const uint8_t *data, uint8_t width)
{
    uint64_t value = 0ULL;
    SILVERSTAR_ASSERT((data != NULL) && (width > 0U) && (width <= 8U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (uint8_t index = 0U; index < width; index++)
    { value |= (uint64_t)data[index] << (8U * index); }
    return value;
}

/* Only a valid frame may retire a previous boot. All checks below operate
 * on wire bytes, including signed E7 coordinates and IEEE-754 exponent bits. */
static uint8_t GroundRadio_TmCoordinateValid(uint32_t bits, uint32_t limit)
{
    return (uint8_t)((bits <= limit) || (bits >= (UINT32_MAX - limit + 1U)));
}

static uint8_t GroundRadio_TmPositionValid(const uint8_t *data)
{
    const uint32_t unavailable = 0x80000000U;
    uint8_t flags = data[26];
    uint32_t lat = (uint32_t)GroundRadio_TmUnsignedGet(&data[8], 4U);
    uint32_t lon = (uint32_t)GroundRadio_TmUnsignedGet(&data[12], 4U);
    uint32_t height = (uint32_t)GroundRadio_TmUnsignedGet(&data[16], 4U);
    if (((flags & 0xC0U) != 0U) ||
        (((flags & 2U) != 0U) != (height != unavailable))) { return 0U; }
    if ((flags & 1U) == 0U)
    { return (uint8_t)((lat == unavailable) && (lon == unavailable) && ((flags & 0x14U) == 0U)); }
    return (uint8_t)(((flags & 0x14U) != 0x14U) &&
        (GroundRadio_TmCoordinateValid(lat, 900000000U) != 0U) &&
        (GroundRadio_TmCoordinateValid(lon, 1800000000U) != 0U));
}

static uint8_t GroundRadio_TmHealthValid(const uint8_t *data)
{
    uint16_t known = (uint16_t)GroundRadio_TmUnsignedGet(&data[12], 2U);
    uint16_t fault = (uint16_t)GroundRadio_TmUnsignedGet(&data[14], 2U);
    return (uint8_t)(((known & 0xF800U) == 0U) && ((fault & ~known) == 0U) &&
        ((GroundRadio_TmUnsignedGet(&data[8], 2U) != UINT16_MAX) ||
         (GroundRadio_TmUnsignedGet(&data[10], 2U) == UINT16_MAX)));
}

static uint8_t GroundRadio_TmFlightDataValid(const uint8_t *data)
{
    for (uint8_t offset = 32U; offset < 56U; offset += 4U)
    {
        uint32_t bits = (uint32_t)GroundRadio_TmUnsignedGet(&data[offset], 4U);
        if ((bits & 0x7F800000U) == 0x7F800000U) { return 0U; }
    }
    return 1U;
}

static uint8_t GroundRadio_TmNeutralGet(const uint8_t *data, uint8_t type, uint8_t length)
{
    if ((type == 0x18U) && (length == 28U)) { return GroundRadio_TmPositionValid(data); }
    if ((type == 0x19U) && (length == 16U)) { return GroundRadio_TmHealthValid(data); }
    if ((type == 0x13U) && (length == 15U))
    { return (uint8_t)(((data[12] & 0xF0U) == 0U) && ((data[13] & 0x80U) == 0U)); }
    return (uint8_t)(((type == 0x11U) && (length == 32U)) ||
                     ((type >= 0x14U) && (type <= 0x17U) && (length == 15U)));
}

void GroundRadioTm_Observe(const uint8_t *data, uint8_t length)
{
    uint32_t session;
    uint8_t type;
    uint8_t capability;
    uint8_t flight_data;
    uint8_t ack;
    uint8_t event;
    if ((data == NULL) || (length < 8U) || (data[0] != 1U) ||
        ((data[1] & 0x80U) != 0U)) { return; }
    session = (uint32_t)GroundRadio_TmUnsignedGet(&data[4], 4U);
    if (session == 0U) { return; }
    type = data[1];
    capability = (uint8_t)((type == 0x12U) && (length == 24U) && (data[8] == 0U) &&
        (data[9] == 1U) && ((data[10] & 0xF8U) == 0U) &&
        ((data[11] & 0xF0U) == 0U) && (data[12] != 0U) &&
        (GroundRadio_TmUnsignedGet(&data[13], 2U) != 0U) && (data[15] == 1U) &&
        (GroundRadio_TmUnsignedGet(&data[16], 8U) != 0ULL));
    flight_data = (uint8_t)((type == 0x10U) && (length == 56U) &&
        (GroundRadio_TmFlightDataValid(data) != 0U));
    ack = (uint8_t)((type == 0x40U) && (length == 16U) && (data[11] <= 0x16U));
    event = (uint8_t)((type == 0x20U) && (length == 32U) &&
        (GroundRadio_TmUnsignedGet(&data[8], 4U) != 0U) &&
        (GroundRadio_TmUnsignedGet(&data[20], 2U) != 0U));
    if ((capability == 0U) && (flight_data == 0U) && (ack == 0U) &&
        (event == 0U) && (GroundRadio_TmNeutralGet(data, type, length) == 0U)) { return; }
    if (session != s_tm_session)
    {
        for (uint8_t index = 0U; index < GROUND_TM_RETIRED_BOUND; index++)
        { if (s_tm_retired[index] == session) { return; } }
        s_tm_retired[s_tm_retired_next] = s_tm_session;
        s_tm_retired_next = (uint8_t)((s_tm_retired_next + 1U) % GROUND_TM_RETIRED_BOUND);
        s_tm_session = session;
        s_tm_direction = GroundTmDirection_AwaitingCapability;
    }
    if ((capability != 0U) && (s_tm_direction == GroundTmDirection_AwaitingCapability))
    { s_tm_direction = GroundTmDirection_Preflight; }
    else if ((flight_data != 0U) || ((ack != 0U) && (data[10] == 1U) && (data[11] == 0U)))
    { s_tm_direction = GroundTmDirection_MissionReceiveOnly; }
    else if (event != 0U)
    {
        uint16_t code = (uint16_t)GroundRadio_TmUnsignedGet(&data[20], 2U);
        /* START_ACCEPTED through LANDED are mission facts. A stage ENTER or
         * EXIT can be delivered during preflight or retried after START. */
        if ((code >= 3U) && (code <= 6U))
        { s_tm_direction = GroundTmDirection_MissionReceiveOnly; }
    }
}

uint8_t GroundRadioTm_PassiveGet(void)
{
    return (uint8_t)(s_tm_direction != GroundTmDirection_Preflight);
}
