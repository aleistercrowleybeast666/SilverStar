#ifndef __PLATFORM_I2C_DEADLINE_H
#define __PLATFORM_I2C_DEADLINE_H

#include <stdint.h>

/* Per-handle blocking transaction context, never a global callback registry. */
typedef struct
{
    uint32_t start_cycles;
    uint32_t budget_cycles;
    uint32_t active;
} PlatformI2cDeadline;

typedef enum
{
    PlatformI2cDeadlineResult_Ok = 0U,
    PlatformI2cDeadlineResult_InvalidArgument,
    PlatformI2cDeadlineResult_Unavailable
} PlatformI2cDeadlineResult;

PlatformI2cDeadlineResult PlatformI2cDeadline_Start(
    PlatformI2cDeadline *deadline, uint32_t timeout_ms);
uint8_t PlatformI2cDeadline_Expired(const PlatformI2cDeadline *deadline);

#endif /* __PLATFORM_I2C_DEADLINE_H */
