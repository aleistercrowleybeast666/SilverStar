#ifndef __JY901B_DEVICE_H
#define __JY901B_DEVICE_H

#include <stdint.h>

#define IMU_FRAME_HEADER                  0x55U
#define IMU_FRAME_LEN                     11U

#define IMU_CFG_FRAME_LEN                 5U
#define IMU_REG_SAVE                      0x00U
#define IMU_REG_CALSW                     0x01U
#define IMU_REG_RSW                       0x02U
#define IMU_REG_RRATE                     0x03U
#define IMU_REG_BAUD                      0x04U
#define IMU_REG_GYRORANGE                 0x20U
#define IMU_REG_ACCRANGE                  0x21U
#define IMU_REG_ORIENT                    0x23U
#define IMU_REG_BANDWIDTH                 0x1FU
#define IMU_REG_AXIS6                     0x24U
#define IMU_REG_FILTK                     0x25U
#define IMU_REG_KEY                       0x69U
#define IMU_REG_READADDR                  0x27U
#define IMU_REG_ACCFILT                   0x2AU
#define IMU_REG_READ_RESPONSE             0x5FU

#define IMU_KEY_UNLOCK                    0xB588U
#define IMU_CALSW_Z_AXIS_ZERO             0x0004U

#define IMU_BAUD_4800_VALUE               0x0001U
#define IMU_BAUD_9600_VALUE               0x0002U
#define IMU_BAUD_19200_VALUE              0x0003U
#define IMU_BAUD_38400_VALUE              0x0004U
#define IMU_BAUD_57600_VALUE              0x0005U
#define IMU_BAUD_115200_VALUE             0x0006U
#define IMU_BAUD_230400_VALUE             0x0007U

#define IMU_RRATE_0_2HZ_VALUE             0x0001U
#define IMU_RRATE_0_5HZ_VALUE             0x0002U
#define IMU_RRATE_1HZ_VALUE               0x0003U
#define IMU_RRATE_2HZ_VALUE               0x0004U
#define IMU_RRATE_5HZ_VALUE               0x0005U
#define IMU_RRATE_10HZ_VALUE              0x0006U
#define IMU_RRATE_20HZ_VALUE              0x0007U
#define IMU_RRATE_50HZ_VALUE              0x0008U
#define IMU_RRATE_100HZ_VALUE             0x0009U
#define IMU_RRATE_200HZ_VALUE             0x000BU
#define IMU_RRATE_SINGLE_0C_VALUE         0x000CU
#define IMU_RRATE_SINGLE_VALUE            0x0010U
#define IMU_RRATE_NONE_VALUE              0x000DU

#define IMU_BANDWIDTH_256HZ_VALUE         0x0000U
#define IMU_BANDWIDTH_188HZ_VALUE         0x0001U
#define IMU_BANDWIDTH_98HZ_VALUE          0x0002U
#define IMU_BANDWIDTH_42HZ_VALUE          0x0003U
#define IMU_BANDWIDTH_20HZ_VALUE          0x0004U
#define IMU_BANDWIDTH_10HZ_VALUE          0x0005U
#define IMU_BANDWIDTH_5HZ_VALUE           0x0006U

#define IMU_GYRO_RANGE_200DPS_VALUE       0x0000U
#define IMU_GYRO_RANGE_500DPS_VALUE       0x0001U
#define IMU_GYRO_RANGE_1000DPS_VALUE      0x0002U
#define IMU_GYRO_RANGE_2000DPS_VALUE      0x0003U

#define IMU_ACCEL_RANGE_2G_VALUE           0x0000U
#define IMU_ACCEL_RANGE_4G_VALUE           0x0001U
#define IMU_ACCEL_RANGE_8G_VALUE           0x0002U
#define IMU_ACCEL_RANGE_16G_VALUE          0x0003U

#define IMU_ALGORITHM_9_AXIS_VALUE         0x0000U
#define IMU_ALGORITHM_6_AXIS_VALUE         0x0001U

typedef enum
{
    IMU_OK = 0,
    IMU_NULL,
    IMU_UART_TX_ERROR,
    IMU_UART_RX_ERROR,
    IMU_UART_INIT_ERROR,
    IMU_RESP_INVALID,
    IMU_RESP_TIMEOUT
} IMUState;

typedef enum
{
    Baudrate_4800   = 0x0001U,
    Baudrate_9600   = 0x0002U,
    Baudrate_19200  = 0x0003U,
    Baudrate_38400  = 0x0004U,
    Baudrate_57600  = 0x0005U,
    Baudrate_115200 = 0x0006U,
    Baudrate_230400 = 0x0007U,
    Baudrate_460800 = 0x0008U
} IMUBaudrate;

typedef enum
{
    OutputRate_0_2Hz    = 0x0001U,
    OutputRate_0_5Hz    = 0x0002U,
    OutputRate_1Hz      = 0x0003U,
    OutputRate_2Hz      = 0x0004U,
    OutputRate_5Hz      = 0x0005U,
    OutputRate_10Hz     = 0x0006U,
    OutputRate_20Hz     = 0x0007U,
    OutputRate_50Hz     = 0x0008U,
    OutputRate_100Hz    = 0x0009U,
    OutputRate_200Hz    = 0x000BU,
    OutputRate_Single0C = 0x000CU,
    OutputRate_None     = 0x000DU,
    OutputRate_Single   = 0x0010U
} IMUOutputRate;

typedef enum
{
    Bandwidth_256Hz = 0x0000U,
    Bandwidth_188Hz = 0x0001U,
    Bandwidth_98Hz  = 0x0002U,
    Bandwidth_42Hz  = 0x0003U,
    Bandwidth_20Hz  = 0x0004U,
    Bandwidth_10Hz  = 0x0005U,
    Bandwidth_5Hz   = 0x0006U
} IMUBandwidth;

typedef enum
{
    Algorithm_9Axis = 0x0000U,
    Algorithm_6Axis = 0x0001U
} IMUAlgorithm;

typedef enum
{
    GyroRange_200Dps  = 0x0000U,
    GyroRange_500Dps  = 0x0001U,
    GyroRange_1000Dps = 0x0002U,
    GyroRange_2000Dps = 0x0003U
} IMUGyroRange;

typedef enum
{
    AccelRange_2G  = 0x0000U,
    AccelRange_4G  = 0x0001U,
    AccelRange_8G  = 0x0002U,
    AccelRange_16G = 0x0003U
} IMUAccelRange;

typedef enum
{
    IMUFrameNone           = 0x00,
    IMUFrameAcc            = 0x51,
    IMUFrameGyro           = 0x52,
    IMUFrameEuler          = 0x53,
    IMUFrameMag            = 0x54,
    IMUFramePressureHeight = 0x56,
    IMUFrameQuaternion     = 0x59
} IMUFrameType;

#define IMU_CONFIG_VALID_BAUD          (1U << 0)
#define IMU_CONFIG_VALID_RATE          (1U << 1)
#define IMU_CONFIG_VALID_BANDWIDTH     (1U << 2)
#define IMU_CONFIG_VALID_ALGORITHM     (1U << 3)
#define IMU_CONFIG_VALID_FUSION_FILTER (1U << 4)
#define IMU_CONFIG_VALID_ACCEL_FILTER  (1U << 5)
#define IMU_CONFIG_VALID_RETURN_CONTENT (1U << 6)
#define IMU_CONFIG_VALID_GYRO_RANGE    (1U << 7)
#define IMU_CONFIG_VALID_ACCEL_RANGE   (1U << 8)
#define IMU_CONFIG_VALID_ORIENTATION   (1U << 9)
#define IMU_CONFIG_VALID_ALL           0x03FFU

typedef struct
{
    /* JY901B 原始量，可直接用于天地协议或离线标定。 */
    int16_t AccRaw[3];
    int16_t GyroRaw[3];
    int16_t EulerRaw[3];
    int16_t MagRaw[3];
    int32_t PressureRawPa;
    int32_t HeightRawCm;

    /* Raw JY901B 0x59 Q0/Q1/Q2/Q3 in signed Q15, ordered W/X/Y/Z. */
    int16_t QuaternionRawQ15[4];

    /* 单位：m/s^2 */
    float Acc[3];

    /* 单位：rad/s */
    float Gyro[3];

    /* 单位：deg，顺序 Roll / Pitch / Yaw */
    float Euler[3];

    /* 原始磁场数据 */
    float Mag[3];

    /* 单位：Pa */
    float PressurePa;

    /* 单位：cm */
    float HeightCm;

    /* 单位：°C */
    float TemperatureC;

    /*
     * Raw JY901B quaternion, ordered W/X/Y/Z. Its rotation direction after
     * ORIENT=1 remains a physical-validation item; this is not final q_nb.
     */
    float Quaternion[4];

    /* Matrix formed directly from raw W/X/Y/Z; not an accepted q_nb matrix. */
    float AttitudeMatrix[3][3];

    /* 状态 */
    uint8_t Online;
    uint8_t NewFrame;
    uint8_t LastFrameType;
    uint8_t ValidMask;

    uint32_t FrameCount;
    uint32_t LastUpdateTickMs;

    uint32_t AccFrameCount;
    uint32_t GyroFrameCount;
    uint32_t MagFrameCount;
    uint32_t PressureFrameCount;
    uint32_t QuaternionFrameCount;

    uint64_t AccTimestampUs;
    uint64_t GyroTimestampUs;
    uint64_t MagTimestampUs;
    uint64_t PressureTimestampUs;
    uint64_t QuaternionTimestampUs;
} IMUData;

typedef struct
{
    uint64_t sample_timestamp_us;
    int16_t accel_raw[3];
    int16_t gyro_raw[3];
    float accel_mps2[3];
    float gyro_radps[3];
    float temperature_c;
} Jy901bImuSample;

typedef enum
{
    JY901B_IMU_SAMPLE_GET_OK = 0,
    JY901B_IMU_SAMPLE_GET_EMPTY,
    JY901B_IMU_SAMPLE_GET_INVALID_ARGUMENT
} Jy901bImuSampleGetResult;

typedef struct
{
    uint16_t BaudrateValue;
    uint16_t OutputRateValue;
    uint16_t BandwidthValue;
    uint16_t AlgorithmValue;
    uint16_t OrientationValue;
    uint16_t GyroRangeValue;
    uint16_t AccelRangeValue;
    uint16_t FusionFilterValue;
    uint16_t AccelerationFilterValue;
    uint16_t ReturnContentValue;
    uint16_t ValidMask;
    uint8_t OrientationConfigAttempted;
    uint8_t OrientationConfigOk;
} IMUConfig;

typedef struct
{
    uint32_t valid_frame_count;
    uint32_t checksum_error_count;
    uint32_t parser_resync_count;
    uint32_t process_limit_count;
} IMUStreamDiagnostics;

IMUState IMU_LocalGravitySet(uint8_t instance, float gravity_mps2);
IMUState IMU_Init(uint8_t instance);
IMUState IMU_ApplyDefaultConfig(uint8_t instance, IMUOutputRate output_rate,
                                IMUAlgorithm algorithm);
void IMU_Reset(uint8_t instance);
void IMU_StreamReset(uint8_t instance);
void IMU_Poll(uint8_t instance);
uint8_t IMU_HasNewFrame(uint8_t instance);
void IMU_ClearNewFrame(uint8_t instance);
uint16_t IMU_GetConsecutiveLegalFrameCount(uint8_t instance);
void IMU_StreamDiagnosticsGet(uint8_t instance, IMUStreamDiagnostics *diagnostics);

uint8_t IMU_IsOnline(uint8_t instance);
const IMUData *IMU_GetData(uint8_t instance);
int16_t IMU_AccelMps2ToRaw(uint8_t instance, float accel_mps2);
int16_t IMU_GyroRadpsToRaw(uint8_t instance, float gyro_radps);
Jy901bImuSampleGetResult Jy901bImu_SampleGetNext(uint8_t instance, Jy901bImuSample *sample);
uint32_t Jy901bImu_OverflowCountTake(uint8_t instance);

/* Bootstrap or JY901B IMU-owner context only: these APIs touch UART/DMA. */
IMUState IMU_SetBaudrate(uint8_t instance, IMUBaudrate baudrate);
IMUState IMU_SetOutputRate(uint8_t instance, IMUOutputRate output_rate);
IMUState IMU_SetBandwidth(uint8_t instance, IMUBandwidth bandwidth);
IMUState IMU_SetAlgorithm(uint8_t instance, IMUAlgorithm algorithm);
IMUState IMU_SetInstallationOrientation(uint8_t instance, uint16_t orient_value, uint32_t timeout_ms);
IMUState IMU_SetGyroRange(uint8_t instance, IMUGyroRange range);
IMUState IMU_SetAccelRange(uint8_t instance, IMUAccelRange range);
/* Fusion and acceleration filter recommended value: 200U~500U. */
IMUState IMU_SetFusionFilter(uint8_t instance, uint16_t filter_value);
IMUState IMU_SetAccelerationFilter(uint8_t instance, uint16_t filter_value);
IMUState IMU_SetReturnContent(uint8_t instance, uint16_t rsw);
IMUState IMU_EnsureAlgorithm6Axis(uint8_t instance);
IMUState IMU_EnsureQuaternionOutput(uint8_t instance);
IMUState IMU_HardwareZeroZ(uint8_t instance);
IMUState IMU_GetLastHardwareZeroZResult(uint8_t instance);
IMUState IMU_SaveConfig(uint8_t instance);
const char *IMU_StateToString(IMUState state);
const char *IMU_AlgorithmValueToString(uint16_t value);
void IMU_ConfigCacheGet(uint8_t instance, IMUConfig *config);
void IMU_ConfigCacheSetField(uint8_t instance, uint16_t valid_mask, uint16_t value);
void IMU_ConfigCacheSetAll(uint8_t instance, const IMUConfig *config);

IMUState IMU_ReadBaudrate(uint8_t instance, uint16_t *value);
IMUState IMU_ReadOutputRate(uint8_t instance, uint16_t *value);
IMUState IMU_ReadBandwidth(uint8_t instance, uint16_t *value);
IMUState IMU_ReadAlgorithm(uint8_t instance, uint16_t *value);
IMUState IMU_ReadInstallationOrientation(uint8_t instance, uint16_t *value, uint32_t timeout_ms);
IMUState IMU_ReadGyroRange(uint8_t instance, uint16_t *value);
IMUState IMU_ReadAccelRange(uint8_t instance, uint16_t *value);
IMUState IMU_ReadFusionFilter(uint8_t instance, uint16_t *value);
IMUState IMU_ReadAccelerationFilter(uint8_t instance, uint16_t *value);
IMUState IMU_ReadReturnContent(uint8_t instance, uint16_t *value);
IMUState IMU_ReadCurrentConfig(uint8_t instance, IMUConfig *config);
IMUState IMU_ReadCurrentConfigPartial(uint8_t instance, IMUConfig *config, uint32_t *elapsed_ms);

#endif /* __JY901B_DEVICE_H */
