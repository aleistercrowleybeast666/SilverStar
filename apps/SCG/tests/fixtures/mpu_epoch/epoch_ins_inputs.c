#include "ins_task.c"
#include "system_inertial.h"
#include "system_imu_if.h"
#include <assert.h>
void Test_InsInputFeed(uint64_t timestamp_us, uint32_t sequence)
{
    (void)timestamp_us; (void)sequence;
    SystemImu_Process();
    InsImuSample sample;
    assert(SystemInertial_LatestGet(&sample) == SYSTEM_DEVICE_OK);
    InsTask_AlignmentProcess(&sample);
}

void Test_InsQueuedQualityCheck(uint8_t clipped)
{
    InsImuSample sample;
    SystemNavigationGroupHealth health;
    assert(ImuSampleBus_Pop(&sample) == IMU_SAMPLE_BUS_RESULT_OK);
    assert(((sample.quality_flags & SYSTEM_IMU_QUALITY_CLIPPED) != 0U) == clipped);
    InsTask_Propagate(&sample);
    assert(SystemNavigationHealth_GroupGet(0U, sample.sample_timestamp_us, &health) == SYSTEM_DEVICE_OK);
    assert(health.state == SYSTEM_NAVIGATION_INVALID);
    assert((health.reason & (0x80U | SYSTEM_IMU_QUALITY_CLIPPED)) ==
        (0x80U | SYSTEM_IMU_QUALITY_CLIPPED));
}
