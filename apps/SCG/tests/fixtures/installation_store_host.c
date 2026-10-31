/* Host coordinator boundary only. No filesystem, UART, DMA or target entry. */
#include "system_installation_store_if.h"
#include "system_lifecycle.h"
#include "system_time.h"
#include "system_installation_active_if.h"

/* Candidate-only store fixture: no active record consumer is linked. Full
 * generated installation_active_integration exercises that owner separately. */
void SystemInstallationActive_DependenciesChanged(void)
{ }

SystemMaintenanceState SystemLifecycle_MaintenanceGet(void)
{ return SystemMaintenanceState_Ready; }

uint64_t SystemTime_GetMonotonicUs(void)
{ return 0U; }

SystemInstallationStoreResult SystemInstallationStoreStorage_Execute(
    SystemInstallationStoreWork *work, uint32_t *progress, uint32_t *generation)
{
    (void)work; (void)progress; (void)generation;
    return SystemInstallationStoreResult_Unsupported;
}
