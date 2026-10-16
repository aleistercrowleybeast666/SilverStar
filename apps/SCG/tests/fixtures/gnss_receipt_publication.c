/* Actual selector and receipt reader with CPU-only source/time/device ports.
 * A higher-priority reader is scheduled at the source/barrier publication gap. */
#include "system_time.h"
#include "platform_critical.h"
#include "system_gnss_receipt.h"

int ReceiptFixture_OriginalMain(int argc, char **argv);
uint64_t ReceiptFixture_BaseTimeGet(void);
PlatformCriticalState ReceiptFixture_BaseCriticalEnter(void);
void ReceiptFixture_BaseCriticalExit(PlatformCriticalState state);
#define main ReceiptFixture_OriginalMain
#define SystemTime_GetMonotonicUs ReceiptFixture_BaseTimeGet
#define PlatformCritical_Enter ReceiptFixture_BaseCriticalEnter
#define PlatformCritical_Exit ReceiptFixture_BaseCriticalExit
#define ProjectGnssInstance_TimeGet ReceiptFixture_BaseNativeGet
#define ProjectGnssInstance_LatestSampleGet ReceiptFixture_BaseSampleGet
#include SOURCE_SELECTOR_FIXTURE
#undef main
#undef SystemTime_GetMonotonicUs
#undef PlatformCritical_Enter
#undef PlatformCritical_Exit
#undef ProjectGnssInstance_TimeGet
#undef ProjectGnssInstance_LatestSampleGet
SystemDeviceResult ProjectGnssInstance_TimeGet(uint8_t instance_id, SystemGnssTime *native);
SystemDeviceResult ProjectGnssInstance_LatestSampleGet(uint8_t instance_id, SystemGnssSample *sample);
#include SOURCE_SELECTOR_SOURCE

static uint32_t s_receipt_critical_depth;
static uint8_t s_receipt_inject;
static uint8_t s_receipt_deferred;
static uint8_t s_receipt_probed;
static SystemDeviceResult s_receipt_probe_result;
static SystemGnssReceiptSnapshot s_receipt_probe_output;
static uint8_t s_receipt_native_available;
static SystemGnssTime s_receipt_native;

SystemDeviceResult ProjectGnssInstance_TimeGet(uint8_t instance_id, SystemGnssTime *native)
{
    TEST_CHECK(s_receipt_critical_depth != 0U);
    if (s_receipt_native_available == 0U)
    { return ReceiptFixture_BaseNativeGet(instance_id, native); }
    *native = s_receipt_native;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectGnssInstance_LatestSampleGet(uint8_t instance_id, SystemGnssSample *sample)
{
    TEST_CHECK(s_receipt_critical_depth != 0U);
    return ReceiptFixture_BaseSampleGet(instance_id, sample);
}

static void ReceiptFixture_Probe(void)
{
    memset(&s_receipt_probe_output,0xA5,sizeof(s_receipt_probe_output));
    s_receipt_probe_result = SystemGnss_ReceiptSnapshotGet(&s_receipt_probe_output);
    s_receipt_probed = 1U;
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_receipt_critical_depth;
    s_receipt_critical_depth++;
    return previous;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    TEST_CHECK(s_receipt_critical_depth == state+1U);
    s_receipt_critical_depth = state;
    if ((state == 0U) && s_receipt_deferred)
    { s_receipt_deferred = 0U; ReceiptFixture_Probe(); }
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    if (s_receipt_inject && (s_gnss.active == 1U) && (s_gnss.active_after_us == 0U))
    {
        s_receipt_inject = 0U;
        if (s_receipt_critical_depth != 0U) { s_receipt_deferred = 1U; }
        else { ReceiptFixture_Probe(); }
    }
    return ReceiptFixture_BaseTimeGet();
}

static void ReceiptFixture_Setup(void)
{
    Test_StateReset();
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    s_now_us = 2000000ULL;
    s_gnss_sample[1].sample_timestamp_us = 1000000ULL;
    s_gnss_sample[1].receive_timestamp_us = 1000000ULL;
    s_gnss_sample[1].sequence = 7U;
    s_receipt_critical_depth = 0U; s_receipt_deferred = 0U;
    s_receipt_probed = 0U; s_receipt_inject = 1U;
    s_receipt_native_available = 0U;
}

static void ReceiptFixture_Publication(uint8_t recovery)
{
    ReceiptFixture_Setup();
    if (recovery)
    {
        /* Explicit initialized CPU state with no selected receiver. */
        s_gnss.active = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
        s_gnss.active_position = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
        SystemSourceSelector_GnssRecoveryAttempt(1U,1U);
    }
    else
    {
        s_gnss_health[0].online = 0U;
        SystemSourceSelector_GnssSwitchEvaluate();
    }
    TEST_CHECK(s_receipt_probed == 1U);
    TEST_CHECK(s_receipt_probe_result == SYSTEM_DEVICE_NOT_READY);
    /* Failed reads must preserve the actual caller bytes. */
    SystemGnssReceiptSnapshot expected;
    memset(&expected,0xA5,sizeof(expected));
    TEST_CHECK(memcmp(&s_receipt_probe_output,&expected,sizeof(expected)) == 0);
    TEST_CHECK(s_receipt_critical_depth == 0U && s_gnss.active == 1U);
    s_gnss_sample[1].sample_timestamp_us = s_now_us+1U;
    s_gnss_sample[1].receive_timestamp_us = s_now_us+1U;
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&s_receipt_probe_output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_receipt_probe_output.source == 1U && s_receipt_probe_output.sample.sequence == 7U);
}

static void ReceiptFixture_Clock(void)
{
    SystemGnssReceiptSnapshot receipt = {0};
    receipt.sample.sequence = 7U; receipt.sample.sample_timestamp_us = 999000ULL;
    receipt.sample.receive_timestamp_us = 1000000ULL;
    receipt.native_result = SYSTEM_DEVICE_UNSUPPORTED;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    receipt.sample.measurement_timestamp_trusted = 1U;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE);
    receipt.sample.measurement_timestamp_trusted = 2U;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    receipt.sample.measurement_timestamp_trusted = 0U;
    receipt.native_result = SYSTEM_DEVICE_OK; receipt.native.sequence = 7U;
    receipt.native.sample_timestamp_us = receipt.sample.sample_timestamp_us;
    receipt.native.receive_timestamp_us = receipt.sample.receive_timestamp_us;
    receipt.native.time_valid = 1U; receipt.native.date_valid = 1U; receipt.native.fully_resolved = 1U;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW);
    receipt.native.sequence++;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    receipt.native.sequence--; receipt.native.time_of_week_ms = 604800000U;
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&receipt) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(NULL) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
}

static void ReceiptFixture_Snapshot(void)
{
    SystemGnssReceiptSnapshot output;
    SystemGnssReceiptSnapshot unchanged;
    PlatformCriticalState outer;
    ReceiptFixture_Setup(); s_receipt_inject = 0U;
    memset(&output,0xA5,sizeof(output)); unchanged = output;
    s_gnss.active = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(memcmp(&output,&unchanged,sizeof(output)) == 0);
    s_gnss.active = PROJECT_GNSS_INSTANCE_COUNT_MAX;
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(memcmp(&output,&unchanged,sizeof(output)) == 0);
    s_gnss.active = 1U;
    s_gnss.active_position = 1U;
    outer = PlatformCritical_Enter();
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_receipt_critical_depth == 1U);
    PlatformCritical_Exit(outer);
    TEST_CHECK(output.source == 1U && output.sample.sequence == 7U);
    TEST_CHECK(output.native_result == SYSTEM_DEVICE_NOT_PRESENT);
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&output) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    s_receipt_native_available = 1U;
    memset(&s_receipt_native,0,sizeof(s_receipt_native));
    s_receipt_native.sequence = 7U;
    s_receipt_native.sample_timestamp_us = 1000000ULL;
    s_receipt_native.receive_timestamp_us = 1000000ULL;
    s_receipt_native.time_valid = 1U; s_receipt_native.date_valid = 1U;
    s_receipt_native.fully_resolved = 1U;
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&output) == SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW);
    s_receipt_native.sequence++;
    TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnssReceipt_ClockBasisGet(&output) == SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN);
    TEST_CHECK(s_receipt_critical_depth == 0U);
}

static void ReceiptFixture_CorruptSelector(void)
{
    ReceiptFixture_Setup(); s_receipt_inject = 0U;
    s_gnss.active = 1U; s_gnss.active_position = 1U;
    SystemSourceSelectorGnssState original = s_gnss;
    for (uint8_t scenario = 0U; scenario < 5U; scenario++)
    {
        SystemGnssReceiptSnapshot output, unchanged;
        s_gnss = original;
        if (scenario == 0U) { s_gnss.active = s_gnss.count; }
        if (scenario == 1U) { s_gnss.active_position = s_gnss.count; }
        if (scenario == 2U) { s_gnss.order[1] = 2U; }
        if (scenario == 3U) { s_gnss.count = PROJECT_GNSS_INSTANCE_COUNT_MAX + 1U; }
        if (scenario == 4U) { s_gnss.count = 0U; }
        memset(&output,0xA5,sizeof(output)); unchanged = output;
        TEST_CHECK(SystemGnss_ReceiptSnapshotGet(&output) == SYSTEM_DEVICE_BAD_STATE);
        TEST_CHECK(memcmp(&output,&unchanged,sizeof(output)) == 0);
        TEST_CHECK(s_receipt_critical_depth == 0U);
    }
}

int main(int argc, char **argv)
{
    uint32_t scenario = (argc == 2) ? (uint32_t)strtoul(argv[1],NULL,10) : 2U;
    if (scenario < 2U) { ReceiptFixture_Publication((uint8_t)scenario); }
    else if (scenario == 2U) { ReceiptFixture_Clock(); }
    else if (scenario == 3U) { ReceiptFixture_Snapshot(); }
    else { ReceiptFixture_CorruptSelector(); }
    return Test_Finish("gnss_receipt_actual_publication");
}
