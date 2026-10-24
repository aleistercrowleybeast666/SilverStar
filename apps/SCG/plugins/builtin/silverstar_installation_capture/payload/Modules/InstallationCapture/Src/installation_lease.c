#include "installation_capture.h"
#include "system_installation_capture_if.h"
#include "silverstar_assert.h"

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
{InstallationCapture_DependenciesChanged();}
