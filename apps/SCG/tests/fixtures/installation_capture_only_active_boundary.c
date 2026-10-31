/* Host capture/serial-owner fixture has no active record. The distinct
 * installation_active_consumer.c fixture exercises the real active owner. */
#include "system_installation_active_if.h"

void SystemInstallationActive_Service(uint64_t now_us)
{ (void)now_us; }

void SystemInstallationActive_DependenciesChanged(void)
{ }

uint8_t SystemInstallationActive_ExecuteLine(const char *line, char *response,
    uint16_t capacity, uint64_t now_us)
{
    (void)line; (void)response; (void)capacity; (void)now_us;
    return 0U;
}
