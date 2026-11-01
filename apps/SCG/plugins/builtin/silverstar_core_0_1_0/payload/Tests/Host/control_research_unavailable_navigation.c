/* The legacy lifecycle/logging fixture already returns no estimator snapshot.
 * Its provenance port must agree; it cannot fabricate a READY input. */
#include "estimator_task.h"
SystemDeviceResult EstimatorTask_ControlProvenanceCheck(const SystemNavigationProvenance *provenance,
    uint64_t timestamp_us, uint32_t sequence)
{
    (void)provenance;
    (void)timestamp_us;
    (void)sequence;
    return SYSTEM_DEVICE_NOT_READY;
}
