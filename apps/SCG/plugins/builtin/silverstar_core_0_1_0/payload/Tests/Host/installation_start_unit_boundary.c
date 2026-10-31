/* Logical ALIGN facade for Lifecycle unit tests. Real ALIGN action and
 * collector handoff are exercised in optional_gnss_start_* with real owner. */
#include "system_alignment.h"
#include "system_installation_capture_if.h"
SystemDeviceResult SystemAlignment_StartLeaseBegin(uint32_t *token)
{return SystemInstallationCapture_StartClaim(0U,token);}
void SystemAlignment_StartLeaseEnd(uint32_t token)
{SystemInstallationCapture_StartRelease(token,0U);}
