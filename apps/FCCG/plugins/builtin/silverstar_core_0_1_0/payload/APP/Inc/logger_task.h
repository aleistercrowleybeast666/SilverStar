#ifndef __LOGGER_TASK_H
#define __LOGGER_TASK_H
#include <stdint.h>
#include "system_device_types.h"

typedef struct
{
    uint64_t max_iteration_us;
    uint64_t total_write_us;
    uint64_t max_write_us;
    uint64_t streaming_ready_us;
    uint32_t serialized_count;
    uint32_t iteration_count;
    uint32_t drain_count;
    uint32_t write_count;
    uint32_t append_failure_count;
    uint32_t flush_failure_count;
    uint32_t serialize_failure_count;
    uint32_t open_attempt_count;
    uint32_t open_failure_count;
    uint32_t session_count;
    uint32_t discarded_bytes;
    uint32_t close_failure_count;
    uint32_t snapshot_mission_id;
    uint32_t snapshot_commit_generation;
    uint32_t snapshot_sequence;
    uint32_t snapshot_calibration_generation;
    uint32_t snapshot_mag_calibration_set_hash;
    uint8_t snapshot_ready;
    uint8_t snapshot_base_instance;
    uint8_t final_status_write_failed;
    uint8_t io_fault;
} LoggerTaskDiagnostics;

SystemDeviceResult LoggerTask_DiagnosticsGet(LoggerTaskDiagnostics *diagnostics);
#endif /* __LOGGER_TASK_H */
