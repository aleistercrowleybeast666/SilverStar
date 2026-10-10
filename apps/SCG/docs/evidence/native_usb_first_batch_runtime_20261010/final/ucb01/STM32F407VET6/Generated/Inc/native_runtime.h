#ifndef __NATIVE_RUNTIME_H
#define __NATIVE_RUNTIME_H
#include <stdint.h>
typedef enum {
    NativeRuntimeResult_Ok,
    NativeRuntimeResult_NotReady,
    NativeRuntimeResult_ClockFailure,
    NativeRuntimeResult_PlatformFailure,
    NativeRuntimeResult_RadioFailure,
    NativeRuntimeResult_PcFailure,
    NativeRuntimeResult_RetirementFailure
} NativeRuntimeResult;
NativeRuntimeResult NativeRuntime_Init(void);
NativeRuntimeResult NativeRuntime_Process(void);
uint8_t NativeRuntime_ReadyGet(void);
void NativeRuntime_TransportFaultRecord(void);
#endif /* __NATIVE_RUNTIME_H */
