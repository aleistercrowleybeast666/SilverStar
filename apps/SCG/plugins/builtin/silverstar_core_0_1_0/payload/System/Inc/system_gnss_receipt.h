#ifndef __SYSTEM_GNSS_RECEIPT_H
#define __SYSTEM_GNSS_RECEIPT_H

#include "system_gnss_if.h"

typedef enum
{
    SYSTEM_GNSS_RECEIPT_CLOCK_UNPROVEN = 0,
    SYSTEM_GNSS_RECEIPT_CLOCK_MCU_SAMPLE,
    SYSTEM_GNSS_RECEIPT_CLOCK_NATIVE_ITOW
} SystemGnssReceiptClockBasis;

/* CPU-owned value copy. The native clock is not a claim that GNSS iTOW is on
 * the MCU axis; ordinary measurement delay resolution remains separate. */
typedef struct
{
    SystemGnssSample sample;
    SystemGnssTime native;
    SystemDeviceResult native_result;
    uint8_t source;
} SystemGnssReceiptSnapshot;

/* Cache-only getters execute in one nested-safe critical section. Preserve the
 * selected-source handoff barrier. No port processing, startup or control IO.
 * A native clock failure leaves an available sample readable, with clock proof
 * unavailable. Any overall failure leaves the caller's output unchanged.
 * Full SystemGnss_Init/reset requires quiesced consumers, as in the existing
 * startup lifecycle. Runtime route changes and freshness barriers are atomic. */
SystemDeviceResult SystemGnss_ReceiptSnapshotGet(SystemGnssReceiptSnapshot *snapshot);
SystemGnssReceiptClockBasis SystemGnssReceipt_ClockBasisGet(
    const SystemGnssReceiptSnapshot *snapshot);

#endif /* __SYSTEM_GNSS_RECEIPT_H */
