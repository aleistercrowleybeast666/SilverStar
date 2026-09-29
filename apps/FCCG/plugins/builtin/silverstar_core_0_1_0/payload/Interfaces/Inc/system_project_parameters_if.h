#ifndef __SYSTEM_PROJECT_PARAMETERS_IF_H
#define __SYSTEM_PROJECT_PARAMETERS_IF_H

#include <stdint.h>

typedef enum
{
    SystemProjectParameterResult_Ok = 0,
    SystemProjectParameterResult_InvalidArgument,
    SystemProjectParameterResult_NotFound
} SystemProjectParameterResult;

typedef enum
{
    SystemProjectParameterKind_Float32 = 1,
    SystemProjectParameterKind_Int32
} SystemProjectParameterKind;

typedef struct
{
    uint32_t key_hash;
    uint32_t value_bits;
    SystemProjectParameterKind kind;
} SystemProjectParameter;

uint16_t SystemProjectParameter_CountGet(void);
SystemProjectParameterResult SystemProjectParameter_Get(
    uint16_t index, SystemProjectParameter *parameter);

#endif /* __SYSTEM_PROJECT_PARAMETERS_IF_H */
