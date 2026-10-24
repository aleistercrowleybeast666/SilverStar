/* Link roots only. No vector table or startup; NEVER FLASH this ELF. */
#include <installation_capture.h>
#include <system_installation_capture.h>
#include <stddef.h>

InstallationCaptureResult InstallationCapture_ArmEntry(
    const InstallationCaptureSnapshot *snapshot,const InstallationCaptureSample *sample,
    char *scratch,InstallationCaptureStatus *status);

InstallationCaptureResult InstallationCapture_ArmEntry(
    const InstallationCaptureSnapshot *snapshot,const InstallationCaptureSample *sample,
    char *scratch,InstallationCaptureStatus *status)
{
    InstallationCaptureResult result;uint16_t length,next;uint8_t end;uint32_t token;
    result=InstallationCapture_Enable(1U);if(result!=InstallationCaptureResult_Ok){return result;}
    result=SystemInstallationCapture_Configure(snapshot);if(result!=InstallationCaptureResult_Ok){return result;}
    SystemInstallationCapture_ExecuteLine("INSTALL CAPS",scratch,511U,0U);
    SystemInstallationCapture_Process(0U);
    result=InstallationCapture_Configure(snapshot);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Status(status);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_InfoRead(0U,(uint8_t *)scratch,&length,&next,&end);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_ResourceClaim(2U,&token);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_ResourceRelease(2U,token);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Begin((const uint8_t *)scratch,1U,status->binding,0U);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Face((const uint8_t *)scratch,2U,0U,1U,0U,1U,0U);if(result!=InstallationCaptureResult_Pending){return result;}
    result=InstallationCapture_SourcePush(0U,sample,sample->receive_us);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_RequestTouch((const uint8_t *)scratch,2U,sample->receive_us);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Poll(sample->receive_us);if(result!=InstallationCaptureResult_Pending){return result;}
    result=InstallationCapture_EventPeek(scratch,439U,&length);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_EventCommit(1U);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Cancel((const uint8_t *)scratch,3U,sample->receive_us);if(result!=InstallationCaptureResult_Pending){return result;}
    result=InstallationCapture_ProducerStopped();if(result!=InstallationCaptureResult_Cancelled){return result;}
    result=InstallationCapture_Release();if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Number(snapshot->accel_bias[0],scratch,&length);if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Hash((const uint8_t *)scratch,48U,status->info_sha256);if(result!=InstallationCaptureResult_Ok){return result;}
    return InstallationCapture_Revoke();
}

