#include "mission_radio_profile.h"

#include <stddef.h>
#include <string.h>

#define MISSION_RADIO_OFFSET 66U

static uint8_t MissionRadioProfile_NrfValid(const uint8_t *data)
{
    uint8_t index;
    uint8_t nonzero = 0U;
    uint8_t not_ff = 0U;
    for (index = 3U; index < 8U; index++)
    { nonzero |= data[index]; not_ff |= (uint8_t)(data[index] ^ 0xFFU); }
    return (uint8_t)((data[0] <= 125U) && (data[1] <= 2U) &&
        ((data[2] == 0U) || (data[2] == 250U) || (data[2] == 244U) || (data[2] == 238U)) &&
        (nonzero != 0U) && (not_ff != 0U) && (data[8] >= 1U) && (data[8] <= 15U) &&
        (data[9] <= 15U) && (data[10] == 2U) && (data[11] == 32U) &&
        (data[12] >= 50U) && (data[12] <= 61U) && (data[13] == 1U));
}

MissionRadioProfileResult MissionRadioProfile_Read(const uint8_t *snapshot,
    uint16_t length, MissionRadioProfile *profile)
{
    MissionRadioProfile candidate = {0};
    uint16_t offset = MISSION_RADIO_OFFSET;
    if ((snapshot == NULL) || (profile == NULL) || (length < 8U))
    { return MissionRadioProfileResult_Invalid; }
    if ((memcmp(snapshot, "SSMS", 4U) != 0) || (snapshot[5] != 0U) ||
        (snapshot[6] != 6U) || (snapshot[7] != 0U))
    { return MissionRadioProfileResult_Invalid; }
    candidate.schema = snapshot[4];
    if (snapshot[4] == 2U)
    {
        candidate.backend = MissionRadioBackend_Sx128x; candidate.length = 15U;
    }
    else if (snapshot[4] == 3U)
    {
        if (length < MISSION_RADIO_OFFSET + 4U) { return MissionRadioProfileResult_Invalid; }
        if (snapshot[offset] != 1U) { return MissionRadioProfileResult_UnsupportedBackend; }
        if (snapshot[offset + 1U] != 1U) { return MissionRadioProfileResult_UnsupportedVersion; }
        if ((snapshot[offset + 2U] != 14U) || (snapshot[offset + 3U] != 0U) ||
            (length < MISSION_RADIO_OFFSET + 18U)) { return MissionRadioProfileResult_Invalid; }
        offset += 4U; candidate.backend = MissionRadioBackend_Nrf24;
        candidate.version = 1U; candidate.length = 14U;
        if (MissionRadioProfile_NrfValid(&snapshot[offset]) == 0U)
        { return MissionRadioProfileResult_Invalid; }
    }
    else { return MissionRadioProfileResult_UnsupportedSchema; }
    if (length < offset + candidate.length) { return MissionRadioProfileResult_Invalid; }
    (void)memcpy(candidate.bytes, &snapshot[offset], candidate.length);
    *profile = candidate; /* Publish once, only after complete validation. */
    return MissionRadioProfileResult_Ok;
}
