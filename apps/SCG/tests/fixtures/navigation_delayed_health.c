/* Host-only actual-source boundary and corruption probes. No target recovery. */
#include "platform_critical.h"
#include <stdint.h>
#include <string.h>
static uint32_t s_test_depth;
static uint32_t s_test_lock_errors;

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_test_depth;
    if (s_test_depth != 0U) { s_test_lock_errors++; }
    s_test_depth++;
    return previous;
}

void PlatformCritical_Exit(PlatformCriticalState previous)
{
    if (s_test_depth != previous + 1U) { s_test_lock_errors++; }
    s_test_depth = previous;
}

#include NAV_HEALTH_TEST_SOURCE

uint32_t Test_HealthGroupSize(void);
uint32_t Test_HealthLockErrors(void);
void Test_HealthCorrupt(uint32_t kind);
uint32_t Test_HealthCapture(uint8_t *output, uint32_t capacity);

uint32_t Test_HealthGroupSize(void) { return (uint32_t)sizeof(SystemNavigationGroupHealth); }
uint32_t Test_HealthLockErrors(void) { return s_test_lock_errors + s_test_depth; }

void Test_HealthCorrupt(uint32_t kind)
{
    if (kind == 1U) { s_delayed_used[0] = 2U; }
    if (kind == 2U) { s_delayed_receipts[0][0].seen = 2U; }
    if (kind == 3U) { s_groups[0].state = 255U; }
    if (kind == 4U) { s_groups[0].source = 255U; }
    if (kind == 5U) { s_delayed_fusions[0][0].seen = 2U; }
}

uint32_t Test_HealthCapture(uint8_t *output, uint32_t capacity)
{
    const uint32_t size = (uint32_t)(sizeof(s_groups) + sizeof(s_delayed_receipts) +
        sizeof(s_delayed_fusions) + sizeof(s_delayed_epoch) + sizeof(s_delayed_barrier) +
        sizeof(s_delayed_evaluation) + sizeof(s_delayed_used) + sizeof(s_delayed_initialized) +
        sizeof(s_epoch_us) + sizeof(s_imu_faults) + sizeof(s_model_mismatch));
    uint32_t offset = 0U;
    if ((output == NULL) || (capacity < size)) { return size; }
    memcpy(output + offset, s_groups, sizeof(s_groups)); offset += (uint32_t)sizeof(s_groups);
    memcpy(output + offset, s_delayed_receipts, sizeof(s_delayed_receipts)); offset += (uint32_t)sizeof(s_delayed_receipts);
    memcpy(output + offset, s_delayed_fusions, sizeof(s_delayed_fusions)); offset += (uint32_t)sizeof(s_delayed_fusions);
    memcpy(output + offset, s_delayed_epoch, sizeof(s_delayed_epoch)); offset += (uint32_t)sizeof(s_delayed_epoch);
    memcpy(output + offset, s_delayed_barrier, sizeof(s_delayed_barrier)); offset += (uint32_t)sizeof(s_delayed_barrier);
    memcpy(output + offset, s_delayed_evaluation, sizeof(s_delayed_evaluation)); offset += (uint32_t)sizeof(s_delayed_evaluation);
    memcpy(output + offset, s_delayed_used, sizeof(s_delayed_used)); offset += (uint32_t)sizeof(s_delayed_used);
    memcpy(output + offset, &s_delayed_initialized, sizeof(s_delayed_initialized)); offset += (uint32_t)sizeof(s_delayed_initialized);
    memcpy(output + offset, &s_epoch_us, sizeof(s_epoch_us)); offset += (uint32_t)sizeof(s_epoch_us);
    memcpy(output + offset, &s_imu_faults, sizeof(s_imu_faults)); offset += (uint32_t)sizeof(s_imu_faults);
    memcpy(output + offset, &s_model_mismatch, sizeof(s_model_mismatch));
    return size;
}
