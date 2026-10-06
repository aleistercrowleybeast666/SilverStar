#include "system_imu_epoch_if.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "platform_critical.h"
#include "silverstar_assert.h"

#define IMU_EPOCH_KNOWN 1U
#define IMU_EPOCH_PHYSICAL 2U
#define IMU_EPOCH_RECOVERED 4U
#define IMU_EPOCH_EXHAUSTED 8U
#define IMU_EPOCH_CALIBRATED 16U
#define IMU_EPOCH_ALIGNED 32U
#define IMU_EPOCH_ORIGINS 64U
#define IMU_EPOCH_REVOKED 128U

static SystemImuEpochToken s_witness;
static uint8_t s_flags;

static uint8_t SystemImuEpoch_PhysicalCheck(void)
{
    SILVERSTAR_ASSERT((s_witness.revision != 0U) &&
        (((s_flags & IMU_EPOCH_PHYSICAL) == 0U) ||
         ((s_flags & (IMU_EPOCH_KNOWN | IMU_EPOCH_REVOKED)) == IMU_EPOCH_KNOWN)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(((s_flags & IMU_EPOCH_ALIGNED) == 0U) ||
        (((s_flags & IMU_EPOCH_CALIBRATED) != 0U) &&
         (s_witness.calibration_generation != 0U) &&
         (s_witness.alignment_generation != 0U)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    return (uint8_t)((s_flags & (IMU_EPOCH_KNOWN | IMU_EPOCH_PHYSICAL |
        IMU_EPOCH_EXHAUSTED | IMU_EPOCH_REVOKED)) == (IMU_EPOCH_KNOWN | IMU_EPOCH_PHYSICAL));
}

static uint8_t SystemImuEpoch_TokenCheck(const SystemImuEpochToken *token)
{
    return (uint8_t)((token != NULL) &&
        (SystemImuEpoch_PhysicalCheck() != 0U) &&
        (token->source_id == s_witness.source_id) &&
        (token->epoch == s_witness.epoch) &&
        (token->revision == s_witness.revision) &&
        (token->calibration_generation == s_witness.calibration_generation) &&
        (token->alignment_generation == s_witness.alignment_generation));
}

static void SystemImuEpoch_Advance(void)
{
    s_flags &= IMU_EPOCH_KNOWN | IMU_EPOCH_RECOVERED | IMU_EPOCH_EXHAUSTED;
    s_flags |= IMU_EPOCH_RECOVERED | IMU_EPOCH_REVOKED;
    s_witness.calibration_generation = 0U;
    s_witness.alignment_generation = 0U;
    if (s_witness.revision == UINT32_MAX)
    { s_flags |= IMU_EPOCH_EXHAUSTED; }
    else { s_witness.revision++; }
}

void SystemImuEpoch_Init(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    (void)memset(&s_witness, 0, sizeof(s_witness));
    s_witness.revision = 1U;
    s_flags = IMU_EPOCH_REVOKED;
    PlatformCritical_Exit(lock);
}

void SystemImuEpoch_Revoke(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    SystemImuEpoch_Advance();
    PlatformCritical_Exit(lock);
}

void SystemImuEpoch_SamplePublish(uint32_t source_id, uint32_t epoch,
    uint8_t configured, uint8_t usable)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t new_epoch = (uint8_t)((s_flags & IMU_EPOCH_KNOWN) == 0U);
    SILVERSTAR_ASSERT(source_id == 0U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((epoch != 0U) && (configured <= 1U) && (usable <= configured),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (configured == 0U)
    {
        SystemImuEpoch_Advance();
        PlatformCritical_Exit(lock);
        return;
    }
    if ((s_flags & IMU_EPOCH_KNOWN) != 0U)
    {
        SILVERSTAR_ASSERT(source_id == s_witness.source_id,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        if (epoch != s_witness.epoch)
        {
            new_epoch = 1U;
            /* A driver configuration ID must never wrap or move backwards. */
            if (epoch <= s_witness.epoch) { s_flags |= IMU_EPOCH_EXHAUSTED; }
            SystemImuEpoch_Advance();
        }
    }
    s_witness.source_id = source_id;
    s_witness.epoch = epoch;
    s_flags |= IMU_EPOCH_KNOWN;
    if ((new_epoch != 0U) && (configured != 0U))
    { s_flags &= (uint8_t)~IMU_EPOCH_REVOKED; }
    if ((usable != 0U) && ((s_flags & IMU_EPOCH_REVOKED) == 0U))
    { s_flags |= IMU_EPOCH_PHYSICAL; }
    else { s_flags &= (uint8_t)~IMU_EPOCH_PHYSICAL; }
    PlatformCritical_Exit(lock);
}

uint8_t SystemImuEpoch_SampleIsCurrent(uint32_t source_id, uint32_t epoch)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    /* Same-epoch clipped/time-quality evidence must reach INS unchanged.
     * PhysicalCheck is reserved for qualification, not queue identity. */
    uint8_t current = (uint8_t)(((s_flags & (IMU_EPOCH_KNOWN |
        IMU_EPOCH_REVOKED | IMU_EPOCH_EXHAUSTED)) == IMU_EPOCH_KNOWN) &&
        (source_id == s_witness.source_id) && (epoch == s_witness.epoch));
    PlatformCritical_Exit(lock);
    return current;
}

uint8_t SystemImuEpoch_PhysicalIsReady(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = SystemImuEpoch_PhysicalCheck();
    PlatformCritical_Exit(lock);
    return ready;
}

uint8_t SystemImuEpoch_RevisionIsCurrent(uint32_t revision)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t current = (uint8_t)((SystemImuEpoch_PhysicalCheck() != 0U) &&
        (revision == s_witness.revision));
    PlatformCritical_Exit(lock);
    return current;
}

uint8_t SystemImuEpoch_IsQualified(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)((SystemImuEpoch_PhysicalCheck() != 0U) &&
        ((s_flags & (IMU_EPOCH_CALIBRATED | IMU_EPOCH_ALIGNED)) ==
         (IMU_EPOCH_CALIBRATED | IMU_EPOCH_ALIGNED)));
    PlatformCritical_Exit(lock);
    return ready;
}

void SystemImuEpoch_CalibrationInvalidate(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_flags &= (uint8_t)~(IMU_EPOCH_CALIBRATED | IMU_EPOCH_ALIGNED | IMU_EPOCH_ORIGINS);
    s_witness.calibration_generation = 0U;
    s_witness.alignment_generation = 0U;
    PlatformCritical_Exit(lock);
}

uint8_t SystemImuEpoch_RecoveryIsQualified(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)(((s_flags & IMU_EPOCH_RECOVERED) != 0U) &&
        (SystemImuEpoch_IsQualified() != 0U));
    PlatformCritical_Exit(lock);
    return ready;
}

void SystemImuEpoch_AlignmentInvalidate(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_flags &= (uint8_t)~(IMU_EPOCH_ALIGNED | IMU_EPOCH_ORIGINS);
    s_witness.alignment_generation = 0U;
    PlatformCritical_Exit(lock);
}

SystemDeviceResult SystemImuEpoch_CalibrationBegin(uint32_t generation,
    uint8_t identity, uint32_t *revision)
{
    PlatformCriticalState lock;
    if ((revision == NULL) || (generation == 0U) || (identity > 1U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if ((SystemImuEpoch_PhysicalCheck() == 0U) ||
        ((identity != 0U) && ((s_flags & IMU_EPOCH_RECOVERED) != 0U)))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_NOT_READY; }
    s_flags &= (uint8_t)~(IMU_EPOCH_CALIBRATED | IMU_EPOCH_ALIGNED | IMU_EPOCH_ORIGINS);
    s_witness.calibration_generation = generation;
    *revision = s_witness.revision;
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemImuEpoch_CalibrationCommit(uint32_t revision, uint32_t generation)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)((SystemImuEpoch_PhysicalCheck() != 0U) &&
        (generation != 0U) &&
        (revision == s_witness.revision) &&
        (generation == s_witness.calibration_generation));
    if (ready != 0U) { s_flags |= IMU_EPOCH_CALIBRATED; }
    PlatformCritical_Exit(lock);
    return ready;
}

uint8_t SystemImuEpoch_CalibrationIsReady(uint32_t generation, uint8_t identity)
{
    if (identity > 1U) { return 0U; }
    PlatformCriticalState lock = PlatformCritical_Enter();
    /* Initial identity is the existing CAL_NONE contract. It may bind only
     * before any physical recovery, never a replacement for fresh calibration. */
    if ((identity != 0U) && ((s_flags & IMU_EPOCH_RECOVERED) == 0U) &&
        (SystemImuEpoch_PhysicalCheck() != 0U) && (generation != 0U))
    {
        s_witness.calibration_generation = generation;
        s_flags |= IMU_EPOCH_CALIBRATED;
    }
    uint8_t ready = (uint8_t)((SystemImuEpoch_PhysicalCheck() != 0U) &&
        ((s_flags & IMU_EPOCH_CALIBRATED) != 0U) &&
        (generation == s_witness.calibration_generation));
    PlatformCritical_Exit(lock);
    return ready;
}

SystemDeviceResult SystemImuEpoch_AlignmentBegin(uint32_t generation,
    SystemImuEpochToken *token)
{
    PlatformCriticalState lock;
    if ((token == NULL) || (generation == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if ((SystemImuEpoch_PhysicalCheck() == 0U) ||
        ((s_flags & IMU_EPOCH_CALIBRATED) == 0U))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_NOT_READY; }
    s_flags &= (uint8_t)~(IMU_EPOCH_ALIGNED | IMU_EPOCH_ORIGINS);
    s_witness.alignment_generation = generation;
    *token = s_witness;
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemImuEpoch_AlignmentCommit(const SystemImuEpochToken *token,
    uint8_t ready)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t current = (uint8_t)((SystemImuEpoch_TokenCheck(token) != 0U) &&
        ((s_flags & IMU_EPOCH_CALIBRATED) != 0U));
    if ((current != 0U) && (ready != 0U)) { s_flags |= IMU_EPOCH_ALIGNED; }
    else { s_flags &= (uint8_t)~(IMU_EPOCH_ALIGNED | IMU_EPOCH_ORIGINS); }
    PlatformCritical_Exit(lock);
    return (uint8_t)((current != 0U) && (ready != 0U));
}

uint8_t SystemImuEpoch_AlignmentIsReady(uint32_t generation)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)((SystemImuEpoch_IsQualified() != 0U) &&
        (generation == s_witness.alignment_generation));
    PlatformCritical_Exit(lock);
    return ready;
}

uint8_t SystemImuEpoch_OriginsCommit(const SystemImuEpochToken *token)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)((SystemImuEpoch_TokenCheck(token) != 0U) &&
        (SystemImuEpoch_IsQualified() != 0U));
    if (ready != 0U) { s_flags |= IMU_EPOCH_ORIGINS; }
    PlatformCritical_Exit(lock);
    return ready;
}

SystemDeviceResult SystemImuEpoch_StartReserve(SystemImuEpochToken *token)
{
    PlatformCriticalState lock;
    if (token == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    if (SystemImuEpoch_IsQualified() == 0U)
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_NOT_READY; }
    *token = s_witness;
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemImuEpoch_StartIsCurrent(const SystemImuEpochToken *token)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t ready = (uint8_t)((SystemImuEpoch_TokenCheck(token) != 0U) &&
        (SystemImuEpoch_IsQualified() != 0U) &&
        ((s_flags & IMU_EPOCH_ORIGINS) != 0U));
    PlatformCritical_Exit(lock);
    return ready;
}
