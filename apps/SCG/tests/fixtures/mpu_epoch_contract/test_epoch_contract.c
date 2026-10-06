/* Host-only white-box state seeds. The exact owning provider is compiled;
 * no state accessor, callback or recovery interception enters firmware. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "system_imu_epoch.c"

static unsigned s_lock_depth;
PlatformCriticalState PlatformCritical_Enter(void) { return s_lock_depth++; }
void PlatformCritical_Exit(PlatformCriticalState state)
{ assert(s_lock_depth == state + 1U); s_lock_depth = state; }

static SystemImuEpochToken Test_Qualify(uint32_t epoch)
{
    uint32_t revision;
    SystemImuEpochToken token;
    SystemImuEpoch_Init();
    SystemImuEpoch_SamplePublish(0U, epoch, 1U, 1U);
    assert(SystemImuEpoch_CalibrationBegin(7U, 0U, &revision) == SYSTEM_DEVICE_OK);
    assert(SystemImuEpoch_CalibrationCommit(revision, 7U) != 0U);
    assert(SystemImuEpoch_AlignmentBegin(9U, &token) == SYSTEM_DEVICE_OK);
    assert(SystemImuEpoch_AlignmentCommit(&token, 1U) != 0U);
    assert(SystemImuEpoch_OriginsCommit(&token) != 0U);
    assert(SystemImuEpoch_StartIsCurrent(&token) != 0U);
    return token;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    unsigned which = (unsigned)strtoul(argv[1], NULL, 10);
    SystemImuEpochToken token = Test_Qualify(1U);
    if (which == 1U)
    {
        assert(SystemImuEpoch_SampleIsCurrent(1U, 1U) == 0U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 2U) == 0U);
        for (unsigned field = 0U; field < 5U; field++)
        {
            token = Test_Qualify(1U);
            if (field == 0U) { token.source_id++; }
            if (field == 1U) { token.epoch++; }
            if (field == 2U) { token.revision++; }
            if (field == 3U) { token.calibration_generation++; }
            if (field == 4U) { token.alignment_generation++; }
            assert(SystemImuEpoch_OriginsCommit(&token) == 0U);
            assert(SystemImuEpoch_StartIsCurrent(&token) == 0U);
            assert(SystemImuEpoch_AlignmentCommit(&token, 1U) == 0U);
            assert(SystemImuEpoch_IsQualified() == 0U);
        }
    }
    else if (which == 2U) { SystemImuEpoch_SamplePublish(1U, 2U, 1U, 1U); }
    else if (which == 3U) { SystemImuEpoch_SamplePublish(0U, 0U, 1U, 1U); }
    else if (which == 4U)
    {
        s_witness.revision = UINT32_MAX;
        SystemImuEpoch_Revoke();
        SystemImuEpoch_SamplePublish(0U, 2U, 1U, 1U);
        assert(SystemImuEpoch_PhysicalIsReady() == 0U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 2U) == 0U);
        assert(SystemImuEpoch_StartReserve(&token) == SYSTEM_DEVICE_NOT_READY);
    }
    else if (which == 5U)
    {
        token = Test_Qualify(UINT32_MAX);
        SystemImuEpoch_Revoke();
        SystemImuEpoch_SamplePublish(0U, 1U, 1U, 1U);
        assert(SystemImuEpoch_PhysicalIsReady() == 0U);
        assert(SystemImuEpoch_StartIsCurrent(&token) == 0U);
    }
    else if (which == 6U)
    {
        uint32_t revision;
        assert(SystemImuEpoch_CalibrationBegin(11U, 0U, &revision) == SYSTEM_DEVICE_OK);
        assert(SystemImuEpoch_CalibrationCommit(revision, 7U) == 0U);
        assert(SystemImuEpoch_CalibrationCommit(revision + 1U, 11U) == 0U);
        assert(SystemImuEpoch_CalibrationCommit(revision, 0U) == 0U);
        assert(SystemImuEpoch_AlignmentBegin(12U, &token) == SYSTEM_DEVICE_NOT_READY);
        assert(SystemImuEpoch_CalibrationCommit(revision, 11U) != 0U);
        assert(SystemImuEpoch_AlignmentBegin(12U, &token) == SYSTEM_DEVICE_OK);
    }
    else if (which == 7U)
    {
        uint32_t old_revision = token.revision;
        SystemImuEpoch_Revoke();
        assert(SystemImuEpoch_SampleIsCurrent(0U, 1U) == 0U);
        SystemImuEpoch_SamplePublish(0U, 1U, 1U, 1U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 1U) == 0U);
        SystemImuEpoch_SamplePublish(0U, 2U, 1U, 1U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 2U) != 0U);
        assert(SystemImuEpoch_CalibrationCommit(old_revision, 7U) == 0U);
        assert(SystemImuEpoch_CalibrationCommit(s_witness.revision, 0U) == 0U);
        assert(SystemImuEpoch_OriginsCommit(&token) == 0U);
        assert(SystemImuEpoch_StartIsCurrent(&token) == 0U);
    }
    else if (which == 8U)
    {
        SystemImuEpoch_SamplePublish(0U, 1U, 1U, 0U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 1U) != 0U);
        assert(SystemImuEpoch_PhysicalIsReady() == 0U);
        assert(SystemImuEpoch_StartIsCurrent(&token) == 0U);
        SystemImuEpoch_SamplePublish(0U, 1U, 1U, 1U);
        assert(SystemImuEpoch_StartIsCurrent(&token) != 0U);
    }
    else if (which == 9U)
    {
        uint32_t revision;
        SystemImuEpoch_Revoke();
        SystemImuEpoch_SamplePublish(0U, 2U, 1U, 1U);
        assert(SystemImuEpoch_CalibrationIsReady(7U, 1U) == 0U);
        assert(SystemImuEpoch_CalibrationBegin(8U, 1U, &revision) == SYSTEM_DEVICE_NOT_READY);
        assert(SystemImuEpoch_CalibrationIsReady(7U, 2U) == 0U);
    }
    else if (which == 10U) { s_witness.revision = 0U; (void)SystemImuEpoch_PhysicalIsReady(); }
    else if (which == 11U) { SystemImuEpoch_SamplePublish(0U, 2U, 1U, 2U); }
    else if (which == 12U)
    {
        SystemImuEpoch_SamplePublish(0U, 1U, 0U, 0U);
        assert(SystemImuEpoch_SampleIsCurrent(0U, 1U) == 0U);
        assert(SystemImuEpoch_StartIsCurrent(&token) == 0U);
    }
    else { assert(!"unknown case"); }
    assert(s_lock_depth == 0U);
    printf("epoch contract case=%u PASS\n", which);
    return 0;
}
