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

static MissionRadioProfileResult MissionRadioProfile_TypedRead(const uint8_t *data,
    uint16_t length, MissionRadioProfile *candidate)
{
    static const uint8_t sx1278[16] = {1U, 0x40U, 0x0EU, 0xCFU, 0x19U,
        7U, 0x48U, 0xE8U, 1U, 0U, 5U, 16U, 0U, 61U, 0U, 17U};
    if (length < 4U) { return MissionRadioProfileResult_Invalid; }
    if ((data[0] != 1U) && (data[0] != 2U)) { return MissionRadioProfileResult_UnsupportedBackend; }
    if (data[1] != 1U) { return MissionRadioProfileResult_UnsupportedVersion; }
    candidate->length = (data[0] == 1U) ? 14U : 16U;
    candidate->version = 1U;
    candidate->backend = (data[0] == 1U) ? MissionRadioBackend_Nrf24 : MissionRadioBackend_Sx1278;
    if ((data[2] != candidate->length) || (data[3] != 0U) || (length < 4U + candidate->length))
    { return MissionRadioProfileResult_Invalid; }
    if (((data[0] == 1U) && (MissionRadioProfile_NrfValid(&data[4]) == 0U)) ||
        ((data[0] == 2U) && (memcmp(&data[4], sx1278, sizeof(sx1278)) != 0)))
    { return MissionRadioProfileResult_Invalid; }
    return MissionRadioProfileResult_Ok;
}

MissionRadioProfileResult MissionRadioProfile_Read(const uint8_t *snapshot,
    uint16_t length, MissionRadioProfile *profile)
{
    MissionRadioProfile candidate = {0};
    uint16_t offset = MISSION_RADIO_OFFSET;
    uint8_t radio_schema;
    if ((snapshot == NULL) || (profile == NULL) || (length < 8U))
    { return MissionRadioProfileResult_Invalid; }
    if ((memcmp(snapshot, "SSMS", 4U) != 0) || (snapshot[5] != 0U) ||
        (snapshot[6] != 6U) || (snapshot[7] != 0U))
    { return MissionRadioProfileResult_Invalid; }
    candidate.schema = snapshot[4];
    radio_schema = snapshot[4];
    if (radio_schema == 4U)
    {
        if (length <= offset) { return MissionRadioProfileResult_Invalid; }
        radio_schema = snapshot[offset++];
    }
    if (radio_schema == 2U)
    {
        candidate.backend = MissionRadioBackend_Sx128x; candidate.length = 15U;
    }
    else if (radio_schema == 3U)
    {
        MissionRadioProfileResult result;
        if (length < offset) { return MissionRadioProfileResult_Invalid; }
        result = MissionRadioProfile_TypedRead(&snapshot[offset], (uint16_t)(length - offset), &candidate);
        if (result != MissionRadioProfileResult_Ok) { return result; }
        offset += 4U;
    }
    else { return MissionRadioProfileResult_UnsupportedSchema; }
    if (length < offset + candidate.length) { return MissionRadioProfileResult_Invalid; }
    (void)memcpy(candidate.bytes, &snapshot[offset], candidate.length);
    *profile = candidate; /* Publish once, only after complete validation. */
    return MissionRadioProfileResult_Ok;
}
