#ifndef __LOGGER_BUS_H
#define __LOGGER_BUS_H
/* Test-only storage boundary. Real record layout comes from the SSLOG owner. */
#include "sslog_protocol.h"
typedef enum { LOGGER_BUS_RESULT_OK=0, LOGGER_BUS_RESULT_FULL=2 } LoggerBusResult;
LoggerBusResult LoggerBus_NavigationOperationPush(uint64_t timestamp_us,
    const FlightLogNavigationOperationPartRecord *record);
#endif
