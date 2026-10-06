#ifndef __MISSION_RADIO_PROFILE_H
#define __MISSION_RADIO_PROFILE_H

#include <stdint.h>

typedef enum
{
    MissionRadioProfileResult_Ok = 0,
    MissionRadioProfileResult_Invalid,
    MissionRadioProfileResult_UnsupportedSchema,
    MissionRadioProfileResult_UnsupportedBackend,
    MissionRadioProfileResult_UnsupportedVersion
} MissionRadioProfileResult;

typedef enum
{
    MissionRadioBackend_Sx128x = 0,
    MissionRadioBackend_Nrf24 = 1
} MissionRadioBackend;

typedef struct
{
    uint8_t bytes[15];
    uint8_t length;
    uint8_t schema;
    uint8_t version;
    MissionRadioBackend backend;
} MissionRadioProfile;

/* Read only the profile from an SSMS section0 payload already accepted by
 * PersistentStorage_ObjectRead's length/generation/CRC32 checks. This function
 * validates the typed radio contract, not the remaining snapshot sections. */
MissionRadioProfileResult MissionRadioProfile_Read(const uint8_t *snapshot,
    uint16_t length, MissionRadioProfile *profile);

#endif /* __MISSION_RADIO_PROFILE_H */
