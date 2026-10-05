#include "sensor_register_bus.h"

#include <stddef.h>

SensorBusResult SensorRegister_Read(const SensorRegisterBus *bus,
    uint16_t reg, uint8_t *data, uint16_t length)
{
    if ((bus == NULL) || (bus->read == NULL) || (data == NULL) ||
        (length == 0U) || (length > SENSOR_REGISTER_TRANSFER_MAX))
    {
        return SENSOR_BUS_INVALID_ARGUMENT;
    }
    return bus->read(bus->context, reg, data, length,
                     SENSOR_REGISTER_TIMEOUT_US);
}

SensorBusResult SensorRegister_Write(const SensorRegisterBus *bus,
    uint16_t reg, const uint8_t *data, uint16_t length)
{
    if ((bus == NULL) || (bus->write == NULL) || (data == NULL) ||
        (length == 0U) || (length > SENSOR_REGISTER_TRANSFER_MAX))
    {
        return SENSOR_BUS_INVALID_ARGUMENT;
    }
    return bus->write(bus->context, reg, data, length,
                      SENSOR_REGISTER_TIMEOUT_US);
}
