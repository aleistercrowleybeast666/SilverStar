#include <setjmp.h>
#define main Test_PreviousMain
#define ProjectImuInstance_Init Test_PortImuInit
#define ProjectImuInstance_Start Test_PortImuStart
#define ProjectGnssInstance_Init Test_PortGnssInit
#define ProjectGnssInstance_Start Test_PortGnssStart
#define ProjectTelemetryInstance_Init Test_PortTelemetryInit
#define ProjectTelemetryInstance_Start Test_PortTelemetryStart
#include "test_source_selector.c"
#undef main
#undef ProjectImuInstance_Init
#undef ProjectImuInstance_Start
#undef ProjectGnssInstance_Init
#undef ProjectGnssInstance_Start
#undef ProjectTelemetryInstance_Init
#undef ProjectTelemetryInstance_Start

SystemDeviceResult ProjectImuInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectImuInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectGnssInstance_Start(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_Init(uint8_t instance_id);
SystemDeviceResult ProjectTelemetryInstance_Start(uint8_t instance_id);
static jmp_buf s_fault_return;
static uint8_t s_mutate_order;
static uint32_t s_invalid_port_calls;
static _Noreturn void Test_Trap(void) { longjmp(s_fault_return, 1); }
#define __builtin_trap() Test_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "system_source_selector.c"

#define WRAP_INIT(name, old, context, id) \
    SystemDeviceResult name(uint8_t index) { \
        if (index >= TEST_INSTANCE_COUNT) { s_invalid_port_calls++; return SYSTEM_DEVICE_IO_ERROR; } \
        SystemDeviceResult result = old(index); \
        if (s_mutate_order == id && index == 0U) { context.order[1] = TEST_INSTANCE_COUNT; } \
        return result; }
#define WRAP_START(name, old) \
    SystemDeviceResult name(uint8_t index) { \
        if (index >= TEST_INSTANCE_COUNT) { s_invalid_port_calls++; return SYSTEM_DEVICE_IO_ERROR; } \
        return old(index); }
WRAP_INIT(ProjectImuInstance_Init, Test_PortImuInit, s_imu, 1U)
WRAP_INIT(ProjectGnssInstance_Init, Test_PortGnssInit, s_gnss, 2U)
WRAP_INIT(ProjectTelemetryInstance_Init, Test_PortTelemetryInit, s_telemetry, 3U)
WRAP_START(ProjectImuInstance_Start, Test_PortImuStart)
WRAP_START(ProjectGnssInstance_Start, Test_PortGnssStart)
WRAP_START(ProjectTelemetryInstance_Start, Test_PortTelemetryStart)

static SystemDeviceResult Test_Init(uint8_t kind)
{
    if (kind == 1U) { return SystemImu_Init(); }
    if (kind == 2U) { return SystemGnss_Init(); }
    return SystemTelemetry_Init();
}
static SystemDeviceResult Test_Start(uint8_t kind)
{
    if (kind == 1U) { return SystemImu_Start(); }
    if (kind == 2U) { return SystemGnss_Start(); }
    return SystemTelemetry_Start();
}

static void Test_StartFailure(uint8_t kind)
{
    Test_StateReset();
    s_imu_count = 1U; s_gnss_count = 1U; s_telemetry_count = 1U;
    TEST_CHECK(Test_Init(kind) == SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_Start(kind) == SYSTEM_DEVICE_OK);
    if (kind == 1U) { s_imu_start_result[0] = SYSTEM_DEVICE_IO_ERROR; }
    if (kind == 2U) { s_gnss_start_result[0] = SYSTEM_DEVICE_IO_ERROR; }
    if (kind == 3U) { s_telemetry_start_result[0] = SYSTEM_DEVICE_IO_ERROR; }
    TEST_CHECK(Test_Start(kind) == ((kind == 3U) ? SYSTEM_DEVICE_NOT_READY : SYSTEM_DEVICE_IO_ERROR));
    TEST_CHECK(((kind == 1U) ? s_imu.started[0] : (kind == 2U) ? s_gnss.started[0] : s_telemetry.started[0]) == 0U);
    if (kind == 3U)
    {
        uint8_t payload = 1U;
        TEST_CHECK(SystemTelemetry_Send(&payload, 1U) == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(s_telemetry_send_count[0] == 0U);
    }
    TEST_CHECK(SilverStarAssert_FaultedGet() == 0U);
}

static void Test_Fault(uint8_t kind, const char *case_name)
{
    SilverStarAssertFaultRecord record;
    volatile SilverStarAssertReasonId reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE;
    volatile uint8_t init_case = (uint8_t)(strncmp(case_name, "init_", 5U) == 0);
    Test_StateReset();
    if (init_case == 0U) { TEST_CHECK(Test_Init(kind) == SYSTEM_DEVICE_OK); }
    if (strcmp(case_name, "init_order") == 0) { s_mutate_order = kind; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "init_result") == 0)
    {
        if (kind == 1U) { s_imu_init_result[0] = (SystemDeviceResult)99U; }
        if (kind == 2U) { s_gnss_init_result[0] = (SystemDeviceResult)99U; }
        if (kind == 3U) { s_telemetry_init_result[0] = (SystemDeviceResult)99U; }
    }
    else if (strcmp(case_name, "start_result") == 0)
    {
        if (kind == 1U) { s_imu_start_result[0] = (SystemDeviceResult)99U; }
        if (kind == 2U) { s_gnss_start_result[0] = (SystemDeviceResult)99U; }
        if (kind == 3U) { s_telemetry_start_result[0] = (SystemDeviceResult)99U; }
    }
    else if (strcmp(case_name, "start_order") == 0)
    {
        if (kind == 1U) { s_imu.order[0] = TEST_INSTANCE_COUNT; }
        if (kind == 2U) { s_gnss.order[1] = TEST_INSTANCE_COUNT; }
        if (kind == 3U) { s_telemetry.active = TEST_INSTANCE_COUNT; }
        reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE;
    }
    else if (strcmp(case_name, "start_active") == 0)
    { s_gnss.active = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "start_position") == 0)
    { s_gnss.active_position = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(case_name, "start_count") == 0)
    {
        if (kind == 1U) { s_imu.count = PROJECT_IMU_INSTANCE_COUNT_MAX + 1U; }
        if (kind == 2U) { s_gnss.count = PROJECT_GNSS_INSTANCE_COUNT_MAX + 1U; }
        if (kind == 3U) { s_telemetry.count = PROJECT_TELEMETRY_INSTANCE_COUNT_MAX + 1U; }
        reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY;
    }
    else { TEST_CHECK(0); }
    if (setjmp(s_fault_return) == 0)
    {
        if (init_case != 0U) { (void)Test_Init(kind); }
        else { (void)Test_Start(kind); }
        TEST_CHECK(0);
    }
    else
    {
        TEST_CHECK(SilverStarAssert_FaultRecordGet(&record) == 1U);
        TEST_CHECK(record.reason_id == reason);
        TEST_CHECK(record.module_id == SILVERSTAR_ASSERT_MODULE_SYSTEM);
        TEST_CHECK(record.line != 0U);
    }
    TEST_CHECK(s_invalid_port_calls == 0U);
    if (strcmp(case_name, "init_result") == 0)
    { TEST_CHECK(((kind == 1U) ? s_imu.initialized[0] : (kind == 2U) ? s_gnss.initialized[0] : s_telemetry.initialized[0]) == 0U); }
    if (strcmp(case_name, "start_result") == 0)
    { TEST_CHECK(((kind == 1U) ? s_imu.started[0] : (kind == 2U) ? s_gnss.started[0] : s_telemetry.started[0]) == 0U); }
}

static void Test_SwitchFault(const char *case_name)
{
    SilverStarAssertFaultRecord record;
    volatile SilverStarAssertReasonId reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT;
    Test_StateReset();
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    if (strcmp(case_name, "gnss_count") == 0)
    { s_gnss.count = PROJECT_GNSS_INSTANCE_COUNT_MAX + 1U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if (strcmp(case_name, "gnss_active") == 0)
    { s_gnss.active = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "gnss_position") == 0) { s_gnss.active_position = TEST_INSTANCE_COUNT; }
    else if (strcmp(case_name, "gnss_order") == 0)
    { s_gnss_health[0].online = 0U; s_gnss.order[1] = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "next_count") == 0)
    { s_telemetry.count = PROJECT_TELEMETRY_INSTANCE_COUNT_MAX + 1U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if (strcmp(case_name, "next_position") == 0) { s_telemetry.active_position = TEST_INSTANCE_COUNT; }
    else if (strcmp(case_name, "next_order") == 0)
    { s_telemetry.order[1] = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "next_result") == 0)
    { s_telemetry_start_result[1] = (SystemDeviceResult)99U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(case_name, "health_count") == 0)
    { s_telemetry.count = PROJECT_TELEMETRY_INSTANCE_COUNT_MAX + 1U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if (strcmp(case_name, "health_active") == 0)
    { s_telemetry.active = TEST_INSTANCE_COUNT; reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE; }
    else if (strcmp(case_name, "health_timeout") == 0)
    { s_telemetry.consecutive_timeout_count = SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT + 1U; }
    else { TEST_CHECK(0); }
    if (setjmp(s_fault_return) == 0)
    {
        if (strncmp(case_name, "gnss_", 5U) == 0) { SystemSourceSelector_GnssSwitchEvaluate(); }
        else if (strncmp(case_name, "next_", 5U) == 0) { (void)SystemSourceSelector_TelemetryNextStart(); }
        else { SystemSourceSelector_TelemetryHealthProcess(); }
        TEST_CHECK(0);
    }
    else
    {
        TEST_CHECK(SilverStarAssert_FaultRecordGet(&record) == 1U);
        TEST_CHECK(record.module_id == SILVERSTAR_ASSERT_MODULE_SYSTEM);
        TEST_CHECK(record.reason_id == reason);
    }
    TEST_CHECK(s_invalid_port_calls == 0U);
    TEST_CHECK(s_telemetry_start_count[2] == 0U);
    TEST_CHECK(s_telemetry.active == ((strcmp(case_name, "health_active") == 0) ? TEST_INSTANCE_COUNT : 0U));
    TEST_CHECK(s_telemetry.started[1] == 0U);
}

static void Test_OrdinaryBoundary(uint8_t kind, const char *case_name)
{
    Test_StateReset();
    if (strcmp(case_name, "init_capacity") == 0)
    {
        s_imu_count = PROJECT_IMU_INSTANCE_COUNT_MAX + 1U;
        s_gnss_count = PROJECT_GNSS_INSTANCE_COUNT_MAX + 1U;
        s_telemetry_count = PROJECT_TELEMETRY_INSTANCE_COUNT_MAX + 1U;
        TEST_CHECK(Test_Init(kind) == SYSTEM_DEVICE_INTERNAL_ERROR);
        TEST_CHECK(Test_Start(kind) == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(s_imu_init_count[0] + s_gnss_init_count[0] + s_telemetry_init_count[0] == 0U);
    }
    else
    {
        TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
        s_telemetry.started[1] = 1U;
        s_telemetry_start_result[1] = SYSTEM_DEVICE_IO_ERROR;
        s_telemetry_start_result[2] = SYSTEM_DEVICE_IO_ERROR;
        TEST_CHECK(SystemSourceSelector_TelemetryNextStart() == 0U);
        TEST_CHECK(s_telemetry.active == 0U && s_telemetry.active_position == 0U);
        TEST_CHECK(s_telemetry.started[1] == 0U);
    }
    TEST_CHECK(SilverStarAssert_FaultedGet() == 0U);
}

int main(int argc, char **argv)
{
    if (argc != 3) { return 2; }
    uint8_t kind = (uint8_t)(argv[1][0] - '0');
    if (kind == 0U)
    {
        Test_SwitchFault(argv[2]);
        return Test_Finish("source_selector_switch_contract");
    }
    if (strcmp(argv[2], "normal") == 0) { return Test_PreviousMain(); }
    if ((strcmp(argv[2], "init_capacity") == 0) || (strcmp(argv[2], "next_failed_restart") == 0))
    {
        Test_OrdinaryBoundary(kind, argv[2]);
        return Test_Finish("source_selector_ordinary_boundary");
    }
    if (strcmp(argv[2], "failed_restart") == 0) { Test_StartFailure(kind); }
    else { Test_Fault(kind, argv[2]); }
    return Test_Finish("source_selector_contract");
}
