#ifndef __SYSTEM_TASK_STACK_H
#define __SYSTEM_TASK_STACK_H

#include <stdint.h>

#include "system_device_types.h"

typedef enum
{
    SYSTEM_TASK_STACK_DEVICE = 0U,
    SYSTEM_TASK_STACK_INS,
    SYSTEM_TASK_STACK_ESTIMATOR,
    SYSTEM_TASK_STACK_FLIGHT,
    SYSTEM_TASK_STACK_LOGGER,
    SYSTEM_TASK_STACK_SERIAL,
    SYSTEM_TASK_STACK_RADIO,
    SYSTEM_TASK_STACK_COUNT
} SystemTaskStackId;

typedef struct
{
    uint32_t allocation_words;
    uint32_t high_water_mark_words;
} SystemTaskStackEntry;

typedef struct
{
    SystemTaskStackEntry task[SYSTEM_TASK_STACK_COUNT];
    uint32_t valid_mask;
} SystemTaskStackSnapshot;

/* Uses only registered handles, trusted names and a cached normal-task HWM.
 * Never dereferences a potentially damaged TCB or the supplied name. */
void SystemTaskStack_OverflowContextSet(uintptr_t task, uintptr_t task_name);

SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemTaskStack_SnapshotGet(
    SystemTaskStackSnapshot *snapshot);

#endif /* __SYSTEM_TASK_STACK_H */
