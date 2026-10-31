#include "installation_capture.h"
#include "system_installation_capture_if.h"
#include "silverstar_assert.h"
#include "system_installation_active_if.h"

SystemDeviceResult SystemInstallationCapture_OperationBegin(
    SystemInstallationOperation operation,uint8_t continuation)
{
    InstallationCaptureResult result=InstallationCapture_OperationBegin((uint8_t)operation,continuation);
    if(result==InstallationCaptureResult_Ok){return SYSTEM_DEVICE_OK;}
    if(result==InstallationCaptureResult_Invalid){return SYSTEM_DEVICE_INVALID_ARGUMENT;}
    if(result==InstallationCaptureResult_Busy||result==InstallationCaptureResult_Capacity){return SYSTEM_DEVICE_BUSY;}
    return SYSTEM_DEVICE_NOT_READY;
}

void SystemInstallationCapture_OperationEnd(SystemInstallationOperation operation)
{
    InstallationCaptureResult result=InstallationCapture_OperationEnd((uint8_t)operation);
    SILVERSTAR_ASSERT(result==InstallationCaptureResult_Ok||result==InstallationCaptureResult_Stale,
        SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
}

uint8_t SystemInstallationCapture_OperationHeld(SystemInstallationOperation operation)
{return InstallationCapture_OperationHeld((uint8_t)operation);}

void SystemInstallationCapture_DependenciesChanged(void)
{InstallationCapture_DependenciesChanged();SystemInstallationActive_DependenciesChanged();}

SystemDeviceResult SystemInstallationCapture_StartClaim(uint8_t from_alignment,uint32_t *token)
{
    InstallationCaptureResult result=InstallationCapture_StartClaim(from_alignment,token);
    return result==InstallationCaptureResult_Ok?SYSTEM_DEVICE_OK:SYSTEM_DEVICE_BUSY;
}

void SystemInstallationCapture_StartRelease(uint32_t token,uint8_t restore_alignment)
{
    InstallationCaptureResult result=InstallationCapture_StartRelease(token,restore_alignment);
    SILVERSTAR_ASSERT(result==InstallationCaptureResult_Ok||result==InstallationCaptureResult_Stale,
        SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
}
