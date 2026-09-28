#ifndef __HOST_PLATFORM_MOCK_H
#define __HOST_PLATFORM_MOCK_H

#include <stdint.h>

#include "platform_adc.h"
#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_uart.h"

void HostPlatformMock_Reset(void);
void HostPlatformMock_TimeSetUs(uint64_t timestamp_us);
void HostPlatformMock_TimeAdvanceUs(uint64_t delta_us);
void HostPlatformMock_UartInitResultSet(PlatformUartId id,
                                        PlatformResult result);
void HostPlatformMock_UartWriteResultSet(PlatformUartId id,
                                         PlatformResult result);
void HostPlatformMock_Jy901bEnable(PlatformUartId id, uint8_t enabled,
    uint8_t ignore_writes);
uint16_t HostPlatformMock_UartRxInject(PlatformUartId id,
                                       const uint8_t *data,
                                       uint16_t length);
uint16_t HostPlatformMock_UartTxTake(PlatformUartId id,
                                     uint8_t *data,
                                     uint16_t capacity);
void HostPlatformMock_UartDiscontinuityRecord(PlatformUartId id);
void HostPlatformMock_AdcSet(PlatformResult result, uint32_t sample);
void HostPlatformMock_GpioSet(PlatformGpioId id, uint8_t logical_high);
void HostPlatformMock_GpioIrqRaise(PlatformGpioId id);
void HostPlatformMock_SpiResultSet(PlatformResult result);

#endif /* __HOST_PLATFORM_MOCK_H */
