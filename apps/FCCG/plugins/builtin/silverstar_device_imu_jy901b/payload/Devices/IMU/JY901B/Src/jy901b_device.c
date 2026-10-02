#include "jy901b_device.h"

#include <limits.h>
#include <math.h>
#include <string.h>

#include "project_resources.h"
#include "jy901b_config.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "silverstar_assert.h"

#define IMU_TEMP_BUF_LEN   64U
#define IMU_ORIENT_WRITE_MIN_TIMEOUT_MS \
    ((2U * IMU_CFG_TX_TIMEOUT_MS) + IMU_CFG_UNLOCK_DELAY_MS + IMU_CFG_WRITE_DELAY_MS)
#define IMU_ORIENT_READ_MIN_TIMEOUT_MS \
    (IMU_CFG_TX_TIMEOUT_MS + IMU_CONFIG_READ_TIMEOUT_MS + IMU_CONFIG_REG_GAP_MS)
#define IMU_CONFIG_READ_MAX_POLLS       1024U
#define IMU_MAX_READ_CHUNKS_PER_PROCESS   16U

typedef struct
{
    IMUData imu;
    IMUConfig config_cache;
    IMUState last_hardware_zero_z_result;
    float local_gravity_mps2;
    Jy901bImuSample sample_fifo[JY901B_IMU_SAMPLE_FIFO_DEPTH];
    uint16_t sample_fifo_head;
    uint16_t sample_fifo_tail;
    uint32_t sample_overflow_count;
    uint32_t last_sample_acc_count;
    uint32_t last_sample_gyro_count;
    uint8_t frame_buffer[IMU_FRAME_LEN];
    uint8_t frame_index;
    uint16_t consecutive_legal_frame_count;
    uint32_t valid_frame_count;
    uint32_t checksum_error_count;
    uint32_t parser_resync_count;
    uint32_t process_limit_count;
    uint32_t port_discontinuity_sequence;
    uint8_t register_read_active;
    uint8_t register_read_index;
    uint8_t register_read_frame[IMU_FRAME_LEN];
    uint32_t register_read_started_ms;
    uint8_t register_write_phase;
    uint8_t register_write_reg;
    uint16_t register_write_value;
    uint32_t register_write_started_ms;
} Jy901bContext;

static Jy901bContext s_contexts[PROJECT_JY901B_INSTANCE_COUNT];

_Static_assert(PROJECT_JY901B_INSTANCE_COUNT <=
               PROJECT_JY901B_INSTANCE_COUNT_MAX,
               "JY901B context count exceeds generated resource bound");

#define s_imu                         (s_contexts[instance].imu)
#define s_config_cache                (s_contexts[instance].config_cache)
#define s_lastHardwareZeroZResult     \
    (s_contexts[instance].last_hardware_zero_z_result)
#define s_local_gravity_mps2          \
    (s_contexts[instance].local_gravity_mps2)
#define s_sample_fifo                 (s_contexts[instance].sample_fifo)
#define s_sample_fifo_head            (s_contexts[instance].sample_fifo_head)
#define s_sample_fifo_tail            (s_contexts[instance].sample_fifo_tail)
#define s_sample_overflow_count       \
    (s_contexts[instance].sample_overflow_count)
#define s_last_sample_acc_count       \
    (s_contexts[instance].last_sample_acc_count)
#define s_last_sample_gyro_count      \
    (s_contexts[instance].last_sample_gyro_count)
#define s_frameBuf                    (s_contexts[instance].frame_buffer)
#define s_frameIndex                  (s_contexts[instance].frame_index)
#define s_consecutiveLegalFrameCount \
    (s_contexts[instance].consecutive_legal_frame_count)
#define s_validFrameCount             (s_contexts[instance].valid_frame_count)
#define s_checksumErrorCount          \
    (s_contexts[instance].checksum_error_count)
#define s_parserResyncCount           \
    (s_contexts[instance].parser_resync_count)
#define s_processLimitCount           \
    (s_contexts[instance].process_limit_count)
#define s_portDiscontinuitySequence   \
    (s_contexts[instance].port_discontinuity_sequence)

static PlatformUartId Jy901bResource_UartGet(uint8_t instance)
{
    ProjectJy901bResources resources;

    if (ProjectJy901bResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    {
        return (PlatformUartId)PLATFORM_UART_COUNT;
    }
    return resources.uart;
}

static uint16_t IMU_ConfigGyroRangeGet(uint8_t instance);
static uint16_t IMU_ConfigAccelRangeGet(uint8_t instance);
static float IMU_GyroRangeValueToDps(uint16_t value);
static float IMU_AccelRangeValueToG(uint16_t value);
static int16_t IMU_PhysicalToRawS16(float physical_value, float scale_per_lsb);
static void IMU_OrientationConfigStatusSet(uint8_t instance, uint8_t attempted, uint8_t ok);

static uint16_t Jy901bImu_FifoIndexNext(uint16_t index)
{
    index++;
    return (index >= JY901B_IMU_SAMPLE_FIFO_DEPTH) ? 0U : index;
}
static void Jy901bImu_SampleQueue(uint8_t instance)
{
    Jy901bImuSample sample;
    uint16_t next_head;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_imu, IMUData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (((s_imu.ValidMask & 0x03U) != 0x03U) ||
        (s_imu.AccFrameCount == s_last_sample_acc_count) ||
        (s_imu.GyroFrameCount == s_last_sample_gyro_count))
    {
        return;
    }
    sample.sample_timestamp_us =
        (s_imu.AccTimestampUs > s_imu.GyroTimestampUs) ?
            s_imu.AccTimestampUs : s_imu.GyroTimestampUs;
    for (index = 0U; index < 3U; index++)
    {
        sample.accel_raw[index] = s_imu.AccRaw[index];
        sample.gyro_raw[index] = s_imu.GyroRaw[index];
        sample.accel_mps2[index] = s_imu.Acc[index];
        sample.gyro_radps[index] = s_imu.Gyro[index];
    }
    sample.temperature_c = s_imu.TemperatureC;
    next_head = Jy901bImu_FifoIndexNext(s_sample_fifo_head);
    if (next_head == s_sample_fifo_tail)
    {
        s_sample_overflow_count++;
        return;
    }
    s_sample_fifo[s_sample_fifo_head] = sample;
    s_sample_fifo_head = next_head;
    s_last_sample_acc_count = s_imu.AccFrameCount;
    s_last_sample_gyro_count = s_imu.GyroFrameCount;
}

static void IMU_ParserReset(uint8_t instance)
{
    (void)memset(s_frameBuf, 0, sizeof(s_frameBuf));
    s_frameIndex = 0U;
    s_consecutiveLegalFrameCount = 0U;
}

static int16_t IMU_S16FromLE(const uint8_t *buf)
{
    return (int16_t)(((uint16_t)buf[1] << 8) | (uint16_t)buf[0]);
}

static int32_t IMU_S32FromLE(const uint8_t *buf)
{
    return (int32_t)(((uint32_t)buf[3] << 24) |
                     ((uint32_t)buf[2] << 16) |
                     ((uint32_t)buf[1] << 8)  |
                     ((uint32_t)buf[0]));
}

static uint8_t IMU_Checksum(const uint8_t *frame)
{
    uint8_t sum = 0U;
    uint8_t i;

    for (i = 0U; i < (IMU_FRAME_LEN - 1U); i++)
    {
        sum = (uint8_t)(sum + frame[i]);
    }

    return sum;
}

static void IMU_UpdateAttitudeMatrix(uint8_t instance)
{
    float q0 = s_imu.Quaternion[0];
    float q1 = s_imu.Quaternion[1];
    float q2 = s_imu.Quaternion[2];
    float q3 = s_imu.Quaternion[3];

    /* Retain the raw W/X/Y/Z algebra; ORIENT=1 direction is still under test. */
    s_imu.AttitudeMatrix[0][0] = 1.0f - 2.0f * (q2 * q2 + q3 * q3);
    s_imu.AttitudeMatrix[0][1] = 2.0f * (q1 * q2 - q0 * q3);
    s_imu.AttitudeMatrix[0][2] = 2.0f * (q1 * q3 + q0 * q2);

    s_imu.AttitudeMatrix[1][0] = 2.0f * (q1 * q2 + q0 * q3);
    s_imu.AttitudeMatrix[1][1] = 1.0f - 2.0f * (q1 * q1 + q3 * q3);
    s_imu.AttitudeMatrix[1][2] = 2.0f * (q2 * q3 - q0 * q1);

    s_imu.AttitudeMatrix[2][0] = 2.0f * (q1 * q3 - q0 * q2);
    s_imu.AttitudeMatrix[2][1] = 2.0f * (q2 * q3 + q0 * q1);
    s_imu.AttitudeMatrix[2][2] = 1.0f - 2.0f * (q1 * q1 + q2 * q2);
}

static void IMU_OnFrameDecoded(uint8_t instance, IMUFrameType frame_type)
{
    uint64_t timestamp_us = PlatformTime_Us();

    SILVERSTAR_ASSERT_OBJECT(&s_imu, IMUData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    switch (frame_type)
    {
        case IMUFrameNone:
            break;
        case IMUFrameAcc:
            s_imu.ValidMask |= (1U << 0);
            s_imu.AccFrameCount++;
            s_imu.AccTimestampUs = timestamp_us;
            break;

        case IMUFrameGyro:
            s_imu.ValidMask |= (1U << 1);
            s_imu.GyroFrameCount++;
            s_imu.GyroTimestampUs = timestamp_us;
            break;

        case IMUFrameEuler:
            s_imu.ValidMask |= (1U << 2);
            break;

        case IMUFrameMag:
            s_imu.ValidMask |= (1U << 3);
            s_imu.MagFrameCount++;
            s_imu.MagTimestampUs = timestamp_us;
            break;

        case IMUFramePressureHeight:
            s_imu.ValidMask |= (1U << 4);
            s_imu.PressureFrameCount++;
            s_imu.PressureTimestampUs = timestamp_us;
            break;

        case IMUFrameQuaternion:
            s_imu.ValidMask |= (1U << 5);
            s_imu.QuaternionFrameCount++;
            s_imu.QuaternionTimestampUs = timestamp_us;
            break;

        default:
            break;
    }

    s_imu.LastFrameType = (uint8_t)frame_type;
    s_imu.NewFrame = 1U;
    s_imu.Online = 1U;
    s_imu.FrameCount++;
    s_imu.LastUpdateTickMs = PlatformTime_Ms();
    if (s_consecutiveLegalFrameCount < UINT16_MAX)
    {
        s_consecutiveLegalFrameCount++;
    }

    if ((frame_type == IMUFrameAcc) || (frame_type == IMUFrameGyro))
    {
        Jy901bImu_SampleQueue(instance);
    }
}

static void IMU_AccelerationFrameDecode(uint8_t instance, const uint8_t *data)
{
    float scale = (IMU_AccelRangeValueToG(IMU_ConfigAccelRangeGet(instance)) *
                   s_local_gravity_mps2) / 32768.0f;

    s_imu.AccRaw[0] = IMU_S16FromLE(&data[0]);
    s_imu.AccRaw[1] = IMU_S16FromLE(&data[2]);
    s_imu.AccRaw[2] = IMU_S16FromLE(&data[4]);
    s_imu.Acc[0] = (float)s_imu.AccRaw[0] * scale;
    s_imu.Acc[1] = (float)s_imu.AccRaw[1] * scale;
    s_imu.Acc[2] = (float)s_imu.AccRaw[2] * scale;
    s_imu.TemperatureC = (float)IMU_S16FromLE(&data[6]) / 100.0f;
    IMU_OnFrameDecoded(instance, IMUFrameAcc);
}

static void IMU_GyroscopeFrameDecode(uint8_t instance, const uint8_t *data)
{
    float scale = (IMU_GyroRangeValueToDps(IMU_ConfigGyroRangeGet(instance)) /
                   32768.0f) * (PI / 180.0f);

    s_imu.GyroRaw[0] = IMU_S16FromLE(&data[0]);
    s_imu.GyroRaw[1] = IMU_S16FromLE(&data[2]);
    s_imu.GyroRaw[2] = IMU_S16FromLE(&data[4]);
    s_imu.Gyro[0] = (float)s_imu.GyroRaw[0] * scale;
    s_imu.Gyro[1] = (float)s_imu.GyroRaw[1] * scale;
    s_imu.Gyro[2] = (float)s_imu.GyroRaw[2] * scale;
    s_imu.TemperatureC = (float)IMU_S16FromLE(&data[6]) / 100.0f;
    IMU_OnFrameDecoded(instance, IMUFrameGyro);
}

static void IMU_EulerFrameDecode(uint8_t instance, const uint8_t *data)
{
    const float scale = 180.0f / 32768.0f;

    s_imu.EulerRaw[0] = IMU_S16FromLE(&data[0]);
    s_imu.EulerRaw[1] = IMU_S16FromLE(&data[2]);
    s_imu.EulerRaw[2] = IMU_S16FromLE(&data[4]);
    s_imu.Euler[0] = (float)s_imu.EulerRaw[0] * scale;
    s_imu.Euler[1] = (float)s_imu.EulerRaw[1] * scale;
    s_imu.Euler[2] = (float)s_imu.EulerRaw[2] * scale;
    s_imu.TemperatureC = (float)IMU_S16FromLE(&data[6]) / 100.0f;
    IMU_OnFrameDecoded(instance, IMUFrameEuler);
}

static void IMU_MagnetometerFrameDecode(uint8_t instance, const uint8_t *data)
{
    s_imu.MagRaw[0] = IMU_S16FromLE(&data[0]);
    s_imu.MagRaw[1] = IMU_S16FromLE(&data[2]);
    s_imu.MagRaw[2] = IMU_S16FromLE(&data[4]);
    s_imu.Mag[0] = (float)s_imu.MagRaw[0];
    s_imu.Mag[1] = (float)s_imu.MagRaw[1];
    s_imu.Mag[2] = (float)s_imu.MagRaw[2];
    s_imu.TemperatureC = (float)IMU_S16FromLE(&data[6]) / 100.0f;
    IMU_OnFrameDecoded(instance, IMUFrameMag);
}

static void IMU_PressureFrameDecode(uint8_t instance, const uint8_t *data)
{
    s_imu.PressureRawPa = IMU_S32FromLE(&data[0]);
    s_imu.HeightRawCm = IMU_S32FromLE(&data[4]);
    s_imu.PressurePa = (float)s_imu.PressureRawPa;
    s_imu.HeightCm = (float)s_imu.HeightRawCm;
    IMU_OnFrameDecoded(instance, IMUFramePressureHeight);
}

static void IMU_QuaternionFrameDecode(uint8_t instance, const uint8_t *data)
{
    const float scale = 1.0f / 32768.0f;

    s_imu.QuaternionRawQ15[0] = IMU_S16FromLE(&data[0]);
    s_imu.QuaternionRawQ15[1] = IMU_S16FromLE(&data[2]);
    s_imu.QuaternionRawQ15[2] = IMU_S16FromLE(&data[4]);
    s_imu.QuaternionRawQ15[3] = IMU_S16FromLE(&data[6]);
    s_imu.Quaternion[0] = (float)s_imu.QuaternionRawQ15[0] * scale;
    s_imu.Quaternion[1] = (float)s_imu.QuaternionRawQ15[1] * scale;
    s_imu.Quaternion[2] = (float)s_imu.QuaternionRawQ15[2] * scale;
    s_imu.Quaternion[3] = (float)s_imu.QuaternionRawQ15[3] * scale;
    IMU_UpdateAttitudeMatrix(instance);
    IMU_OnFrameDecoded(instance, IMUFrameQuaternion);
}

static void IMU_DecodeFrame(uint8_t instance, const uint8_t *frame)
{
    IMUFrameType frame_type;
    const uint8_t *data;

    if (frame == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(frame, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    frame_type = (IMUFrameType)frame[1];
    data = &frame[2];

    switch (frame_type)
    {
        case IMUFrameNone:
            break;
        case IMUFrameAcc:
            IMU_AccelerationFrameDecode(instance, data);
            break;
        case IMUFrameGyro:
            IMU_GyroscopeFrameDecode(instance, data);
            break;
        case IMUFrameEuler:
            IMU_EulerFrameDecode(instance, data);
            break;
        case IMUFrameMag:
            IMU_MagnetometerFrameDecode(instance, data);
            break;
        case IMUFramePressureHeight:
            IMU_PressureFrameDecode(instance, data);
            break;
        case IMUFrameQuaternion:
            IMU_QuaternionFrameDecode(instance, data);
            break;
        default:
            break;
    }
}

static void IMU_ParseByte(uint8_t instance, uint8_t byte)
{
    SILVERSTAR_ASSERT_OBJECT(s_frameBuf, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_frameIndex == 0U)
    {
        if (byte == IMU_FRAME_HEADER)
        {
            s_frameBuf[s_frameIndex++] = byte;
        }
        return;
    }

    s_frameBuf[s_frameIndex++] = byte;

    if (s_frameIndex >= IMU_FRAME_LEN)
    {
        if (IMU_Checksum(s_frameBuf) == s_frameBuf[IMU_FRAME_LEN - 1U])
        {
            s_validFrameCount++;
            IMU_DecodeFrame(instance, s_frameBuf);
        }
        else
        {
            s_checksumErrorCount++;
            s_parserResyncCount++;
            s_consecutiveLegalFrameCount = 0U;
        }

        s_frameIndex = 0U;
    }
}

static IMUState IMU_SendConfigFrame(uint8_t instance, uint8_t reg, uint16_t value)
{
    uint8_t frame[IMU_CFG_FRAME_LEN];

    frame[0] = 0xFFU;
    frame[1] = 0xAAU;
    frame[2] = reg;
    frame[3] = (uint8_t)(value & 0xFFU);
    frame[4] = (uint8_t)((value >> 8) & 0xFFU);

    if (PlatformUart_Write(Jy901bResource_UartGet(instance), frame, IMU_CFG_FRAME_LEN,
                           IMU_CFG_TX_TIMEOUT_MS) != PLATFORM_OK)
    {
        return IMU_UART_TX_ERROR;
    }

    return IMU_OK;
}

static PlatformResult IMU_ConfigFrameEnqueue(uint8_t instance,
    uint8_t reg, uint16_t value)
{
    uint8_t frame[IMU_CFG_FRAME_LEN] =
    {
        0xFFU, 0xAAU, reg, (uint8_t)(value & 0xFFU),
        (uint8_t)((value >> 8U) & 0xFFU)
    };

    return PlatformUart_WriteFrameAsync(Jy901bResource_UartGet(instance),
        frame, sizeof(frame), PLATFORM_UART_TX_PRIORITY);
}

static IMUState IMU_ReceiveResume(uint8_t instance, IMUState state)
{
    if (PlatformUart_RxRestart(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    {
        return IMU_UART_RX_ERROR;
    }
    return state;
}

static IMUState IMU_WriteRegister(uint8_t instance, uint8_t reg, uint16_t value, uint8_t save)
{
    IMUState state;

    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (PlatformUart_RxStop(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    {
        return IMU_ReceiveResume(instance, IMU_UART_RX_ERROR);
    }

    state = IMU_SendConfigFrame(instance, IMU_REG_KEY, IMU_KEY_UNLOCK);
    if (state != IMU_OK)
    {
        return IMU_ReceiveResume(instance, state);
    }
    PlatformTime_DelayMs(IMU_CFG_UNLOCK_DELAY_MS);

    state = IMU_SendConfigFrame(instance, reg, value);
    if (state != IMU_OK)
    {
        return IMU_ReceiveResume(instance, state);
    }
    PlatformTime_DelayMs(IMU_CFG_WRITE_DELAY_MS);

    if (save != 0U)
    {
        state = IMU_SendConfigFrame(instance, IMU_REG_SAVE, 0x0000U);
        if (state != IMU_OK)
        {
            return IMU_ReceiveResume(instance, state);
        }
        PlatformTime_DelayMs(IMU_CFG_SAVE_DELAY_MS);
    }

    return IMU_ReceiveResume(instance, IMU_OK);
}

static uint8_t IMU_ReadResponseChecksumValid(const uint8_t *frame)
{
    uint8_t sum = 0U;
    uint8_t i;

    if (frame == NULL) { return 0U; }
    for (i = 0U; i < (IMU_FRAME_LEN - 1U); i++)
    {
        sum = (uint8_t)(sum + frame[i]);
    }
    return (sum == frame[IMU_FRAME_LEN - 1U]) ? 1U : 0U;
}

static uint8_t IMU_ParseReadResponseByte(uint8_t byte, uint8_t *frame, uint8_t *idx)
{
    uint8_t next;

    if ((frame == NULL) || (idx == NULL)) { return 0U; }
    SILVERSTAR_ASSERT(*idx < IMU_FRAME_LEN,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if ((*idx == 0U) && (byte != IMU_FRAME_HEADER)) { return 0U; }
    frame[*idx] = byte;
    (*idx)++;
    if (*idx < IMU_FRAME_LEN) { return 0U; }
    if (IMU_ReadResponseChecksumValid(frame) != 0U)
    {
        *idx = 0U;
        /* Consume a whole legal stream frame; never inspect its payload
         * for a register-response header. Both frame kinds share the CRC. */
        return (uint8_t)(frame[1] == IMU_REG_READ_RESPONSE);
    }
    /* A corrupt/truncated candidate may have swallowed the next header.
     * Retain its earliest bounded suffix, including an incomplete header. */
    *idx = 0U;
    for (next = 1U; next < IMU_FRAME_LEN; next++)
    {
        if (frame[next] == IMU_FRAME_HEADER)
        {
            *idx = (uint8_t)(IMU_FRAME_LEN - next);
            (void)memmove(frame, &frame[next], *idx);
            break;
        }
    }
    return 0U;
}

Jy901bRegisterReadStartResult IMU_RegisterReadAsyncStart(
    uint8_t instance, uint8_t reg)
{
    uint8_t cmd[IMU_CFG_FRAME_LEN] =
        {0xFFU, 0xAAU, IMU_REG_READADDR, reg, 0x00U};
    Jy901bContext *context;

    if (instance >= PROJECT_JY901B_INSTANCE_COUNT)
    { return Jy901bRegisterReadStartResult_InvalidArgument; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, Jy901bContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->register_write_phase <= 2U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((context->register_read_active != 0U) ||
        (context->register_write_phase != 0U))
    { return Jy901bRegisterReadStartResult_Busy; }
    if (PlatformUart_RxFlush(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    { return Jy901bRegisterReadStartResult_IoError; }
    {
        PlatformResult send_result = PlatformUart_WriteFrameAsync(
            Jy901bResource_UartGet(instance), cmd, sizeof(cmd),
            PLATFORM_UART_TX_PRIORITY);
        if (send_result == PLATFORM_BUSY)
        { return Jy901bRegisterReadStartResult_Busy; }
        if (send_result != PLATFORM_OK)
        { return Jy901bRegisterReadStartResult_IoError; }
    }
    context->register_read_index = 0U;
    context->register_read_started_ms = PlatformTime_Ms();
    context->register_read_active = 1U;
    return Jy901bRegisterReadStartResult_Ok;
}

static Jy901bRegisterReadPollResult IMU_RegisterReadDrain(
    uint8_t instance, Jy901bContext *context, uint16_t *value)
{
    uint8_t buffer[IMU_TEMP_BUF_LEN];
    uint16_t remaining;
    uint16_t capacity;
    uint16_t read_length;
    uint16_t index;
    uint32_t chunk;

    if (PlatformUart_RxCountGet(Jy901bResource_UartGet(instance),
            &remaining) != PLATFORM_OK)
    { return Jy901bRegisterReadPollResult_IoError; }
    /* Snapshot the queue once: newly arriving data cannot extend this poll.
     * No byte timestamps exist; a poll after the deadline is conservative. */
    for (chunk = 0U; (chunk < IMU_MAX_READ_CHUNKS_PER_PROCESS) &&
            (remaining != 0U); chunk++)
    {
        if ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >
                IMU_CONFIG_READ_TIMEOUT_MS)
        { return Jy901bRegisterReadPollResult_Timeout; }
        capacity = (remaining < sizeof(buffer)) ? remaining : sizeof(buffer);
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), buffer,
                capacity, &read_length) != PLATFORM_OK)
        { return Jy901bRegisterReadPollResult_IoError; }
        SILVERSTAR_ASSERT(read_length <= capacity,
            SILVERSTAR_ASSERT_MODULE_DEVICE,
            SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        if (read_length == 0U) { break; }
        remaining = (uint16_t)(remaining - read_length);
        for (index = 0U; index < read_length; index++)
        {
            if (IMU_ParseReadResponseByte(buffer[index],
                    context->register_read_frame,
                    &context->register_read_index) != 0U)
            {
                if ((uint32_t)(PlatformTime_Ms() -
                        context->register_read_started_ms) >
                        IMU_CONFIG_READ_TIMEOUT_MS)
                { return Jy901bRegisterReadPollResult_Timeout; }
                *value = (uint16_t)(((uint16_t)context->register_read_frame[3] << 8) |
                                    context->register_read_frame[2]);
                return Jy901bRegisterReadPollResult_Complete;
            }
        }
    }
    return Jy901bRegisterReadPollResult_Pending;
}

Jy901bRegisterReadPollResult IMU_RegisterReadAsyncPoll(
    uint8_t instance, uint16_t *value)
{
    Jy901bContext *context;
    Jy901bRegisterReadPollResult result;

    if ((instance >= PROJECT_JY901B_INSTANCE_COUNT) || (value == NULL))
    { return Jy901bRegisterReadPollResult_NotReady; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT(context->register_read_index < IMU_FRAME_LEN,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if (context->register_read_active == 0U)
    { return Jy901bRegisterReadPollResult_NotReady; }
    if ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >
            IMU_CONFIG_READ_TIMEOUT_MS)
    { result = Jy901bRegisterReadPollResult_Timeout; }
    else
    { result = IMU_RegisterReadDrain(instance, context, value); }
    if ((result == Jy901bRegisterReadPollResult_Pending) &&
        ((uint32_t)(PlatformTime_Ms() - context->register_read_started_ms) >=
         IMU_CONFIG_READ_TIMEOUT_MS))
    { result = Jy901bRegisterReadPollResult_Timeout; }
    if (result != Jy901bRegisterReadPollResult_Pending)
    { context->register_read_active = 0U; }
    return result;
}

Jy901bRegisterWriteStartResult IMU_RegisterWriteAsyncStart(
    uint8_t instance, uint8_t reg, uint16_t value)
{
    Jy901bContext *context;
    PlatformUartId uart;

    if (instance >= PROJECT_JY901B_INSTANCE_COUNT)
    { return Jy901bRegisterWriteStartResult_InvalidArgument; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, Jy901bContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->register_write_phase <= 2U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((context->register_read_active != 0U) ||
        (context->register_write_phase != 0U))
    { return Jy901bRegisterWriteStartResult_Busy; }
    uart = Jy901bResource_UartGet(instance);
    if (PlatformUart_RxStop(uart) != PLATFORM_OK)
    { return Jy901bRegisterWriteStartResult_IoError; }
    {
        PlatformResult send_result = IMU_ConfigFrameEnqueue(
            instance, IMU_REG_KEY, IMU_KEY_UNLOCK);
        if (send_result == PLATFORM_BUSY)
        {
            (void)PlatformUart_RxRestart(uart);
            return Jy901bRegisterWriteStartResult_Busy;
        }
        if (send_result != PLATFORM_OK)
        {
            (void)PlatformUart_RxRestart(uart);
            return Jy901bRegisterWriteStartResult_IoError;
        }
    }
    context->register_write_reg = reg;
    context->register_write_value = value;
    context->register_write_started_ms = PlatformTime_Ms();
    context->register_write_phase = 1U;
    return Jy901bRegisterWriteStartResult_Ok;
}

Jy901bRegisterWritePollResult IMU_RegisterWriteAsyncPoll(uint8_t instance)
{
    Jy901bContext *context;
    PlatformUartId uart;
    uint32_t now_ms;

    if (instance >= PROJECT_JY901B_INSTANCE_COUNT)
    { return Jy901bRegisterWritePollResult_NotReady; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, Jy901bContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->register_write_phase <= 2U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (context->register_write_phase == 0U)
    { return Jy901bRegisterWritePollResult_NotReady; }
    uart = Jy901bResource_UartGet(instance);
    now_ms = PlatformTime_Ms();
    if ((uint32_t)(now_ms - context->register_write_started_ms) >=
        IMU_CFG_WRITE_ASYNC_TIMEOUT_MS)
    {
        context->register_write_phase = 0U;
        (void)PlatformUart_RxRestart(uart);
        return Jy901bRegisterWritePollResult_IoError;
    }
    if (context->register_write_phase == 1U)
    {
        if ((uint32_t)(now_ms - context->register_write_started_ms) <
            IMU_CFG_UNLOCK_DELAY_MS)
        { return Jy901bRegisterWritePollResult_Pending; }
        PlatformResult send_result = IMU_ConfigFrameEnqueue(instance,
            context->register_write_reg, context->register_write_value);
        if (send_result == PLATFORM_BUSY)
        { return Jy901bRegisterWritePollResult_Pending; }
        if (send_result != PLATFORM_OK)
        {
            context->register_write_phase = 0U;
            (void)PlatformUart_RxRestart(uart);
            return Jy901bRegisterWritePollResult_IoError;
        }
        context->register_write_started_ms = PlatformTime_Ms();
        context->register_write_phase = 2U;
        return Jy901bRegisterWritePollResult_Pending;
    }
    if ((uint32_t)(now_ms - context->register_write_started_ms) <
        IMU_CFG_WRITE_DELAY_MS)
    { return Jy901bRegisterWritePollResult_Pending; }
    context->register_write_phase = 0U;
    return (PlatformUart_RxRestart(uart) == PLATFORM_OK) ?
        Jy901bRegisterWritePollResult_Complete :
        Jy901bRegisterWritePollResult_IoError;
}

static IMUState IMU_ReadRegister(uint8_t instance, uint8_t reg, uint16_t *value)
{
    uint8_t cmd[IMU_CFG_FRAME_LEN];
    uint8_t rxBuf[IMU_TEMP_BUF_LEN];
    uint8_t frame[IMU_FRAME_LEN];
    uint8_t idx = 0U;
    uint16_t readLen;
    uint16_t i;
    uint32_t startTick;
    uint32_t poll;

    if (value == NULL)
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    cmd[0] = 0xFFU;
    cmd[1] = 0xAAU;
    cmd[2] = IMU_REG_READADDR;
    cmd[3] = reg;
    cmd[4] = 0x00U;

    /*
     * The Platform UART backend owns the receive mechanism. Register reads
     * only consume its byte stream and never switch to a competing RX path.
     */
    (void)PlatformUart_RxFlush(Jy901bResource_UartGet(instance));

    if (PlatformUart_Write(Jy901bResource_UartGet(instance), cmd, sizeof(cmd),
                           IMU_CFG_TX_TIMEOUT_MS) != PLATFORM_OK)
    {
        PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
        return IMU_UART_TX_ERROR;
    }

    startTick = PlatformTime_Ms();
    for (poll = 0U; poll < IMU_CONFIG_READ_MAX_POLLS; poll++)
    {
        if ((PlatformTime_Ms() - startTick) >= IMU_CONFIG_READ_TIMEOUT_MS)
        {
            break;
        }
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), rxBuf, sizeof(rxBuf),
                              &readLen) != PLATFORM_OK)
        {
            return IMU_UART_RX_ERROR;
        }
        if (readLen == 0U)
        {
            PlatformTime_DelayMs(1U);
            continue;
        }

        for (i = 0U; (i < readLen) && (i < IMU_TEMP_BUF_LEN); i++)
        {
            if (IMU_ParseReadResponseByte(rxBuf[i], frame, &idx) != 0U)
            {
                *value = (uint16_t)(((uint16_t)frame[3] << 8) | frame[2]);
                PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
                return IMU_OK;
            }
        }
    }

    PlatformTime_DelayMs(IMU_CONFIG_REG_GAP_MS);
    return IMU_RESP_TIMEOUT;
}

static IMUState IMU_WriteFilterRegister(uint8_t instance, uint8_t reg, uint16_t value)
{
    if ((value < IMU_FILTER_VALUE_MIN) || (value > IMU_FILTER_VALUE_MAX))
    {
        return IMU_RESP_INVALID;
    }

    return IMU_WriteRegister(instance, reg, value, 0U);
}

static IMUState IMU_BaudrateToConfig(IMUBaudrate baudrate, uint16_t *reg_value, uint32_t *uart_baudrate)
{
    if ((reg_value == NULL) || (uart_baudrate == NULL))
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(reg_value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    switch (baudrate)
    {
        case Baudrate_4800:
            *reg_value = IMU_BAUD_4800_VALUE;
            *uart_baudrate = IMU_UART_BAUD_4800;
            break;

        case Baudrate_9600:
            *reg_value = IMU_BAUD_9600_VALUE;
            *uart_baudrate = IMU_UART_BAUD_9600;
            break;

        case Baudrate_19200:
            *reg_value = IMU_BAUD_19200_VALUE;
            *uart_baudrate = IMU_UART_BAUD_19200;
            break;

        case Baudrate_38400:
            *reg_value = IMU_BAUD_38400_VALUE;
            *uart_baudrate = IMU_UART_BAUD_38400;
            break;

        case Baudrate_57600:
            *reg_value = IMU_BAUD_57600_VALUE;
            *uart_baudrate = IMU_UART_BAUD_57600;
            break;

        case Baudrate_115200:
            *reg_value = IMU_BAUD_115200_VALUE;
            *uart_baudrate = IMU_UART_BAUD_115200;
            break;

        case Baudrate_230400:
            *reg_value = IMU_BAUD_230400_VALUE;
            *uart_baudrate = IMU_UART_BAUD_230400;
            break;

        case Baudrate_460800:
        default:
            return IMU_RESP_INVALID;
    }

    return IMU_OK;
}

static IMUState IMU_OutputRateToValue(IMUOutputRate output_rate, uint16_t *value)
{
    if (value == NULL)
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    switch (output_rate)
    {
        case OutputRate_0_2Hz:
        case OutputRate_0_5Hz:
        case OutputRate_1Hz:
        case OutputRate_2Hz:
        case OutputRate_5Hz:
        case OutputRate_10Hz:
        case OutputRate_20Hz:
        case OutputRate_50Hz:
        case OutputRate_100Hz:
        case OutputRate_200Hz:
        case OutputRate_Single0C:
        case OutputRate_None:
        case OutputRate_Single:
            *value = (uint16_t)output_rate;
            return IMU_OK;

        default:
            return IMU_RESP_INVALID;
    }
}

static IMUState IMU_BandwidthToValue(IMUBandwidth bandwidth, uint16_t *value)
{
    if (value == NULL)
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    switch (bandwidth)
    {
        case Bandwidth_256Hz:
        case Bandwidth_188Hz:
        case Bandwidth_98Hz:
        case Bandwidth_42Hz:
        case Bandwidth_20Hz:
        case Bandwidth_10Hz:
        case Bandwidth_5Hz:
            *value = (uint16_t)bandwidth;
            return IMU_OK;

        default:
            return IMU_RESP_INVALID;
    }
}

static IMUState IMU_AlgorithmToValue(IMUAlgorithm algorithm, uint16_t *value)
{
    if (value == NULL)
    {
        return IMU_NULL;
    }

    switch (algorithm)
    {
        case Algorithm_9Axis:
        case Algorithm_6Axis:
            *value = (uint16_t)algorithm;
            return IMU_OK;

        default:
            return IMU_RESP_INVALID;
    }
}

static IMUState IMU_GyroRangeToValue(IMUGyroRange range, uint16_t *value)
{
    if (value == NULL)
    {
        return IMU_NULL;
    }

    switch (range)
    {
        case GyroRange_200Dps:
        case GyroRange_500Dps:
        case GyroRange_1000Dps:
        case GyroRange_2000Dps:
            *value = (uint16_t)range;
            return IMU_OK;

        default:
            return IMU_RESP_INVALID;
    }
}

static IMUState IMU_AccelRangeToValue(IMUAccelRange range, uint16_t *value)
{
    if (value == NULL)
    {
        return IMU_NULL;
    }

    switch (range)
    {
        case AccelRange_2G:
        case AccelRange_4G:
        case AccelRange_8G:
        case AccelRange_16G:
            *value = (uint16_t)range;
            return IMU_OK;

        default:
            return IMU_RESP_INVALID;
    }
}

static uint16_t IMU_ConfigGyroRangeGet(uint8_t instance)
{
    if ((s_config_cache.ValidMask & IMU_CONFIG_VALID_GYRO_RANGE) != 0U)
    {
        return s_config_cache.GyroRangeValue;
    }

    return IMU_DEFAULT_GYRO_RANGE_VALUE;
}

static uint16_t IMU_ConfigAccelRangeGet(uint8_t instance)
{
    if ((s_config_cache.ValidMask & IMU_CONFIG_VALID_ACCEL_RANGE) != 0U)
    {
        return s_config_cache.AccelRangeValue;
    }

    return IMU_DEFAULT_ACCEL_RANGE_VALUE;
}

static float IMU_GyroRangeValueToDps(uint16_t value)
{
    switch (value & 0x000FU)
    {
        case IMU_GYRO_RANGE_200DPS_VALUE:
            return 200.0f;

        case IMU_GYRO_RANGE_500DPS_VALUE:
            return 500.0f;

        case IMU_GYRO_RANGE_1000DPS_VALUE:
            return 1000.0f;

        case IMU_GYRO_RANGE_2000DPS_VALUE:
        default:
            return 2000.0f;
    }
}

static float IMU_AccelRangeValueToG(uint16_t value)
{
    switch (value & 0x000FU)
    {
        case IMU_ACCEL_RANGE_2G_VALUE:
            return 2.0f;

        case IMU_ACCEL_RANGE_4G_VALUE:
            return 4.0f;

        case IMU_ACCEL_RANGE_8G_VALUE:
            return 8.0f;

        case IMU_ACCEL_RANGE_16G_VALUE:
        default:
            return 16.0f;
    }
}

static int16_t IMU_PhysicalToRawS16(float physical_value, float scale_per_lsb)
{
    float raw_value;

    if ((!isfinite(physical_value)) || (!isfinite(scale_per_lsb)) ||
        (scale_per_lsb <= 0.0f))
    {
        return 0;
    }

    raw_value = physical_value / scale_per_lsb;
    if (raw_value >= (float)INT16_MAX)
    {
        return INT16_MAX;
    }
    if (raw_value <= (float)INT16_MIN)
    {
        return INT16_MIN;
    }

    return (int16_t)lroundf(raw_value);
}

static const char *IMU_AlgorithmToString(uint16_t value)
{
    switch (value)
    {
        case IMU_ALGORITHM_9_AXIS_VALUE:
            return "9-axis";

        case IMU_ALGORITHM_6_AXIS_VALUE:
            return "6-axis";

        default:
            return "unknown";
    }
}

const char *IMU_StateToString(IMUState state)
{
    SILVERSTAR_ASSERT_OBJECT(&state, IMUState,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(state <= IMU_RESP_TIMEOUT,
                      SILVERSTAR_ASSERT_MODULE_DEVICE,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (state)
    {
        case IMU_OK:
            return "OK";

        case IMU_NULL:
            return "NULL";

        case IMU_UART_TX_ERROR:
            return "UART_TX_ERROR";

        case IMU_UART_RX_ERROR:
            return "UART_RX_ERROR";

        case IMU_UART_INIT_ERROR:
            return "UART_INIT_ERROR";

        case IMU_RESP_INVALID:
            return "RESP_INVALID";

        case IMU_RESP_TIMEOUT:
            return "RESP_TIMEOUT";

        default:
            return "UNKNOWN";
    }
}

const char *IMU_AlgorithmValueToString(uint16_t value)
{
    return IMU_AlgorithmToString(value);
}

void IMU_Reset(uint8_t instance)
{
    IMU_StreamReset(instance);
    memset(&s_config_cache, 0, sizeof(s_config_cache));
    s_contexts[instance].register_read_active = 0U;
    s_contexts[instance].register_write_phase = 0U;
}

void IMU_StreamReset(uint8_t instance)
{
    uint32_t state = IMU_IrqLock();

    memset(&s_imu, 0, sizeof(s_imu));
    IMU_ParserReset(instance);
    s_validFrameCount = 0U;
    s_checksumErrorCount = 0U;
    s_parserResyncCount = 0U;
    s_portDiscontinuitySequence = 0U;
    s_sample_fifo_head = 0U;
    s_sample_fifo_tail = 0U;
    s_sample_overflow_count = 0U;
    s_last_sample_acc_count = 0U;
    s_last_sample_gyro_count = 0U;
    IMU_IrqUnlock(state);
}

static void IMU_DefaultValuesGet(const IMUConfig *config, uint16_t values[10])
{
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig, SILVERSTAR_ASSERT_MODULE_DEVICE);
    values[0] = config->BaudrateValue;
    values[1] = config->OrientationValue;
    values[2] = config->AlgorithmValue;
    values[3] = config->BandwidthValue;
    values[4] = config->OutputRateValue;
    values[5] = config->GyroRangeValue;
    values[6] = config->AccelRangeValue;
    values[7] = config->FusionFilterValue;
    values[8] = config->AccelerationFilterValue;
    values[9] = config->ReturnContentValue;
}

Jy901bStartupRegisterResult IMU_StartupRegisterGet(
    uint8_t index, IMUOutputRate output_rate, IMUAlgorithm algorithm,
    uint8_t *reg, uint16_t *expected_value)
{
    static const uint8_t registers[JY901B_STARTUP_REGISTER_COUNT] =
    {
        IMU_REG_BAUD, IMU_REG_ORIENT, IMU_REG_AXIS6,
        IMU_REG_BANDWIDTH, IMU_REG_RRATE, IMU_REG_GYRORANGE,
        IMU_REG_ACCRANGE, IMU_REG_FILTK, IMU_REG_ACCFILT,
        IMU_REG_RSW
    };
    const uint16_t values[JY901B_STARTUP_REGISTER_COUNT] =
    {
        IMU_DEFAULT_BAUD_VALUE, IMU_DEFAULT_ORIENT_VALUE,
        (uint16_t)algorithm, IMU_DEFAULT_BANDWIDTH_VALUE,
        (uint16_t)output_rate, IMU_DEFAULT_GYRO_RANGE_VALUE,
        IMU_DEFAULT_ACCEL_RANGE_VALUE, IMU_DEFAULT_FUSION_FILTER_VALUE,
        IMU_DEFAULT_ACCEL_FILTER_VALUE, FC_IMU_RETURN_CONTENT_DEFAULT
    };

    if ((index >= JY901B_STARTUP_REGISTER_COUNT) ||
        (reg == NULL) || (expected_value == NULL))
    { return Jy901bStartupRegisterResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(reg, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(expected_value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    *reg = registers[index];
    *expected_value = values[index];
    return Jy901bStartupRegisterResult_Ok;
}

static IMUState IMU_DefaultDifferencesApply(uint8_t instance,
    const uint16_t actual[10], const uint16_t expected[10], uint8_t *changed)
{
    uint8_t index;
    SILVERSTAR_ASSERT_OBJECT(changed, uint8_t, SILVERSTAR_ASSERT_MODULE_DEVICE);
    *changed = 0U;
    for (index = 0U; index < 10U; index++)
    {
        IMUState result;
        uint8_t reg;
        uint16_t ignored_expected;
        if (actual[index] == expected[index]) { continue; }
        (void)IMU_StartupRegisterGet(index, OutputRate_200Hz,
            Algorithm_6Axis, &reg, &ignored_expected);
        result = (index == 0U) ? IMU_SetBaudrate(instance, Baudrate_230400) :
            IMU_WriteRegister(instance, reg, expected[index], 0U);
        if (result != IMU_OK) { return result; }
        *changed = 1U;
    }
    return IMU_OK;
}

IMUState IMU_ApplyDefaultConfig(uint8_t instance, IMUOutputRate output_rate,
                                IMUAlgorithm algorithm)
{
    IMUConfig actual = {0};
    uint16_t values[10];
    uint16_t expected[JY901B_STARTUP_REGISTER_COUNT];
    IMUState result;
    uint8_t changed;
    uint8_t index;
    uint8_t reg;
    SILVERSTAR_ASSERT_OBJECT(&actual, IMUConfig, SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (index = 0U; index < JY901B_STARTUP_REGISTER_COUNT; index++)
    {
        (void)IMU_StartupRegisterGet(index, output_rate, algorithm,
            &reg, &expected[index]);
    }
    result = IMU_ReadCurrentConfig(instance, &actual);
    if (result != IMU_OK) { return result; }
    IMU_DefaultValuesGet(&actual, values);
    result = IMU_DefaultDifferencesApply(instance, values, expected, &changed);
    if (result != IMU_OK) { return result; }
    if (changed == 0U) { return IMU_OK; }
    /* Transport success is not readback. Verify every effective field.
     * JY exposes no independent NVM comparison: startup remains volatile.
     * Explicit maintenance may call IMU_SaveConfig; never infer NVM changes. */
    result = IMU_ReadCurrentConfig(instance, &actual);
    if (result != IMU_OK) { return result; }
    IMU_DefaultValuesGet(&actual, values);
    for (index = 0U; index < 10U; index++)
    {
        if (values[index] != expected[index]) { return IMU_RESP_INVALID; }
    }
    IMU_StreamReset(instance);
    return IMU_OK;
}

IMUState IMU_LocalGravitySet(uint8_t instance, float gravity_mps2)
{
    if ((!isfinite(gravity_mps2)) || (gravity_mps2 <= 0.0f))
    {
        return IMU_RESP_INVALID;
    }
    s_local_gravity_mps2 = gravity_mps2;
    return IMU_OK;
}

IMUState IMU_Init(uint8_t instance)
{
    if ((!isfinite(s_local_gravity_mps2)) ||
        (s_local_gravity_mps2 <= 0.0f))
    {
        return IMU_RESP_INVALID;
    }
    IMU_Reset(instance);
    s_lastHardwareZeroZResult = IMU_RESP_INVALID;
    return (PlatformUart_Init(Jy901bResource_UartGet(instance)) == PLATFORM_OK) ?
        IMU_OK : IMU_UART_INIT_ERROR;
    //仅修改波特率时打开该注释，单片机波特率需要同步修改
}

void IMU_Poll(uint8_t instance)
{
    uint8_t tempBuf[IMU_TEMP_BUF_LEN];
    PlatformUartDiagnostics port_diagnostics;
    uint16_t readLen;
    uint16_t i;
    uint32_t now;
    uint32_t chunk;

    SILVERSTAR_ASSERT_OBJECT(&s_imu, IMUData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((s_contexts[instance].register_read_active != 0U) ||
        (s_contexts[instance].register_write_phase != 0U))
    { return; }
    if (PlatformUart_DiagnosticsGet(Jy901bResource_UartGet(instance), &port_diagnostics) !=
        PLATFORM_OK)
    {
        return;
    }
    if (port_diagnostics.rx_discontinuity_count !=
        s_portDiscontinuitySequence)
    {
        IMU_ParserReset(instance);
        s_parserResyncCount++;
        s_portDiscontinuitySequence =
            port_diagnostics.rx_discontinuity_count;
    }

    readLen = 0U;
    for (chunk = 0U; chunk < IMU_MAX_READ_CHUNKS_PER_PROCESS; chunk++)
    {
        if (PlatformUart_Read(Jy901bResource_UartGet(instance), tempBuf, sizeof(tempBuf),
                              &readLen) != PLATFORM_OK)
        {
            return;
        }
        for (i = 0U; (i < readLen) && (i < IMU_TEMP_BUF_LEN); i++)
        {
            IMU_ParseByte(instance, tempBuf[i]);
        }
        if (readLen == 0U) { break; }
    }
    if ((chunk == IMU_MAX_READ_CHUNKS_PER_PROCESS) && (readLen != 0U))
    {
        s_processLimitCount++;
    }

    /* Decoding may publish a timestamp newer than the poll entry tick. */
    now = PlatformTime_Ms();
    if ((s_imu.ValidMask == 0U) ||
        ((now - s_imu.LastUpdateTickMs) > IMU_ONLINE_TIMEOUT_MS))
    {
        s_imu.Online = 0U;
    }
}

uint8_t IMU_HasNewFrame(uint8_t instance)
{
    return s_imu.NewFrame;
}

void IMU_ClearNewFrame(uint8_t instance)
{
    s_imu.NewFrame = 0U;
}

uint16_t IMU_GetConsecutiveLegalFrameCount(uint8_t instance)
{
    return s_consecutiveLegalFrameCount;
}

uint8_t IMU_IsOnline(uint8_t instance)
{
    uint32_t now = PlatformTime_Ms();

    if ((s_imu.ValidMask == 0U) ||
        ((now - s_imu.LastUpdateTickMs) > IMU_ONLINE_TIMEOUT_MS))
    {
        return 0U;
    }

    return 1U;
}

const IMUData *IMU_GetData(uint8_t instance)
{
    return &s_imu;
}

int16_t IMU_AccelMps2ToRaw(uint8_t instance, float accel_mps2)
{
    float scale_per_lsb;

    scale_per_lsb =
        (IMU_AccelRangeValueToG(IMU_ConfigAccelRangeGet(instance)) *
         s_local_gravity_mps2) /
        32768.0f;
    return IMU_PhysicalToRawS16(accel_mps2, scale_per_lsb);
}

int16_t IMU_GyroRadpsToRaw(uint8_t instance, float gyro_radps)
{
    float scale_per_lsb;

    scale_per_lsb =
        (IMU_GyroRangeValueToDps(IMU_ConfigGyroRangeGet(instance)) / 32768.0f) *
        (PI / 180.0f);
    return IMU_PhysicalToRawS16(gyro_radps, scale_per_lsb);
}

Jy901bImuSampleGetResult Jy901bImu_SampleGetNext(uint8_t instance, Jy901bImuSample *sample)
{
    uint32_t state;

    if (sample == NULL) { return JY901B_IMU_SAMPLE_GET_INVALID_ARGUMENT; }
    state = IMU_IrqLock();
    if (s_sample_fifo_tail == s_sample_fifo_head)
    {
        IMU_IrqUnlock(state);
        return JY901B_IMU_SAMPLE_GET_EMPTY;
    }
    *sample = s_sample_fifo[s_sample_fifo_tail];
    s_sample_fifo_tail = Jy901bImu_FifoIndexNext(s_sample_fifo_tail);
    IMU_IrqUnlock(state);
    return JY901B_IMU_SAMPLE_GET_OK;
}

uint32_t Jy901bImu_OverflowCountTake(uint8_t instance)
{
    uint32_t state = IMU_IrqLock();
    uint32_t count = s_sample_overflow_count;

    s_sample_overflow_count = 0U;
    IMU_IrqUnlock(state);
    return count;
}

void IMU_ConfigCacheGet(uint8_t instance, IMUConfig *config)
{
    if (config == NULL)
    {
        return;
    }

    *config = s_config_cache;
}

void IMU_ConfigCacheSetField(uint8_t instance, uint16_t valid_mask, uint16_t value)
{
    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((valid_mask & IMU_CONFIG_VALID_BAUD) != 0U)
    {
        s_config_cache.BaudrateValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_RATE) != 0U)
    {
        s_config_cache.OutputRateValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_BANDWIDTH) != 0U)
    {
        s_config_cache.BandwidthValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_ALGORITHM) != 0U)
    {
        s_config_cache.AlgorithmValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_ORIENTATION) != 0U)
    {
        s_config_cache.OrientationValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_GYRO_RANGE) != 0U)
    {
        s_config_cache.GyroRangeValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_ACCEL_RANGE) != 0U)
    {
        s_config_cache.AccelRangeValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_FUSION_FILTER) != 0U)
    {
        s_config_cache.FusionFilterValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_ACCEL_FILTER) != 0U)
    {
        s_config_cache.AccelerationFilterValue = value;
    }
    if ((valid_mask & IMU_CONFIG_VALID_RETURN_CONTENT) != 0U)
    {
        s_config_cache.ReturnContentValue = value;
    }

    s_config_cache.ValidMask |= (uint16_t)(valid_mask & IMU_CONFIG_VALID_ALL);
}

void IMU_ConfigCacheSetAll(uint8_t instance, const IMUConfig *config)
{
    uint8_t orientation_attempted;
    uint8_t orientation_ok;

    if (config == NULL)
    {
        return;
    }

    orientation_attempted = s_config_cache.OrientationConfigAttempted;
    orientation_ok = s_config_cache.OrientationConfigOk;
    s_config_cache = *config;
    s_config_cache.ValidMask = IMU_CONFIG_VALID_ALL;
    s_config_cache.OrientationConfigAttempted = orientation_attempted;
    s_config_cache.OrientationConfigOk = orientation_ok;
}

static void IMU_OrientationConfigStatusSet(uint8_t instance, uint8_t attempted, uint8_t ok)
{
    s_config_cache.OrientationConfigAttempted = attempted;
    s_config_cache.OrientationConfigOk = ok;
}

IMUState IMU_SetBaudrate(uint8_t instance, IMUBaudrate baudrate)
{
    IMUState state;
    uint16_t baud_value;
    uint32_t uart_baudrate;

    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    state = IMU_BaudrateToConfig(baudrate, &baud_value, &uart_baudrate);
    if (state != IMU_OK)
    {
        return state;
    }

    if (PlatformUart_RxStop(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    {
        return IMU_ReceiveResume(instance, IMU_UART_RX_ERROR);
    }

    state = IMU_SendConfigFrame(instance, IMU_REG_KEY, IMU_KEY_UNLOCK);
    if (state != IMU_OK)
    {
        return IMU_ReceiveResume(instance, state);
    }
    PlatformTime_DelayMs(IMU_CFG_UNLOCK_DELAY_MS);

    state = IMU_SendConfigFrame(instance, IMU_REG_BAUD, baud_value);
    if (state != IMU_OK)
    {
        return IMU_ReceiveResume(instance, state);
    }
    PlatformTime_DelayMs(IMU_CFG_BAUD_SWITCH_DELAY_MS);

    if (PlatformUart_BaudSet(Jy901bResource_UartGet(instance), uart_baudrate) != PLATFORM_OK)
    {
        return IMU_UART_INIT_ERROR;
    }
    return IMU_OK;
}

IMUState IMU_SetOutputRate(uint8_t instance, IMUOutputRate output_rate)
{
    IMUState state;
    uint16_t value = 0U;

    state = IMU_OutputRateToValue(output_rate, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return IMU_WriteRegister(instance, IMU_REG_RRATE, value, 0U);
}

IMUState IMU_SetBandwidth(uint8_t instance, IMUBandwidth bandwidth)
{
    IMUState state;
    uint16_t value = 0U;

    state = IMU_BandwidthToValue(bandwidth, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return IMU_WriteRegister(instance, IMU_REG_BANDWIDTH, value, 0U);
}

IMUState IMU_SetAlgorithm(uint8_t instance, IMUAlgorithm algorithm)
{
    IMUState state;
    uint16_t value;

    state = IMU_AlgorithmToValue(algorithm, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return IMU_WriteRegister(instance, IMU_REG_AXIS6, value, 0U);
}

IMUState IMU_SetInstallationOrientation(uint8_t instance, uint16_t orient_value, uint32_t timeout_ms)
{
    IMUState state;
    uint32_t start_tick;

    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    IMU_OrientationConfigStatusSet(instance, 1U, 0U);
    if ((orient_value != IMU_ORIENT_HORIZONTAL_VALUE) &&
        (orient_value != IMU_ORIENT_VERTICAL_VALUE))
    {
        return IMU_RESP_INVALID;
    }
    if (timeout_ms < IMU_ORIENT_WRITE_MIN_TIMEOUT_MS)
    {
        return IMU_RESP_TIMEOUT;
    }

    start_tick = PlatformTime_Ms();
    state = IMU_WriteRegister(instance, IMU_REG_ORIENT, orient_value, 0U);
    if ((state == IMU_OK) &&
        ((PlatformTime_Ms() - start_tick) > timeout_ms))
    {
        state = IMU_RESP_TIMEOUT;
    }
    if (state == IMU_OK)
    {
        IMU_ConfigCacheSetField(instance, IMU_CONFIG_VALID_ORIENTATION, orient_value);
        IMU_OrientationConfigStatusSet(instance, 1U, 1U);
    }

    return state;
}

IMUState IMU_SetGyroRange(uint8_t instance, IMUGyroRange range)
{
    IMUState state;
    uint16_t value;

    state = IMU_GyroRangeToValue(range, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return IMU_WriteRegister(instance, IMU_REG_GYRORANGE, value, 0U);
}

IMUState IMU_SetAccelRange(uint8_t instance, IMUAccelRange range)
{
    IMUState state;
    uint16_t value;

    state = IMU_AccelRangeToValue(range, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return IMU_WriteRegister(instance, IMU_REG_ACCRANGE, value, 0U);
}

IMUState IMU_EnsureAlgorithm6Axis(uint8_t instance)
{
    IMUState state;
    uint16_t value = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    state = IMU_ReadAlgorithm(instance, &value);
    if ((state == IMU_OK) && (value == IMU_ALGORITHM_6_AXIS_VALUE))
    {
        return IMU_OK;
    }

    state = IMU_SetAlgorithm(instance, Algorithm_6Axis);
    if (state != IMU_OK)
    {
        return state;
    }

    state = IMU_ReadAlgorithm(instance, &value);
    if (state != IMU_OK)
    {
        return state;
    }

    return (value == IMU_ALGORITHM_6_AXIS_VALUE) ? IMU_OK : IMU_RESP_INVALID;
}

IMUState IMU_HardwareZeroZ(uint8_t instance)
{
    IMUState state;

    state = IMU_EnsureAlgorithm6Axis(instance);
    if (state != IMU_OK)
    {
        s_lastHardwareZeroZResult = state;
        return state;
    }

    /*
     * JY901B/WitMotion CALSW register: 0x0004 resets heading/Z-axis angle.
     * The lower write helper already uses finite UART timeouts and restarts DMA RX.
     */
    state = IMU_WriteRegister(instance, IMU_REG_CALSW, IMU_CALSW_Z_AXIS_ZERO, 0U);
    s_lastHardwareZeroZResult = state;
    return state;
}

IMUState IMU_GetLastHardwareZeroZResult(uint8_t instance)
{
    return s_lastHardwareZeroZResult;
}

IMUState IMU_SetFusionFilter(uint8_t instance, uint16_t filter_value)
{
    return IMU_WriteFilterRegister(instance, IMU_REG_FILTK, filter_value);
}

IMUState IMU_SetAccelerationFilter(uint8_t instance, uint16_t filter_value)
{
    return IMU_WriteFilterRegister(instance, IMU_REG_ACCFILT, filter_value);
}

IMUState IMU_SetReturnContent(uint8_t instance, uint16_t rsw)
{
    return IMU_WriteRegister(instance, IMU_REG_RSW, rsw, 0U);
}

void IMU_StreamDiagnosticsGet(uint8_t instance, IMUStreamDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return; }
    diagnostics->valid_frame_count = s_validFrameCount;
    diagnostics->checksum_error_count = s_checksumErrorCount;
    diagnostics->parser_resync_count = s_parserResyncCount;
    diagnostics->process_limit_count = s_processLimitCount;
}

IMUState IMU_EnsureQuaternionOutput(uint8_t instance)
{
    IMUState state;
    uint16_t rsw;
    uint16_t target_rsw;

    SILVERSTAR_ASSERT_OBJECT(&s_config_cache, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    state = IMU_ReadReturnContent(instance, &rsw);
    if (state != IMU_OK)
    {
        return state;
    }

    if (((rsw & FC_IMU_RETURN_CONTENT_DEFAULT) == FC_IMU_RETURN_CONTENT_DEFAULT) &&
        ((rsw & FC_IMU_RETURN_CONTENT_QUAT_MASK) != 0U))
    {
        IMU_ConfigCacheSetField(instance, IMU_CONFIG_VALID_RETURN_CONTENT, rsw);
        return IMU_OK;
    }

    target_rsw = (uint16_t)(rsw |
                            FC_IMU_RETURN_CONTENT_DEFAULT |
                            FC_IMU_RETURN_CONTENT_QUAT_MASK);
    state = IMU_SetReturnContent(instance, target_rsw);
    if (state != IMU_OK)
    {
        return state;
    }

    state = IMU_ReadReturnContent(instance, &rsw);
    if (state != IMU_OK)
    {
        return state;
    }

    IMU_ConfigCacheSetField(instance, IMU_CONFIG_VALID_RETURN_CONTENT, rsw);
    return (((rsw & FC_IMU_RETURN_CONTENT_DEFAULT) == FC_IMU_RETURN_CONTENT_DEFAULT) &&
            ((rsw & FC_IMU_RETURN_CONTENT_QUAT_MASK) != 0U)) ? IMU_OK : IMU_RESP_INVALID;
}

IMUState IMU_SaveConfig(uint8_t instance)
{
    IMUState state;

    if (PlatformUart_RxStop(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    {
        return IMU_ReceiveResume(instance, IMU_UART_RX_ERROR);
    }

    state = IMU_SendConfigFrame(instance, IMU_REG_KEY, IMU_KEY_UNLOCK);
    if (state != IMU_OK)
    {
        return IMU_ReceiveResume(instance, state);
    }
    PlatformTime_DelayMs(IMU_CFG_UNLOCK_DELAY_MS);

    state = IMU_SendConfigFrame(instance, IMU_REG_SAVE, 0x0000U);
    PlatformTime_DelayMs(IMU_CFG_SAVE_DELAY_MS);
    return IMU_ReceiveResume(instance, state);
}

IMUState IMU_ReadBaudrate(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_BAUD, value);
}

IMUState IMU_ReadOutputRate(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_RRATE, value);
}

IMUState IMU_ReadBandwidth(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_BANDWIDTH, value);
}

IMUState IMU_ReadAlgorithm(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_AXIS6, value);
}

IMUState IMU_ReadInstallationOrientation(uint8_t instance, uint16_t *value, uint32_t timeout_ms)
{
    IMUState state;
    uint32_t start_tick;

    if (value == NULL)
    {
        return IMU_NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(value, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (timeout_ms < IMU_ORIENT_READ_MIN_TIMEOUT_MS)
    {
        return IMU_RESP_TIMEOUT;
    }

    start_tick = PlatformTime_Ms();
    state = IMU_ReadRegister(instance, IMU_REG_ORIENT, value);
    if ((state == IMU_OK) &&
        ((PlatformTime_Ms() - start_tick) > timeout_ms))
    {
        return IMU_RESP_TIMEOUT;
    }
    if ((state == IMU_OK) && (*value != IMU_ORIENT_HORIZONTAL_VALUE) &&
        (*value != IMU_ORIENT_VERTICAL_VALUE))
    {
        return IMU_RESP_INVALID;
    }

    return state;
}

IMUState IMU_ReadGyroRange(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_GYRORANGE, value);
}

IMUState IMU_ReadAccelRange(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_ACCRANGE, value);
}

IMUState IMU_ReadFusionFilter(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_FILTK, value);
}

IMUState IMU_ReadAccelerationFilter(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_ACCFILT, value);
}

IMUState IMU_ReadReturnContent(uint8_t instance, uint16_t *value)
{
    return IMU_ReadRegister(instance, IMU_REG_RSW, value);
}

static IMUState IMU_CurrentConfigPrimaryRead(uint8_t instance, IMUConfig *config)
{
    IMUState state;

    if (config == NULL) { return IMU_NULL; }
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    state = IMU_ReadBaudrate(instance, &config->BaudrateValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadOutputRate(instance, &config->OutputRateValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadBandwidth(instance, &config->BandwidthValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadAlgorithm(instance, &config->AlgorithmValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadInstallationOrientation(instance, &config->OrientationValue,
                                            IMU_ORIENT_READ_TIMEOUT_MS);
    return state;
}

static IMUState IMU_CurrentConfigSensorRead(uint8_t instance, IMUConfig *config)
{
    IMUState state;

    if (config == NULL) { return IMU_NULL; }
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    state = IMU_ReadGyroRange(instance, &config->GyroRangeValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadAccelRange(instance, &config->AccelRangeValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadFusionFilter(instance, &config->FusionFilterValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadAccelerationFilter(instance, &config->AccelerationFilterValue);
    if (state != IMU_OK) { return state; }
    state = IMU_ReadReturnContent(instance, &config->ReturnContentValue);
    return state;
}

IMUState IMU_ReadCurrentConfig(uint8_t instance, IMUConfig *config)
{
    IMUState state;

    if (config == NULL) { return IMU_NULL; }
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(config, 0, sizeof(*config));
    config->OrientationConfigAttempted =
        s_config_cache.OrientationConfigAttempted;
    config->OrientationConfigOk = s_config_cache.OrientationConfigOk;
    state = IMU_CurrentConfigPrimaryRead(instance, config);
    if (state != IMU_OK) { return state; }
    state = IMU_CurrentConfigSensorRead(instance, config);
    if (state != IMU_OK) { return state; }
    config->ValidMask = IMU_CONFIG_VALID_ALL;
    IMU_ConfigCacheSetAll(instance, config);
    return IMU_OK;
}

static void IMU_PartialFieldStore(uint8_t instance, IMUConfig *config,
                                  uint16_t *field,
                                  uint16_t valid_mask,
                                  uint16_t value,
                                  IMUState state,
                                  IMUState *last_error)
{
    if ((config == NULL) || (field == NULL) || (last_error == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(last_error, IMUState,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (state == IMU_OK)
    {
        *field = value;
        config->ValidMask |= valid_mask;
        IMU_ConfigCacheSetField(instance, valid_mask, value);
    }
    else
    {
        *last_error = state;
    }
}

IMUState IMU_ReadCurrentConfigPartial(uint8_t instance, IMUConfig *config, uint32_t *elapsed_ms)
{
    IMUState state;
    IMUState last_error = IMU_RESP_TIMEOUT;
    uint16_t value = 0U;
    uint32_t start_tick;

    if (config == NULL) { return IMU_NULL; }
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    start_tick = PlatformTime_Ms();
    (void)memset(config, 0, sizeof(*config));
    config->OrientationConfigAttempted = s_config_cache.OrientationConfigAttempted;
    config->OrientationConfigOk = s_config_cache.OrientationConfigOk;

    state = IMU_ReadBaudrate(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->BaudrateValue,
        IMU_CONFIG_VALID_BAUD, value, state, &last_error);
    state = IMU_ReadOutputRate(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->OutputRateValue,
        IMU_CONFIG_VALID_RATE, value, state, &last_error);
    state = IMU_ReadBandwidth(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->BandwidthValue,
        IMU_CONFIG_VALID_BANDWIDTH, value, state, &last_error);
    state = IMU_ReadAlgorithm(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->AlgorithmValue,
        IMU_CONFIG_VALID_ALGORITHM, value, state, &last_error);
    state = IMU_ReadInstallationOrientation(instance, &value, IMU_ORIENT_READ_TIMEOUT_MS);
    IMU_PartialFieldStore(instance, config, &config->OrientationValue,
        IMU_CONFIG_VALID_ORIENTATION, value, state, &last_error);
    state = IMU_ReadGyroRange(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->GyroRangeValue,
        IMU_CONFIG_VALID_GYRO_RANGE, value, state, &last_error);
    state = IMU_ReadAccelRange(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->AccelRangeValue,
        IMU_CONFIG_VALID_ACCEL_RANGE, value, state, &last_error);
    state = IMU_ReadFusionFilter(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->FusionFilterValue,
        IMU_CONFIG_VALID_FUSION_FILTER, value, state, &last_error);
    state = IMU_ReadAccelerationFilter(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->AccelerationFilterValue,
        IMU_CONFIG_VALID_ACCEL_FILTER, value, state, &last_error);
    state = IMU_ReadReturnContent(instance, &value);
    IMU_PartialFieldStore(instance, config, &config->ReturnContentValue,
        IMU_CONFIG_VALID_RETURN_CONTENT, value, state, &last_error);

    if (elapsed_ms != NULL)
    {
        *elapsed_ms = PlatformTime_Ms() - start_tick;
    }

    return (config->ValidMask != 0U) ? IMU_OK : last_error;
}
