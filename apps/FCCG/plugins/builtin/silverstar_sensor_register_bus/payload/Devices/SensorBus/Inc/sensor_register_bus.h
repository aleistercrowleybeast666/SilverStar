#ifndef __SENSOR_REGISTER_BUS_H
#define __SENSOR_REGISTER_BUS_H

#include <stdint.h>

#define SENSOR_REGISTER_TRANSFER_MAX 64U
#define SENSOR_REGISTER_TIMEOUT_US 2000U

typedef enum
{
    SENSOR_BUS_OK = 0,
    SENSOR_BUS_INVALID_ARGUMENT,
    SENSOR_BUS_TIMEOUT,
    SENSOR_BUS_IO_ERROR
} SensorBusResult;

typedef enum
{
    SENSOR_BUS_I2C = 0,
    SENSOR_BUS_SPI
} SensorBusKind;

/* Register callbacks retain chip-select for the entire transaction. The
 * implementation owns SPI read bits/dummy bytes or the 7-bit I2C address.
 * Every operation must complete within timeout_us; it is never called in ISR. */
typedef SensorBusResult (*SensorRegisterRead)(void *context, uint16_t reg,
    uint8_t *data, uint16_t length, uint32_t timeout_us);
typedef SensorBusResult (*SensorRegisterWrite)(void *context, uint16_t reg,
    const uint8_t *data, uint16_t length, uint32_t timeout_us);

typedef struct
{
    void *context;
    SensorRegisterRead read;
    SensorRegisterWrite write;
    SensorBusKind kind;
} SensorRegisterBus;

SensorBusResult SensorRegister_Read(const SensorRegisterBus *bus,
    uint16_t reg, uint8_t *data, uint16_t length);
SensorBusResult SensorRegister_Write(const SensorRegisterBus *bus,
    uint16_t reg, const uint8_t *data, uint16_t length);

#endif /* __SENSOR_REGISTER_BUS_H */
