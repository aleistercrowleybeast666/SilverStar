/* Real HAL buffers/assertions; only terminal trap intercepted on Host. */
#include <assert.h>
#include <setjmp.h>
#include <string.h>
#include "hw.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "sx1280-hal.h"
static jmp_buf trap_return;
static unsigned transfers, gpio_writes, iram_bytes;
static uint16_t next_iram = IRAM_START_ADDRESS;
static uint8_t iram_mode;
static _Noreturn void Test_Trap(void) { longjmp(trap_return, 1); }
#define __builtin_trap() Test_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "sx1280-hal.c"

void GpioWrite(uint8_t instance, PlatformGpioId id, uint32_t value)
{ assert(instance < 2U); (void)id; (void)value; gpio_writes++; }
uint8_t GpioRead(uint8_t instance, PlatformGpioId id) { (void)instance; (void)id; return 0U; }
uint8_t GpioWaitLow(uint8_t instance, PlatformGpioId id, uint32_t timeout)
{ (void)instance; (void)id; (void)timeout; return 1U; }
PlatformGpioId Sx1281Bus_NssGet(uint8_t i) { return (PlatformGpioId)(i + 1U); }
PlatformGpioId Sx1281Bus_ResetGet(uint8_t i) { return (PlatformGpioId)(i + 3U); }
PlatformGpioId Sx1281Bus_BusyGet(uint8_t i) { return (PlatformGpioId)(i + 5U); }
PlatformGpioId Sx1281Bus_Dio1Get(uint8_t i) { return (PlatformGpioId)(i + 7U); }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
void PlatformTime_DelayMs(uint32_t delay) { (void)delay; }
void SpiIn(uint8_t i, const uint8_t *tx, uint16_t size)
{
    unsigned j; assert(i < 2U && size <= 260U); transfers++;
    if (iram_mode)
    {
        assert(tx[0] == RADIO_WRITE_REGISTER);
        assert(((uint16_t)tx[1] << 8U | tx[2]) == next_iram);
        for (j = 3U; j < size; j++) { assert(tx[j] == 0U); }
        iram_bytes += size - 3U; next_iram = (uint16_t)(next_iram + size - 3U);
    }
}
void SpiInOut(uint8_t i, const uint8_t *tx, uint8_t *rx, uint16_t size)
{ assert(i < 2U && size <= 260U); (void)tx; memset(rx, 0x5A, size); transfers++; }
int main(int argc, char **argv)
{
    uint8_t data[260]; memset(data, 0xA5, sizeof(data)); assert(argc == 2);
    if (strcmp(argv[1], "normal") == 0)
    {
        SX1280HalWriteBuffer(0U,0U,data,255U);
        SX1280HalReadBuffer(1U,0U,data,255U); assert(data[254] == 0x5AU);
        SX1280HalWriteRegisters(0U,0x100U,data,257U);
        SX1280HalReadRegisters(1U,0x100U,data,256U); assert(data[255] == 0x5AU);
        SX1280HalWriteCommand(0U,RADIO_SET_PACKETTYPE,NULL,0U);
        SX1280HalReadCommand(1U,RADIO_GET_PACKETTYPE,NULL,0U);
        SX1280HalWriteBuffer(0U,0U,NULL,0U);
        SX1280HalReadBuffer(1U,0U,NULL,0U);
        assert(transfers == 8U); return 0;
    }
    if (strcmp(argv[1], "iram") == 0)
    { iram_mode = 1U; SX1280HalClearInstructionRam(0U); assert(iram_bytes == IRAM_SIZE); assert(transfers == (IRAM_SIZE + 256U) / 257U); return 0; }
    if (setjmp(trap_return) == 0)
    {
        if (strcmp(argv[1], "size") == 0) { SX1280HalWriteCommand(0U,RADIO_SET_PACKETTYPE,data,260U); }
        else if (strcmp(argv[1], "register") == 0) { SX1280HalReadRegisters(0U,0U,data,257U); }
        else if (strcmp(argv[1], "null") == 0) { SX1280HalReadBuffer(0U,0U,NULL,1U); }
        else if (strcmp(argv[1], "index") == 0) { SX1280HalWriteBuffer(2U,0U,data,1U); }
        else { assert(0 && "unknown scenario"); }
        assert(0 && "missing safety trap");
    }
    assert(transfers == 0U && gpio_writes == 0U);
    return 0;
}
