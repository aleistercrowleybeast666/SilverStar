#ifndef __DIAGNOSTIC_LOG_H
#define __DIAGNOSTIC_LOG_H

#include <stdint.h>

typedef struct
{
    uint64_t last_emission_us;
} DiagnosticLogPeriodicState;

void DiagnosticLog_StatsProcess(DiagnosticLogPeriodicState *state,
                                uint64_t now_us);
void DiagnosticLog_TelemetryProcess(DiagnosticLogPeriodicState *state,
                                    uint64_t now_us);

#endif /* __DIAGNOSTIC_LOG_H */
