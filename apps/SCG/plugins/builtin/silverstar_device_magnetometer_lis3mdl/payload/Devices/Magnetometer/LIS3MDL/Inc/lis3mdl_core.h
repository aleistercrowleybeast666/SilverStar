#ifndef __LIS3MDL_CORE_H
#define __LIS3MDL_CORE_H

#include <stdint.h>

#include "system_magnetometer_if.h"

typedef enum
{
    Lis3mdlBusOk = 0,
    Lis3mdlBusError
} Lis3mdlBusResult;

typedef Lis3mdlBusResult (*Lis3mdlReadOperation)(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length);
typedef Lis3mdlBusResult (*Lis3mdlWriteOperation)(void *bus,
    uint8_t register_address, uint8_t value);

typedef struct
{
    void *bus;
    Lis3mdlReadOperation read;
    Lis3mdlWriteOperation write;
} Lis3mdlPort;

typedef enum
{
    Lis3mdlStateProbe = 0,
    Lis3mdlStateReadConfig,
    Lis3mdlStateApplyConfig,
    Lis3mdlStateVerifyConfig,
    Lis3mdlStatePollStatus,
    Lis3mdlStateReadSample,
    Lis3mdlStateFailed
} Lis3mdlState;

typedef enum
{
    Lis3mdlStepPending = 0,
    Lis3mdlStepSampleReady,
    Lis3mdlStepNotPresent,
    Lis3mdlStepBusError,
    Lis3mdlStepVerifyFailed,
    Lis3mdlStepInvalidSample
} Lis3mdlStepResult;

typedef struct
{
    Lis3mdlPort port;
    SystemMagnetometerSample sample;
    Lis3mdlState state;
    uint64_t last_sample_us;
    uint32_t error_count;
    uint32_t sequence;
    uint8_t config_index;
} Lis3mdlContext;

void Lis3mdl_Init(Lis3mdlContext *context, const Lis3mdlPort *port);
Lis3mdlStepResult Lis3mdl_Step(Lis3mdlContext *context, uint64_t now_us);

#endif /* __LIS3MDL_CORE_H */
