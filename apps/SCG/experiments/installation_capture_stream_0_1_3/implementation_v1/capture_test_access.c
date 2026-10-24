/* Test-only TU includes the exact owning C, then exposes private fault hooks.
 * Never supplied by the plugin/source graph or linked into target firmware. */
#include "capture_test_access.h"
#include <installation_capture.c>
void InstallationCapture_TestReset(void)
{ (void)memset(&s_capture,0,sizeof(s_capture)); }
void InstallationCapture_TestCorruptQueue(void)
{ s_capture.transaction.fields.queue_head=3U;s_capture.transaction.fields.consumer_active=1U; }
InstallationCaptureResult InstallationCapture_TestGuard(uint8_t held)
{
    if(held>1U){return InstallationCaptureResult_Invalid;}
    if(held!=0U){return Capture_Enter()?InstallationCaptureResult_Ok:InstallationCaptureResult_Busy;}
    Capture_Leave();return InstallationCaptureResult_Ok;
}
