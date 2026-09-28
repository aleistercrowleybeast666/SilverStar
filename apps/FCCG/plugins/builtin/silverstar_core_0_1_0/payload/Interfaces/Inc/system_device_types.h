#ifndef __SYSTEM_DEVICE_TYPES_H
#define __SYSTEM_DEVICE_TYPES_H

#include <stdint.h>

#include "silverstar_compiler.h"

#define SYSTEM_WARN_UNUSED_RESULT SILVERSTAR_WARN_UNUSED_RESULT

typedef enum
{
    SYSTEM_DEVICE_OK = 0,
    SYSTEM_DEVICE_ALREADY_MATCHED,
    SYSTEM_DEVICE_NOT_READY,
    SYSTEM_DEVICE_OFFLINE,
    SYSTEM_DEVICE_UNSUPPORTED,
    SYSTEM_DEVICE_INVALID_ARGUMENT,
    SYSTEM_DEVICE_TIMEOUT,
    SYSTEM_DEVICE_IO_ERROR,
    SYSTEM_DEVICE_VERIFY_FAILED,
    SYSTEM_DEVICE_BAD_STATE,
    SYSTEM_DEVICE_VALUE_ADJUSTED,
    SYSTEM_DEVICE_INTERNAL_ERROR,
    SYSTEM_DEVICE_CONFIG_NO_ACTION,
    SYSTEM_DEVICE_CONFIG_DELEGATED,
    SYSTEM_DEVICE_NOT_EXECUTED,
    SYSTEM_DEVICE_BUSY,
    SYSTEM_DEVICE_NOT_PRESENT
} SystemDeviceResult;

typedef struct
{
    const char *device_name;
    const char *model_name;
    const char *driver_version;
    uint32_t capability_mask;
    uint32_t configuration_mask;
} SystemDeviceInfo;

typedef struct
{
    uint64_t last_sample_timestamp_us;
    uint64_t last_receive_timestamp_us;
    uint32_t sample_count;
    uint32_t error_count;
    uint32_t timeout_count;
    uint32_t checksum_error_count;
    uint32_t health_flags;
    uint8_t initialized;
    uint8_t started;
    uint8_t online;
    uint8_t healthy;
} SystemDeviceHealth;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint32_t supported_mask;
    uint32_t applied_mask;
    uint32_t matched_mask;
    uint32_t unsupported_optional_mask;
    uint32_t unsupported_required_mask;
    uint32_t verify_failed_mask;
    uint32_t delegated_mask;
    uint32_t failed_mask;
    uint32_t detail_code;
    uint32_t retry_count;
    uint8_t restart_performed;
    uint8_t persisted;
    uint8_t success;
} SystemDeviceConfigReport;

typedef struct
{
    uint32_t passed_mask;
    uint32_t failed_mask;
    uint32_t unsupported_mask;
    uint32_t detail_code;
} SystemDeviceSelfTestResult;

typedef enum
{
    SYSTEM_DEVICE_TRANSPORT_NONE = 0,
    SYSTEM_DEVICE_TRANSPORT_UART,
    SYSTEM_DEVICE_TRANSPORT_SPI
} SystemDeviceTransportType;

typedef enum
{
    SYSTEM_DEVICE_IO_OWNER_SELF = 0,
    SYSTEM_DEVICE_IO_OWNER_IMU,
    SYSTEM_DEVICE_IO_OWNER_GNSS,
    SYSTEM_DEVICE_IO_OWNER_TELEMETRY,
    SYSTEM_DEVICE_IO_OWNER_CONSOLE
} SystemDeviceIoOwner;

#define SYSTEM_DEVICE_IO_VALID_TRANSPORT       (1UL << 0)
#define SYSTEM_DEVICE_IO_VALID_RX_BYTES         (1UL << 1)
#define SYSTEM_DEVICE_IO_VALID_TX_BYTES         (1UL << 2)
#define SYSTEM_DEVICE_IO_VALID_RX_EVENTS        (1UL << 3)
#define SYSTEM_DEVICE_IO_VALID_RX_IDLE_EVENTS   (1UL << 4)
#define SYSTEM_DEVICE_IO_VALID_RX_TC_EVENTS     (1UL << 5)
#define SYSTEM_DEVICE_IO_VALID_RX_DISCARDED     (1UL << 6)
#define SYSTEM_DEVICE_IO_VALID_UART_OVERRUN     (1UL << 7)
#define SYSTEM_DEVICE_IO_VALID_UART_FRAMING     (1UL << 8)
#define SYSTEM_DEVICE_IO_VALID_UART_NOISE       (1UL << 9)
#define SYSTEM_DEVICE_IO_VALID_UART_PARITY      (1UL << 10)
#define SYSTEM_DEVICE_IO_VALID_DMA_ERRORS       (1UL << 11)
#define SYSTEM_DEVICE_IO_VALID_RX_RESTARTS      (1UL << 12)
#define SYSTEM_DEVICE_IO_VALID_RX_RESTART_FAILS (1UL << 13)
#define SYSTEM_DEVICE_IO_VALID_DISCONTINUITIES  (1UL << 14)
#define SYSTEM_DEVICE_IO_VALID_INTEGRITY_ERRORS (1UL << 15)
#define SYSTEM_DEVICE_IO_VALID_TIMEOUTS         (1UL << 16)
#define SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS (1UL << 17)
#define SYSTEM_DEVICE_IO_VALID_SPI_ERRORS       (1UL << 18)
#define SYSTEM_DEVICE_IO_VALID_SPI_TIMEOUTS     (1UL << 19)
#define SYSTEM_DEVICE_IO_VALID_BUSY_TIMEOUTS    (1UL << 20)
#define SYSTEM_DEVICE_IO_VALID_RX_ACTIVE        (1UL << 21)

typedef struct
{
    uint32_t supported_mask;
    uint32_t valid_mask;
    SystemDeviceTransportType transport_type;
    SystemDeviceIoOwner owner;
    uint32_t rx_bytes;
    uint32_t tx_bytes;
    uint32_t rx_event_count;
    uint32_t rx_idle_event_count;
    uint32_t rx_transfer_complete_count;
    uint32_t rx_discarded_bytes;
    uint32_t uart_overrun_error_count;
    uint32_t uart_framing_error_count;
    uint32_t uart_noise_error_count;
    uint32_t uart_parity_error_count;
    uint32_t dma_error_count;
    uint32_t rx_restart_count;
    uint32_t rx_restart_failure_count;
    uint32_t rx_discontinuity_count;
    uint32_t integrity_error_count;
    uint32_t timeout_count;
    uint32_t transport_error_count;
    uint32_t spi_error_count;
    uint32_t spi_timeout_count;
    uint32_t busy_timeout_count;
    uint8_t rx_active;
} SystemDeviceIoDiagnostics;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    float dt_s;
    float delta_theta_b_corrected[3];
    float delta_velocity_b_sculling_corrected[3];
#if defined(SYSTEM_BUILD_ESKF15_ENABLED) && (SYSTEM_BUILD_ESKF15_ENABLED != 0U)
    float body_gyro_radps[2][3];
    float body_accel_mps2[2][3];
    uint32_t quality_flags;
#endif
} SystemInertialIncrement;

#endif /* __SYSTEM_DEVICE_TYPES_H */
