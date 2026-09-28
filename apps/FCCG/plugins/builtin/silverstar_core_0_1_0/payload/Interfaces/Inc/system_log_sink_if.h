#ifndef __SYSTEM_LOG_SINK_IF_H
#define __SYSTEM_LOG_SINK_IF_H

#include "system_device_types.h"

typedef struct
{
    uint32_t profile_id;
    uint8_t version_major;
    uint8_t version_minor;
    uint8_t version_patch;
    uint8_t reserved;
} SystemLogSessionInfo;

typedef struct
{
    uint64_t bytes_written;
    uint64_t last_write_timestamp_us;
    uint64_t last_flush_timestamp_us;
    uint32_t write_count;
    uint32_t flush_count;
    uint32_t error_count;
    uint8_t initialized;
    uint8_t session_active;
    uint8_t healthy;
} SystemLogSinkHealth;

const char *SystemLogSink_NameGet(void);
SystemDeviceResult SystemLogSink_Init(void);
SystemDeviceResult SystemLogSink_SessionBegin(
    const SystemLogSessionInfo *session);
SystemDeviceResult SystemLogSink_Write(const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length);
SystemDeviceResult SystemLogSink_Flush(void);
SystemDeviceResult SystemLogSink_SessionEnd(void);
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health);

#endif /* __SYSTEM_LOG_SINK_IF_H */
