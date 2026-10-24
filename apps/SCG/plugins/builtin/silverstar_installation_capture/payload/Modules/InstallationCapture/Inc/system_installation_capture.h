#ifndef __SYSTEM_INSTALLATION_CAPTURE_H
#define __SYSTEM_INSTALLATION_CAPTURE_H
#include "installation_capture.h"
#include "system_installation_capture_if.h"
/* Only explicit offline host fixtures can be qualified by this revision.
 * Real providers remain closed until their source/boot/proof contract exists. */
InstallationCaptureResult SystemInstallationCapture_Configure(
    const InstallationCaptureSnapshot *snapshot);
#endif
