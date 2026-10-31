/* Logical coordination for isolated units; complete owner paths are linked
 * by optional START and installation_active_integration. */
#include "system_installation_capture_if.h"
#include <stddef.h>
static SystemInstallationOperation s_unit_owner;
SystemDeviceResult SystemInstallationCapture_OperationBegin(SystemInstallationOperation operation,uint8_t continuation)
{
    if(s_unit_owner!=0U){return (s_unit_owner==operation&&continuation)?SYSTEM_DEVICE_OK:SYSTEM_DEVICE_BUSY;}
    s_unit_owner=operation;return SYSTEM_DEVICE_OK;
}
void SystemInstallationCapture_OperationEnd(SystemInstallationOperation operation)
{if(s_unit_owner==operation){s_unit_owner=0U;}}
uint8_t SystemInstallationCapture_OperationHeld(SystemInstallationOperation operation)
{return (uint8_t)(s_unit_owner==operation);}
void SystemInstallationCapture_DependenciesChanged(void){}

static uint32_t s_unit_token;
SystemDeviceResult SystemInstallationCapture_StartClaim(uint8_t from_alignment,uint32_t *token)
{
    if(token==NULL||from_alignment>1U){return SYSTEM_DEVICE_INVALID_ARGUMENT;}
    if((from_alignment!=0U&&s_unit_owner!=SystemInstallationOperation_Alignment)||
       (from_alignment==0U&&s_unit_owner!=0U)){return SYSTEM_DEVICE_BUSY;}
    s_unit_owner=SystemInstallationOperation_Start;*token=++s_unit_token;return SYSTEM_DEVICE_OK;
}
void SystemInstallationCapture_StartRelease(uint32_t token,uint8_t restore)
{
    if(token==s_unit_token&&s_unit_owner==SystemInstallationOperation_Start){
        s_unit_owner=restore?SystemInstallationOperation_Alignment:0U;
    }
}
