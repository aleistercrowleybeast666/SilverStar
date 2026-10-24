#ifndef __CAPTURE_TEST_ACCESS_H
#define __CAPTURE_TEST_ACCESS_H
#include <installation_capture.h>
void InstallationCapture_TestReset(void);
void InstallationCapture_TestCorruptQueue(void);
InstallationCaptureResult InstallationCapture_TestGuard(uint8_t held);
#endif
