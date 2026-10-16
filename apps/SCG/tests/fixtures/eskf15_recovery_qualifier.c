/* Explicit synthetic qualification policy; no hardware or flight settings. */
#include "navigation_eskf_recovery_qualifier.h"
#include "system_source_selector.h"
#include "platform_critical.h"
#include <float.h>
#include <math.h>
#include <string.h>

int Test_RecoveryQualifier(uint32_t scenario);
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *source)
{ (void)source; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ (void)sample; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *native)
{ (void)native; return SYSTEM_DEVICE_NOT_READY; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

#define CHECK(predicate) do { if (!(predicate)) { return __LINE__; } } while (0)

static void QualifierTest_Packet(SystemGnssReceiptSnapshot *receipt,
    uint32_t sequence, uint64_t receive_us, uint32_t tow_ms)
{
    memset(receipt, 0, sizeof(*receipt));
    receipt->sample.sequence = sequence;
    receipt->sample.sample_timestamp_us = receive_us;
    receipt->sample.receive_timestamp_us = receive_us;
    receipt->sample.online = 1U; receipt->sample.fix_ok = 1U; receipt->sample.fix_type = 3U;
    receipt->sample.supported_fields = SYSTEM_GNSS_FIELD_FIX_TYPE | SYSTEM_GNSS_FIELD_FIX_OK |
        SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HEIGHT | SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY |
        SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY | SYSTEM_GNSS_FIELD_VELOCITY_HORIZONTAL |
        SYSTEM_GNSS_FIELD_VELOCITY_VERTICAL | SYSTEM_GNSS_FIELD_SPEED_ACCURACY;
    receipt->sample.valid_fields = receipt->sample.supported_fields;
    receipt->sample.valid_group_mask = 15U; receipt->sample.physical_valid_group_mask = 15U;
    receipt->sample.velocity_valid_mask = 7U;
    receipt->sample.velocity_enu_mps[0] = 10.0f;
    receipt->sample.velocity_enu_mps[1] = -4.0f;
    receipt->sample.velocity_enu_mps[2] = 2.0f;
    receipt->sample.horizontal_accuracy_m = 0.5f; receipt->sample.vertical_accuracy_m = 1.0f;
    receipt->sample.speed_accuracy_mps = 0.1f;
    receipt->native_result = SYSTEM_DEVICE_OK;
    receipt->native.sequence = sequence; receipt->native.sample_timestamp_us = receive_us;
    receipt->native.receive_timestamp_us = receive_us; receipt->native.time_of_week_ms = tow_ms;
    receipt->native.time_valid = 1U; receipt->native.date_valid = 1U; receipt->native.fully_resolved = 1U;
}

int Test_RecoveryQualifier(uint32_t scenario)
{
    NavigationEskfRecoveryQualifier qualifier;
    NavigationEskfRecoveryQualifierConfig config = {250000ULL, 1000ULL, 10.0f, 8.0f, 3.0f};
    NavigationEskfRecoveryQualifierOutput output, unchanged_output;
    NavigationEskfRecoveryQualifier original;
    SystemGnssReceiptSnapshot receipt;
    float position[3] = {0.0f, 0.0f, 0.0f};
    uint8_t mask = 15U, no_write = 0U;
    uint32_t reason = 0U;
    uint64_t present = 1040000ULL;
    NavigationEskfRecoveryQualifierResult expected = NAV_ESKF_QUALIFIER_COMPLETE;
    CHECK(NavigationEskfRecoveryQualifier_Reset(&qualifier) == NAV_ESKF_QUALIFIER_COMPLETE);
    QualifierTest_Packet(&receipt, (scenario == 37U) ? UINT32_MAX : 1U, 1000000ULL,
        (scenario == 11U) ? 604799980U : 300000U);
    if (scenario == 4U) { receipt.sample.measurement_timestamp_trusted = 1U; }
    CHECK(NavigationEskfRecoveryQualifier_Receive(&qualifier, &config, &receipt, position,
        1000000ULL, &output) == NAV_ESKF_QUALIFIER_BASELINE);
    QualifierTest_Packet(&receipt, (scenario == 37U) ? 1U : 2U, 1040000ULL,
        (scenario == 11U) ? 20U : 300040U);
    position[0] = 0.4f; position[1] = -0.16f; position[2] = 0.08f;
    switch (scenario)
    {
        case 0U: break;
        case 1U: receipt.native.fully_resolved = 0U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 2U: receipt.native.sequence++; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 3U: receipt.native_result = SYSTEM_DEVICE_UNSUPPORTED; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 4U: receipt.sample.measurement_timestamp_trusted = 1U; receipt.native_result = SYSTEM_DEVICE_UNSUPPORTED; break;
        case 5U: receipt.source = 1U; mask = 0U; expected = NAV_ESKF_QUALIFIER_BASELINE; break;
        case 6U: receipt.sample.sequence = 1U; expected = NAV_ESKF_QUALIFIER_DUPLICATE; no_write = 1U; break;
        case 7U: receipt.sample.sequence = UINT32_MAX; expected = NAV_ESKF_QUALIFIER_DISCONTINUITY; no_write = 1U; break;
        case 8U: receipt.sample.receive_timestamp_us = 999999ULL; expected = NAV_ESKF_QUALIFIER_DISCONTINUITY; no_write = 1U; break;
        case 9U: receipt.native.time_of_week_ms = 300000U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 10U: receipt.native.time_of_week_ms = 299999U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 11U: break;
        case 12U: receipt.native.time_of_week_ms = 301000U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_INTERVAL; break;
        case 13U:
            receipt.sample.sample_timestamp_us = 1080000ULL; receipt.sample.receive_timestamp_us = 1080000ULL;
            receipt.native.sample_timestamp_us = 1080000ULL; receipt.native.receive_timestamp_us = 1080000ULL;
            present = 1080000ULL; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_JITTER; break;
        case 14U:
            QualifierTest_Packet(&receipt, 2U, 2000000ULL, 301000U); present = 2000000ULL;
            position[0] = 10.0f; position[1] = -4.0f; position[2] = 2.0f;
            mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_INTERVAL; break;
        case 15U: position[0] += 1000.0f; mask = 14U; break;
        case 16U: receipt.sample.velocity_enu_mps[0] += 500.0f; mask = 10U; break;
        case 17U: position[2] += 1000.0f; mask = 13U; break;
        case 18U: receipt.sample.velocity_enu_mps[2] += 500.0f; mask = 5U; break;
        case 19U: receipt.sample.supported_fields &= ~SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY; mask = 14U; break;
        case 20U: receipt.sample.valid_fields &= ~SYSTEM_GNSS_FIELD_SPEED_ACCURACY; mask = 0U; break;
        case 21U: receipt.sample.horizontal_accuracy_m = 0.0f; mask = 14U; break;
        case 22U: receipt.sample.speed_accuracy_mps = NAN; mask = 0U; break;
        case 23U: position[0] = NAN; mask = 14U; break;
        case 24U: receipt.sample.velocity_enu_mps[0] = 1.0e30f; mask = 10U; break;
        case 25U: present = 1039999ULL; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_STALE; no_write = 2U; break;
        case 26U: present = 1540001ULL; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_STALE; no_write = 2U; break;
        case 27U: qualifier.initialized = 2U; expected = NAV_ESKF_QUALIFIER_BAD_STATE; no_write = 1U; break;
        case 28U: qualifier.week_us = 1ULL; expected = NAV_ESKF_QUALIFIER_BAD_STATE; no_write = 1U; break;
        case 29U: expected = NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; no_write = 1U; break;
        case 30U: expected = NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; no_write = 1U; break;
        case 31U: config.closure_sigma = NAN; expected = NAV_ESKF_QUALIFIER_INVALID_ARGUMENT; no_write = 1U; break;
        case 32U: receipt.sample.physical_valid_group_mask = UINT8_MAX; mask = 0U; break;
        case 33U: receipt.native.time_of_week_ms = 604800000U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 34U: receipt.sample.measurement_timestamp_trusted = 2U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 35U: receipt.native.sample_timestamp_us--; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_CLOCK; break;
        case 36U: receipt.sample.sequence = 0U; mask = 0U; reason = NAV_ESKF_QUALIFIER_REASON_STALE; no_write = 2U; break;
        case 37U: break;
        case 38U: receipt.sample.speed_accuracy_mps = FLT_MAX; mask = 0U; break;
        default: return -1;
    }
    if ((mask == 0U) && (expected == NAV_ESKF_QUALIFIER_COMPLETE)) { expected = NAV_ESKF_QUALIFIER_INELIGIBLE; }
    memset(&output, 0xA5, sizeof(output)); unchanged_output = output; original = qualifier;
    NavigationEskfRecoveryQualifierResult result = NavigationEskfRecoveryQualifier_Receive(&qualifier,
        &config, (scenario == 30U) ? &qualifier.previous : &receipt, position, present,
        (scenario == 29U) ? (NavigationEskfRecoveryQualifierOutput *)(void *)&qualifier : &output);
    CHECK(result == expected);
    if (no_write != 0U) { CHECK(memcmp(&qualifier, &original, sizeof(qualifier)) == 0); }
    if (no_write == 1U) { CHECK(memcmp(&output, &unchanged_output, sizeof(output)) == 0); return 0; }
    CHECK(output.coherent_mask == mask);
    if (reason != 0U) { CHECK((output.reasons & reason) != 0U); }
    if (scenario == 0U)
    { CHECK(output.native_us == 300040000ULL && output.native_us > receipt.sample.receive_timestamp_us); }
    if (scenario == 4U)
    { CHECK(output.native_us == receipt.sample.sample_timestamp_us && output.clock_basis == SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE); }
    if (scenario == 11U) { CHECK(output.native_us == 604800020000ULL); }
    if ((scenario == 14U) || (scenario == 32U))
    {
        uint64_t next_receive = receipt.sample.receive_timestamp_us + 40000ULL;
        uint32_t next_tow = receipt.native.time_of_week_ms + 40U;
        QualifierTest_Packet(&receipt, 3U, next_receive, next_tow);
        position[0] += 0.4f; position[1] -= 0.16f; position[2] += 0.08f;
        result = NavigationEskfRecoveryQualifier_Receive(&qualifier, &config, &receipt, position, next_receive, &output);
        CHECK(result == ((scenario == 14U) ? NAV_ESKF_QUALIFIER_COMPLETE : NAV_ESKF_QUALIFIER_INELIGIBLE));
        CHECK(output.coherent_mask == ((scenario == 14U) ? 15U : 0U));
    }
    return 0;
}
