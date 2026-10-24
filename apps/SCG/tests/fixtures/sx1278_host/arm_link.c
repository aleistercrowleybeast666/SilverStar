/* ARM link-closure fixture only: every IO operation fails without hardware IO.
 * This is never installed in a generated production project or flashed. */
#include "sx1278_instance.h"
#include "sx1278_device.h"
#include "ground_radio.h"
#include "project_resources.h"
#include "platform_critical.h"
#include "silverstar_assert.h"

uint32_t PlatformTime_Ms(void) { return 0U; }
uint64_t PlatformTime_Us(void) { return 0ULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint8_t PlatformGpio_IrqConsume(PlatformGpioId id) { (void)id; return 0U; }
PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t value)
{ (void)id; (void)value; return PLATFORM_IO_ERROR; }
PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout)
{ (void)id; (void)tx; (void)rx; (void)length; (void)timeout; return PLATFORM_IO_ERROR; }
SystemDeviceResult ProjectSx1278Resources_Get(uint8_t instance, ProjectSx1278Resources *r)
{
    if (instance != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *r = (ProjectSx1278Resources){PLATFORM_SPI_1,PLATFORM_GPIO_0,PLATFORM_GPIO_1,
        PLATFORM_GPIO_2,PLATFORM_TIME_1,PLATFORM_GPIO_3,PLATFORM_GPIO_4};
    return SYSTEM_DEVICE_OK;
}
void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    if (condition == 0U) { __builtin_trap(); }
}
int main(void)
{
    SystemDeviceInfo info;
    GroundRadioStats stats;
    Sx1278Result result = Sx1278_Init(0U);
    result = (result == Sx1278Result_Ok) ? Sx1278_Start(0U) : result;
    if (result == Sx1278Result_Ok) { result = Sx1278_Process(0U); }
    if (Sx1278TelemetryInstance_InfoGet(0U, &info) != SYSTEM_DEVICE_OK) { return 1; }
    if (GroundRadio_Init() != GROUND_RADIO_OK) { return 2; }
    GroundRadio_Process(); GroundRadio_StatsGet(&stats);
    if (Sx1278_Stop(0U) != Sx1278Result_Ok) { return 3; }
    return (int)result;
}
