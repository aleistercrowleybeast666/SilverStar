/* Synthetic endpoint ports. The qualification and its timing/identity
 * rejection paths are the same compilation unit as INSTALL CAPS. */
#include "system_installation_capture_if.h"
#include "system_installation_active_if.h"
#include "system_source_selector.h"
#include "system_descriptor_if.h"
#include "platform_critical.h"
#include "platform_time.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

static uint64_t s_now;
static uint32_t s_depth;
static uint8_t s_selected;

uint64_t PlatformTime_Us(void) { return s_now; }
PlatformCriticalState PlatformCritical_Enter(void) { return s_depth++; }
void PlatformCritical_Exit(PlatformCriticalState lock) { assert(s_depth == lock + 1U); s_depth = lock; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *id)
{ *id = s_selected; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass kind, uint8_t id, SystemDeviceDescriptor *d)
{
    if (id != 0U || (kind != SYSTEM_DEVICE_CLASS_IMU && kind != SYSTEM_DEVICE_CLASS_MAGNETOMETER))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    (void)memset(d, 0, sizeof(*d));
    d->physical_device_id = kind == SYSTEM_DEVICE_CLASS_IMU ? 99U : 42U;
    d->descriptor_id = 7U;
    return SYSTEM_DEVICE_OK;
}

static void Samples_Send(uint32_t index, uint32_t epoch, uint8_t frame_ok, uint16_t physical)
{
    SystemMagnetometerSample mag = {0};
    s_now += 2500ULL;
    SystemInstallationCapture_ProviderImu(0U, epoch, index, index, s_now, frame_ok);
    mag.sequence = index;
    mag.physical_device_id = physical;
    mag.valid_mask = SYSTEM_MAG_VALID_RAW | SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    mag.sample_timestamp_us = s_now - 1000ULL;
    SystemInstallationCapture_ProviderMag(&mag, s_now - 2000ULL, s_now);
}

int main(void)
{
    float matrix[9] = {0};
    s_now = 10000ULL;
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(1U, 6U, 1U, 42U);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(2U, 6U, 1U, 42U);
    assert(SystemInstallationCapture_ActiveQualifiedGet(matrix));
    for (uint8_t i = 0U; i < 9U; i++) { assert(matrix[i] == (i % 4U ? 0.0f : 1.0f)); }
    Samples_Send(3U, 7U, 1U, 42U);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(4U, 7U, 1U, 42U);
    assert(SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(5U, 7U, 0U, 42U);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(6U, 7U, 1U, 77U);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    Samples_Send(7U, 7U, 1U, 42U);
    Samples_Send(8U, 7U, 1U, 42U);
    assert(SystemInstallationCapture_ActiveQualifiedGet(matrix));
    s_now += 4501ULL;
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    s_selected = 1U;
    Samples_Send(9U, 7U, 1U, 42U);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix));
    SystemInstallationCapture_ProviderMag(NULL, 0ULL, 0ULL);
    assert(!SystemInstallationCapture_ActiveQualifiedGet(matrix) && !s_depth);
    puts("PASS selected physical ports, two-frame continuity, common axes, epoch, raw identity, stale, stop");
    return 0;
}
