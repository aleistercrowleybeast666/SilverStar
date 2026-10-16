#include "system_gnss_receipt.h"
#include "system_source_selector.h"
#include "project_device_instances.h"
#include "platform_critical.h"
#include <stddef.h>

SystemDeviceResult SystemGnss_ReceiptSnapshotGet(SystemGnssReceiptSnapshot *snapshot)
{
    SystemGnssReceiptSnapshot candidate = {0};
    PlatformCriticalState critical;
    SystemDeviceResult result;
    uint8_t after = UINT8_MAX;
    if (snapshot == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    candidate.native_result = SYSTEM_DEVICE_NOT_READY;
    critical = PlatformCritical_Enter();
    result = SystemSourceSelector_GnssActiveInstanceGet(&candidate.source);
    if ((result == SYSTEM_DEVICE_OK) && (candidate.source >= PROJECT_GNSS_INSTANCE_COUNT_MAX))
    { result = SYSTEM_DEVICE_BAD_STATE; }
    if (result == SYSTEM_DEVICE_OK) { result = SystemGnss_LatestSampleGet(&candidate.sample); }
    if (result == SYSTEM_DEVICE_OK)
    {
        candidate.native_result = SystemGnss_TimeGet(&candidate.native);
        if ((SystemSourceSelector_GnssActiveInstanceGet(&after) != SYSTEM_DEVICE_OK) ||
            (after != candidate.source)) { result = SYSTEM_DEVICE_BAD_STATE; }
    }
    PlatformCritical_Exit(critical);
    if (result == SYSTEM_DEVICE_OK) { *snapshot = candidate; }
    return result;
}

SystemGnssReceiptClockBasis SystemGnssReceipt_ClockBasisGet(
    const SystemGnssReceiptSnapshot *snapshot)
{
    if ((snapshot == NULL) || (snapshot->sample.sequence == 0U) ||
        (snapshot->sample.sample_timestamp_us == 0U) ||
        (snapshot->sample.sample_timestamp_us > snapshot->sample.receive_timestamp_us))
    { return SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN; }
    if (snapshot->sample.measurement_timestamp_trusted != 0U)
    {
        return (snapshot->sample.measurement_timestamp_trusted == 1U) ?
            SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE : SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN;
    }
    if ((snapshot->native_result != SYSTEM_DEVICE_OK) ||
        (snapshot->native.sequence != snapshot->sample.sequence) ||
        (snapshot->native.sample_timestamp_us != snapshot->sample.sample_timestamp_us) ||
        (snapshot->native.receive_timestamp_us != snapshot->sample.receive_timestamp_us) ||
        (snapshot->native.time_of_week_ms >= 604800000U) ||
        (snapshot->native.time_valid != 1U) || (snapshot->native.date_valid != 1U) ||
        (snapshot->native.fully_resolved != 1U))
    { return SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN; }
    return SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW;
}
