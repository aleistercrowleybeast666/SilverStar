/* Production state/queue/assertion code. Only the terminal trap is intercepted
 * so the Host can inspect the latched fault and pre-publication state. */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "platform_critical.h"

static jmp_buf s_trap_return;
static uint32_t s_lock_depth;
PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_lock_depth;
    s_lock_depth++;
    return previous;
}
void PlatformCritical_Exit(PlatformCriticalState state) { s_lock_depth = state; }
static _Noreturn void Test_Trap(void) { longjmp(s_trap_return, 1); }
#define __builtin_trap() Test_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "system_navigation_health.c"
#include "common_spsc_queue.c"

#define CHECK(condition) do { if (!(condition)) { \
    (void)fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)

static SystemNavigationFusionEvidence Test_Evidence(void)
{
    SystemNavigationFusionEvidence e = {0};
    e.receive_us = 110U; e.measurement_us = 50U; e.evaluation_us = 120U;
    e.sequence = 1U; e.physically_valid = 1U; e.attempted = 1U;
    e.effective_update = 1U; e.variance_scale = 1.0f; e.nis = 0.5f;
    return e;
}

static void Test_NavigationRejection(const char *name)
{
    SystemNavigationFusionEvidence e = Test_Evidence();
    SystemNavigationGroupHealth before;
    SystemNavigationGroupHealth output;
    SystemNavigationGroupHealth sentinel;
    SystemNavigationHealth_Reset(100U);
    if (strcmp(name, "nav_get_atomic") == 0)
    {
        memset(&output, 0xA5, sizeof(output)); sentinel = output;
        CHECK(SystemNavigationHealth_GroupGet(0U, 99U, &output) == SYSTEM_DEVICE_BAD_STATE);
        CHECK(memcmp(&output, &sentinel, sizeof(output)) == 0);
        CHECK(s_lock_depth == 0U);
        return;
    }
    if (strcmp(name, "nav_before_epoch") == 0)
    {
        e.receive_us = 90U; e.measurement_us = 80U; e.evaluation_us = 99U;
        before = s_groups[0];
        CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_BAD_STATE);
    }
    else if (strcmp(name, "nav_time_regression") == 0)
    {
        CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_OK);
        before = s_groups[0]; e.source = 1U; e.evaluation_us = 119U;
        CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_BAD_STATE);
    }
    else
    {
        before = s_groups[0];
        if (strcmp(name, "nav_physical_bool") == 0) { e.physically_valid = 2U; }
        else if (strcmp(name, "nav_attempt_bool") == 0) { e.attempted = 2U; }
        else if (strcmp(name, "nav_effective_bool") == 0) { e.effective_update = 2U; }
        else if (strcmp(name, "nav_soft_bool") == 0) { e.soft_weighted = 2U; }
        else { CHECK(0); }
        CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    }
    CHECK(memcmp(&before, &s_groups[0], sizeof(before)) == 0);
    CHECK(s_lock_depth == 0U);
    CHECK(SilverStarAssert_FaultedGet() == 0U);
}

static void Test_QueueNormal(void)
{
    CommonSpscQueue queue;
    uint32_t storage[3];
    uint32_t value, output, cycle;
    CHECK(CommonSpscQueue_Init(NULL, storage, 3U, sizeof(value)) == COMMON_SPSC_QUEUE_RESULT_BAD_PARAM);
    CHECK(CommonSpscQueue_Init(&queue, storage, 32768U, sizeof(value)) == COMMON_SPSC_QUEUE_RESULT_BAD_PARAM);
    CHECK(CommonSpscQueue_Init(&queue, storage, 3U, sizeof(value)) == COMMON_SPSC_QUEUE_RESULT_OK);
    /* A non-power-of-two capacity must survive independent 16-bit sequence wrap. */
    for (cycle = 0U; cycle < 70000U; cycle++)
    {
        for (value = 0U; value < 3U; value++)
        { CHECK(CommonSpscQueue_Push(&queue, &value) == COMMON_SPSC_QUEUE_RESULT_OK); }
        CHECK(CommonSpscQueue_Count(&queue) == 3U);
        CHECK(CommonSpscQueue_Push(&queue, &value) == COMMON_SPSC_QUEUE_RESULT_FULL);
        for (value = 0U; value < 3U; value++)
        {
            CHECK(CommonSpscQueue_Pop(&queue, &output) == COMMON_SPSC_QUEUE_RESULT_OK);
            CHECK(output == value);
        }
        output = 0xA5A5A5A5U;
        CHECK(CommonSpscQueue_Pop(&queue, &output) == COMMON_SPSC_QUEUE_RESULT_EMPTY);
        CHECK(output == 0xA5A5A5A5U);
    }
    CHECK(queue.push_count == 210000U); CHECK(queue.pop_count == 210000U);
    CHECK(queue.overflow_count == 70000U);
    CHECK(SilverStarAssert_FaultedGet() == 0U);
}

static void Test_NavigationNormal(void)
{
    SystemNavigationFusionEvidence e = Test_Evidence();
    SystemNavigationGroupHealth output;
    SystemNavigationHealth_Reset(100U);
    CHECK(SystemNavigationHealth_OverallGet(100U, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_WARMUP);
    /* Delayed physical timestamps predating the epoch remain valid. */
    CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_OK);
    CHECK(SystemNavigationHealth_OverallGet(120U, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_HEALTHY);
    CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_BAD_STATE);
    e.source = 1U;
    CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_OK);
    CHECK(SystemNavigationHealth_GroupGet(0U, 120U, &output) == SYSTEM_DEVICE_OK);
    CHECK(output.last_successful_fusion_us == 120U); CHECK(output.recovery_count == 0U);
    CHECK(SystemNavigationHealth_GroupGet(0U, 2000120U, &output) == SYSTEM_DEVICE_OK);
    CHECK(output.state == SYSTEM_NAVIGATION_DEAD_RECKONING);
    e.sequence++; e.receive_us = 2000130U; e.evaluation_us = 2000140U;
    CHECK(SystemNavigationHealth_Observe(0U, &e) == SYSTEM_DEVICE_OK);
    CHECK(SystemNavigationHealth_GroupGet(0U, 2000140U, &output) == SYSTEM_DEVICE_OK);
    CHECK(output.recovery_count == 1U);
    SystemNavigationHealth_ImuQualityRecord(2U);
    SystemNavigationHealth_ImuQualityRecord(0U);
    CHECK(SystemNavigationHealth_GroupGet(0U, 0U, &output) == SYSTEM_DEVICE_OK);
    CHECK(output.state == SYSTEM_NAVIGATION_INVALID); CHECK(output.reason == 0x82U);
    CHECK(SystemNavigationHealth_OverallGet(0U, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
    CHECK(s_lock_depth == 0U); CHECK(SilverStarAssert_FaultedGet() == 0U);
}

static void Test_InternalCorruption(const char *name)
{
    static CommonSpscQueue queue;
    static uint32_t storage[8]; /* Extra canaries make pre-fix logical OOB observable without C UB. */
    static uint32_t storage_before[8];
    static uint32_t output;
    static CommonSpscQueue queue_before;
    static SystemNavigationGroupHealth groups_before[SYSTEM_NAVIGATION_GROUP_COUNT];
    static SystemNavigationGroupHealth nav_output;
    static SystemNavigationGroupHealth nav_sentinel;
    uint32_t value = 1U;
    SilverStarAssertFaultRecord fault;
    volatile SilverStarAssertReasonId reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT;
    volatile uint8_t is_queue = (uint8_t)(strncmp(name, "queue_", 6U) == 0);
    memset(storage, 0xA5, sizeof(storage)); output = 0xA5A5A5A5U;
    CHECK(CommonSpscQueue_Init(&queue, storage, 3U, sizeof(value)) == COMMON_SPSC_QUEUE_RESULT_OK);
    CHECK(CommonSpscQueue_Push(&queue, &value) == COMMON_SPSC_QUEUE_RESULT_OK);
    SystemNavigationHealth_Reset(100U);
    if (strcmp(name, "queue_head_index") == 0) { queue.head_index = 3U; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(name, "queue_tail_index") == 0) { queue.tail_index = 3U; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(name, "queue_capacity") == 0) { queue.capacity = 32768U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if ((strcmp(name, "queue_push_distance") == 0) || (strcmp(name, "queue_pop_distance") == 0))
    { queue.head = 4U; reason = SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT; }
    else if (strcmp(name, "nav_state") == 0) { s_groups[0].state = 99U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "nav_quality") == 0) { s_groups[0].quality = 4U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "nav_success_flag") == 0) { s_groups[0].has_success = 2U; }
    else if (strcmp(name, "nav_receive_flag") == 0) { s_groups[0].has_receive = 2U; }
    else if (strcmp(name, "nav_model_flag") == 0) { s_model_mismatch = 2U; }
    else if (strcmp(name, "nav_fault_mask") == 0) { s_imu_faults = 0x80U; }
    else { CHECK(0); }
    queue_before = queue; memcpy(storage_before, storage, sizeof(storage));
    memcpy(groups_before, s_groups, sizeof(s_groups));
    memset(&nav_output, 0xA5, sizeof(nav_output)); nav_sentinel = nav_output;
    if (setjmp(s_trap_return) == 0)
    {
        if (is_queue != 0U)
        {
            if ((strcmp(name, "queue_tail_index") == 0) || (strcmp(name, "queue_pop_distance") == 0))
            { (void)CommonSpscQueue_Pop(&queue, &output); }
            else { (void)CommonSpscQueue_Push(&queue, &value); }
        }
        else if ((strcmp(name, "nav_model_flag") == 0) || (strcmp(name, "nav_fault_mask") == 0))
        { (void)SystemNavigationHealth_OverallGet(120U, 1U, 0U); }
        else { (void)SystemNavigationHealth_GroupGet(0U, 120U, &nav_output); }
        CHECK(0); /* Real failure must trap before publication or unsafe copy. */
    }
    CHECK(SilverStarAssert_FaultRecordGet(&fault) == 1U);
    CHECK(fault.reason_id == reason); CHECK(fault.line != 0U); CHECK(fault.file_name != NULL);
    CHECK(fault.module_id == ((is_queue != 0U) ? SILVERSTAR_ASSERT_MODULE_COMMON : SILVERSTAR_ASSERT_MODULE_SYSTEM));
    CHECK(memcmp(&queue_before, &queue, sizeof(queue)) == 0);
    CHECK(memcmp(storage_before, storage, sizeof(storage)) == 0);
    CHECK(output == 0xA5A5A5A5U);
    CHECK(memcmp(groups_before, s_groups, sizeof(s_groups)) == 0);
    CHECK(memcmp(&nav_output, &nav_sentinel, sizeof(nav_output)) == 0);
}

int main(int argc, char **argv)
{
    CHECK(argc == 2);
    if (strcmp(argv[1], "queue_normal") == 0) { Test_QueueNormal(); }
    else if (strcmp(argv[1], "nav_normal") == 0) { Test_NavigationNormal(); }
    else if ((strcmp(argv[1], "nav_get_atomic") == 0) ||
             (strcmp(argv[1], "nav_before_epoch") == 0) ||
             (strcmp(argv[1], "nav_time_regression") == 0) || strstr(argv[1], "_bool") != NULL)
    { Test_NavigationRejection(argv[1]); }
    else { Test_InternalCorruption(argv[1]); }
    return 0;
}
