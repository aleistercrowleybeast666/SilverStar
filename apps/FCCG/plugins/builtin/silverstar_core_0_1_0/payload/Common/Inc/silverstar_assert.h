#ifndef __SILVERSTAR_ASSERT_H
#define __SILVERSTAR_ASSERT_H

#include <stdint.h>

#include "silverstar_compiler.h"

typedef enum
{
    SILVERSTAR_ASSERT_MODULE_APP = 1U,
    SILVERSTAR_ASSERT_MODULE_ALGORITHM,
    SILVERSTAR_ASSERT_MODULE_BOARD,
    SILVERSTAR_ASSERT_MODULE_COMMON,
    SILVERSTAR_ASSERT_MODULE_DEVICE,
    SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
    SILVERSTAR_ASSERT_MODULE_GENERATED,
    SILVERSTAR_ASSERT_MODULE_INTERFACE,
    SILVERSTAR_ASSERT_MODULE_MODULES,
    SILVERSTAR_ASSERT_MODULE_PLATFORM,
    SILVERSTAR_ASSERT_MODULE_PROTOCOL,
    SILVERSTAR_ASSERT_MODULE_SYSTEM,
    SILVERSTAR_ASSERT_MODULE_OS
} SilverStarAssertModuleId;

typedef enum
{
    SILVERSTAR_ASSERT_REASON_NULL_POINTER = 1U,
    SILVERSTAR_ASSERT_REASON_ENUM_RANGE,
    SILVERSTAR_ASSERT_REASON_INDEX_RANGE,
    SILVERSTAR_ASSERT_REASON_LENGTH_RANGE,
    SILVERSTAR_ASSERT_REASON_STATE_INVARIANT,
    SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT,
    SILVERSTAR_ASSERT_REASON_TIME_INVARIANT,
    SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE,
    SILVERSTAR_ASSERT_REASON_LOOP_BOUND,
    SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY,
    SILVERSTAR_ASSERT_REASON_POSTCONDITION
} SilverStarAssertReasonId;

#define SILVERSTAR_FAULT_TASK_NAME_SIZE 16U
#define SILVERSTAR_FAULT_TASK_UNKNOWN UINT32_MAX

typedef enum
{
    SILVERSTAR_FAULT_ASSERT = 0U,
    SILVERSTAR_FAULT_STACK_OVERFLOW
} SilverStarFaultType;

typedef struct
{
    const char *file_name;
    uint64_t timestamp_us;
    uint32_t line;
    uint32_t sequence;
    SilverStarAssertModuleId module_id;
    SilverStarAssertReasonId reason_id;
    SilverStarFaultType fault_type;
    uintptr_t task_handle;
    uintptr_t task_name_address;
    uint32_t task_id;
    uint32_t system_state;
    uint32_t high_water_mark_words;
    char task_name[SILVERSTAR_FAULT_TASK_NAME_SIZE];
    uint8_t high_water_mark_valid;
    uint8_t timestamp_valid;
    uint8_t active;
} SilverStarAssertFaultRecord;

#define SILVERSTAR_ASSERT(expression_, module_id_, reason_id_) \
    SilverStarAssert_Check((uint8_t)((expression_) != 0), (module_id_), \
                           __FILE__, (uint32_t)__LINE__, (reason_id_))

/* One typed-object contract expands to two runtime assertions: non-null and
 * natural alignment.  The Power of Ten checker deliberately counts both. */
#define SILVERSTAR_ASSERT_OBJECT(object_, type_, module_id_) \
    SilverStarAssert_ObjectCheck((object_), (uint32_t)_Alignof(type_), \
                                 (module_id_), __FILE__, \
                                 (uint32_t)__LINE__)

void SilverStarAssert_Check(uint8_t condition,
                            SilverStarAssertModuleId module_id,
                            const char *file_name,
                            uint32_t line,
                            SilverStarAssertReasonId reason_id);
void SilverStarAssert_ObjectCheck(const volatile void *object,
                                  uint32_t alignment,
                                  SilverStarAssertModuleId module_id,
                                  const char *file_name,
                                  uint32_t line);
SILVERSTAR_NORETURN void SilverStarAssert_Fail(
    SilverStarAssertModuleId module_id,
    const char *file_name,
    uint32_t line,
    SilverStarAssertReasonId reason_id);
uint8_t SilverStarAssert_FaultedGet(void);
void SilverStarAssert_StackOverflowContextSet(
    uintptr_t task_handle, uintptr_t task_name_address,
    uint32_t task_id, const char *stable_name, uint32_t system_state,
    uint32_t high_water_mark_words, uint8_t high_water_mark_valid);
SILVERSTAR_WARN_UNUSED_RESULT uint8_t SilverStarAssert_FaultRecordGet(
    SilverStarAssertFaultRecord *record);

#endif /* __SILVERSTAR_ASSERT_H */
