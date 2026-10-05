#ifndef __MMC5983MA_CORE_H
#define __MMC5983MA_CORE_H

#include <stdint.h>

#include "system_magnetometer_if.h"

typedef enum
{
    Mmc5983maBusOk = 0,
    Mmc5983maBusError
} Mmc5983maBusResult;

typedef Mmc5983maBusResult (*Mmc5983maReadOperation)(void *bus,
    uint8_t register_address, uint8_t *bytes, uint8_t length);
typedef Mmc5983maBusResult (*Mmc5983maWriteOperation)(void *bus,
    uint8_t register_address, uint8_t value);

typedef struct
{
    void *bus;
    Mmc5983maReadOperation read;
    Mmc5983maWriteOperation write;
} Mmc5983maPort;

typedef enum
{
    Mmc5983maStateProbe = 0,
    Mmc5983maStateReadConfig,
    Mmc5983maStateApplyConfig,
    Mmc5983maStateVerifyConfig,
    Mmc5983maStateSet,
    Mmc5983maStateTriggerMag,
    Mmc5983maStatePollMag,
    Mmc5983maStateReadMag,
    Mmc5983maStateTriggerTemp,
    Mmc5983maStatePollTemp,
    Mmc5983maStateReadTemp,
    Mmc5983maStateWaitPeriod,
    Mmc5983maStateFailed
} Mmc5983maState;

typedef enum
{
    Mmc5983maStepPending = 0,
    Mmc5983maStepSampleReady,
    Mmc5983maStepNotPresent,
    Mmc5983maStepBusError,
    Mmc5983maStepVerifyFailed,
    Mmc5983maStepMeasurementTimeout
} Mmc5983maStepResult;

typedef struct
{
    Mmc5983maPort port;
    SystemMagnetometerSample sample;
    Mmc5983maState state;
    uint64_t operation_started_us;
    uint64_t last_sample_us;
    uint32_t error_count;
    uint32_t sequence;
    uint8_t config_index;
} Mmc5983maContext;

void Mmc5983ma_Init(Mmc5983maContext *context, const Mmc5983maPort *port);
Mmc5983maStepResult Mmc5983ma_Step(Mmc5983maContext *context,
    uint64_t now_us);

#endif /* __MMC5983MA_CORE_H */
