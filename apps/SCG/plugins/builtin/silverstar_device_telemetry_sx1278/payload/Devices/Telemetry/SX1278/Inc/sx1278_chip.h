#ifndef __SX1278_CHIP_H
#define __SX1278_CHIP_H

#include "platform_gpio.h"
#include "platform_spi.h"

#define SX1278_PACKET_CAPACITY 61U

typedef enum
{
    Sx1278Result_Ok = 0, Sx1278Result_Busy, Sx1278Result_Empty,
    Sx1278Result_Invalid, Sx1278Result_Offline, Sx1278Result_Timeout,
    Sx1278Result_Io, Sx1278Result_NotPresent
} Sx1278Result;

/* Chip bus contains no module RF-switch or reset policy and no callback. */
typedef struct
{
    PlatformSpiId spi;
    PlatformGpioId nss;
} Sx1278ChipBus;

Sx1278Result Sx1278Chip_Read(const Sx1278ChipBus *bus, uint8_t address,
    uint8_t *data, uint8_t length);
Sx1278Result Sx1278Chip_Write(const Sx1278ChipBus *bus, uint8_t address,
    const uint8_t *data, uint8_t length);
Sx1278Result Sx1278Chip_RegisterWrite(const Sx1278ChipBus *bus,
    uint8_t address, uint8_t value);
Sx1278Result Sx1278Chip_ModeSet(const Sx1278ChipBus *bus, uint8_t mode);
Sx1278Result Sx1278Chip_Configure(const Sx1278ChipBus *bus);

#endif /* __SX1278_CHIP_H */
