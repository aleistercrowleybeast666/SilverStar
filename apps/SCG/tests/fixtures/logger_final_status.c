#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "persistent_storage.h"
#include "silverstar_assert.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_lifecycle.h"
#include "system_mission_snapshot_if.h"

/* SX snapshots retain schema2; the approved NRF typed profile uses schema3
 * for every SSMS section. Each build checks one exact expected version. */
#ifndef TEST_MISSION_SCHEMA
#define TEST_MISSION_SCHEMA 2U
#endif

static unsigned s_case;
static uint32_t s_writes;
static uint8_t s_written[512];
static uint16_t s_length;

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    if (condition == 0U) { exit(86); }
}
void SilverStarAssert_ObjectCheck(const volatile void *object,
    uint32_t alignment, SilverStarAssertModuleId module,
    const char *file, uint32_t line)
{
    (void)alignment; (void)module; (void)file; (void)line;
    if (object == NULL) { exit(86); }
}

SystemDeviceResult SystemStorage_MissionIdGet(uint32_t *id)
{
    *id = 0x12345678U;
    return (s_case == 1U) ? SYSTEM_DEVICE_NOT_READY : SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemFlightRecovery_StatusGet(SystemFlightRecoveryStatus *s)
{
    if (s_case == 2U) { return SYSTEM_DEVICE_NOT_READY; }
    s->landing_detected = 1U;
    s->deploy_triggered = 1U;
    s->deploy_completed = (uint8_t)(s_case != 3U);
    s->deploy_action_result = SYSTEM_DEVICE_IO_ERROR;
    s->landing_transition_result = SYSTEM_DEVICE_BUSY;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemFlightRecovery_FinalStatusGet(SystemFlightRecoveryFinalStatus *s)
{
    if (s_case == 2U) { return SYSTEM_DEVICE_NOT_READY; }
    s->landing_detected = 1U;
    s->deploy_triggered = 1U;
    s->deploy_completed = (uint8_t)(s_case != 3U);
    s->deploy_action_result = SYSTEM_DEVICE_IO_ERROR;
    s->landing_transition_result = SYSTEM_DEVICE_BUSY;
    return SYSTEM_DEVICE_OK;
}
void SystemHealth_GetSnapshot(SystemHealthSnapshot *s)
{
    s->start_blocking_mask = 0xABCDEF12U;
    s->warning_mask = 0xFEDCBA98U;
    s->sequence = 77U;
}
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *s)
{
    if (s_case == 4U) { return SYSTEM_DEVICE_IO_ERROR; }
    s->healthy = (uint8_t)(s_case != 5U);
    s->mounted = (uint8_t)(s_case != 6U);
    return SYSTEM_DEVICE_OK;
}
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_LANDED; }
PersistentStorageResult PersistentStorage_ObjectWriteAtomic(
    PersistentStorageObjectKind kind, uint8_t instance, const uint8_t *data,
    uint16_t length, uint32_t *generation)
{
    if (kind != PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT || instance != 7U ||
        length != 48U) { exit(87); }
    s_writes++;
    s_length = length;
    (void)memcpy(s_written, data, length);
    *generation = 99U;
    return (s_case == 7U) ? PERSISTENT_STORAGE_IO_ERROR : PERSISTENT_STORAGE_OK;
}

static uint32_t Read32(unsigned at)
{
    return (uint32_t)s_written[at] | ((uint32_t)s_written[at+1] << 8U) |
        ((uint32_t)s_written[at+2] << 16U) | ((uint32_t)s_written[at+3] << 24U);
}
int main(int argc, char **argv)
{
    SystemMissionSnapshotResult result;
    unsigned i;
    const uint8_t expected_header[8] =
        {'S', 'S', 'M', 'S', TEST_MISSION_SCHEMA, 7U, 1U, 0U};
    if (argc != 2) { return 2; }
    s_case = (unsigned)strtoul(argv[1], NULL, 10);
    result = SystemMissionSnapshot_FinalStatusWrite(0x123456789ABCDEF0ULL,
        (uint8_t)(s_case == 8U));
    if (s_case == 1U)
    { return (result == SystemMissionSnapshotResult_NotReady && s_writes == 0U) ? 0 : 3; }
    if (result != ((s_case == 7U) ? SystemMissionSnapshotResult_StorageError :
        SystemMissionSnapshotResult_Ok) || s_writes != 1U || s_length != 48U)
    { return 4; }
    if (memcmp(s_written, expected_header, sizeof(expected_header)) != 0 ||
        Read32(8) != 0x12345678U || Read32(12) != 0x9ABCDEF0U ||
        Read32(16) != 0x12345678U || s_written[20] != SYSTEM_STATE_LANDED ||
        s_written[21] != (s_case != 2U) ||
        s_written[22] != (s_case != 2U) || s_written[23] != (s_case != 2U) ||
        s_written[24] != (s_case != 2U && s_case != 3U) ||
        s_written[25] != (s_case == 8U) || s_written[26] != (s_case != 4U) ||
        s_written[27] != (s_case >= 4U && s_case <= 6U) ||
        Read32(28) != 0xABCDEF12U || Read32(32) != 0xFEDCBA98U ||
        Read32(36) != 77U ||
        Read32(40) != ((s_case == 2U) ? 0U : SYSTEM_DEVICE_IO_ERROR) ||
        Read32(44) != ((s_case == 2U) ? 0U : SYSTEM_DEVICE_BUSY)) { return 5; }
    for (i=0U; i<s_length; i++) { printf("%02x", s_written[i]); }
    printf("\n");
    return 0;
}
