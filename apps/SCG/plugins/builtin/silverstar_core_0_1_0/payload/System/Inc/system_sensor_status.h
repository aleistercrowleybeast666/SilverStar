#ifndef __SYSTEM_SENSOR_STATUS_H
#define __SYSTEM_SENSOR_STATUS_H

#include <stdint.h>

#include "system_device_types.h"
#include "silverstar_sensor_id.h"

#define SYSTEM_SENSOR_STATUS_MAX_ENTRIES 16U

typedef SilverStarSensorId SystemSensorId;

#define SYSTEM_SENSOR_STATUS_REGISTERED         (1U << 0)
#define SYSTEM_SENSOR_STATUS_INITIALIZED        (1U << 1)
#define SYSTEM_SENSOR_STATUS_ONLINE             (1U << 2)
#define SYSTEM_SENSOR_STATUS_HEALTHY            (1U << 3)
#define SYSTEM_SENSOR_STATUS_DATA_VALID         (1U << 4)
#define SYSTEM_SENSOR_STATUS_CALIBRATION_OK     (1U << 5)
#define SYSTEM_SENSOR_STATUS_ALIGNMENT_USED    (1U << 6)
#define SYSTEM_SENSOR_STATUS_REQUIRED_FOR_START (1U << 7)

typedef enum
{
    SYSTEM_SENSOR_DETAIL_NONE = 0x00U,
    SYSTEM_SENSOR_DETAIL_NOT_REGISTERED = 0x01U,
    SYSTEM_SENSOR_DETAIL_INIT_FAILED = 0x02U,
    SYSTEM_SENSOR_DETAIL_OFFLINE = 0x03U,
    SYSTEM_SENSOR_DETAIL_UNHEALTHY = 0x04U,
    SYSTEM_SENSOR_DETAIL_NO_VALID_DATA = 0x05U,
    SYSTEM_SENSOR_DETAIL_CALIBRATION_REQUIRED = 0x06U,
    SYSTEM_SENSOR_DETAIL_ALIGNMENT_INPUT_INVALID = 0x07U,
    SYSTEM_SENSOR_DETAIL_IO_ERROR = 0x08U,
    SYSTEM_SENSOR_DETAIL_CONFIG_ERROR = 0x09U,
    SYSTEM_SENSOR_DETAIL_UNSUPPORTED = 0x0AU,
    SYSTEM_SENSOR_DETAIL_OTHER = 0xFFU
} SystemSensorDetailCode;

typedef struct
{
    uint8_t sensor_id;
    uint8_t instance_id;
    uint8_t status_flags;
    uint8_t detail_code;
} SystemSensorStatus;

typedef struct
{
    uint32_t sequence;
    uint8_t snapshot_id;
    uint8_t total;
    uint8_t alignment_state;
    uint8_t valid;
} SystemSensorStatusSnapshotInfo;

void SystemSensorStatus_Reset(void);
uint8_t SystemSensorStatus_CountGet(void);
SystemDeviceResult SystemSensorStatus_Get(uint8_t index,
                                          SystemSensorStatus *status);
uint8_t SystemSensorStatus_SummaryFlagsGet(void);
SystemDeviceResult SystemSensorStatus_SnapshotCapture(
    uint8_t alignment_state);
SystemDeviceResult SystemSensorStatus_SnapshotInfoGet(
    SystemSensorStatusSnapshotInfo *info);
SystemDeviceResult SystemSensorStatus_SnapshotGet(
    uint8_t index,
    SystemSensorStatus *status);

#endif /* __SYSTEM_SENSOR_STATUS_H */
