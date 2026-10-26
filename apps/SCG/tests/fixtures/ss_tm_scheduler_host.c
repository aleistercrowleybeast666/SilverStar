/* Real generated service, SX transport and radio driver. Only hardware ports
 * and unrelated flight subsystems are supplied by existing host fixtures. */
#include <stdio.h>
#include <string.h>
#include "stm32f4xx_hal.h"
/* Test-owned CubeMX handle. Keep it private in this amalgamated Host TU. */
static UART_HandleTypeDef huart3 = {
    .Init = {.BaudRate=230400U, .WordLength=UART_WORDLENGTH_8B,
        .StopBits=UART_STOPBITS_1, .Parity=UART_PARITY_NONE,
        .Mode=UART_MODE_TX_RX, .HwFlowCtl=UART_HWCONTROL_NONE},
    .Instance=USART3
};
#define main Test_TelemetryPreviousMain
#define SystemTelemetry_SendControl Test_PreviousSystemSendControl
#define SystemTelemetry_TxResultGet Test_PreviousSystemTxResultGet
#define SystemTelemetry_Send Test_PreviousSystemSend
#define SystemTelemetry_Receive Test_PreviousSystemReceive
#define SystemTelemetry_Process Test_PreviousSystemProcess
#define s_tx_count s_mock_tx_count
#define Estimator_GetLatestSnapshot Test_PreviousEstimatorSnapshot
#include "test_telemetry.c"
#undef Estimator_GetLatestSnapshot
#undef main
#undef SystemTelemetry_SendControl
#undef SystemTelemetry_TxResultGet
#undef SystemTelemetry_Send
#undef SystemTelemetry_Receive
#undef SystemTelemetry_Process
#undef s_tx_count
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280SendPayload Test_PreviousRadioSend
#define SX1280GetStatus Test_PreviousRadioStatus
#define Sx1281Bus_StatusGet Test_PreviousRadioBusStatus
#define Sx1281Bus_Init Test_PreviousRadioBusInit
#include "test_sx1281_device.c"
#undef SX1280SendPayload
#undef SX1280GetStatus
#undef Sx1281Bus_StatusGet
#undef Sx1281Bus_Init
static uint8_t s_radio_bus_failure;
static Sx1281BusStatus s_radio_bus_status;
void Sx1281Bus_Init(uint8_t instance)
{ (void)instance; memset(&s_radio_bus_status, 0, sizeof(s_radio_bus_status)); }
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{ (void)instance; *status = s_radio_bus_status; }
RadioStatus_t SX1280GetStatus(uint8_t instance)
{
    (void)instance; RadioStatus_t status; status.Value = 0x40U;
    if (s_radio_bus_failure != 0U)
    { s_radio_bus_status.spi_error_count++; s_radio_bus_status.last_result = SX1281_BUS_SPI_ERROR; }
    else { s_radio_bus_status.last_result = SX1281_BUS_OK; }
    return status;
}
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout);
#include "sx1281_device.c"
#undef s_tx_count
#undef s_tx_head
#undef s_tx_tail
#undef s_rx_count
#undef s_rx_head
#undef s_rx_tail
#include "sx1281_instance.h"
static uint32_t s_simulated_tx_end_ms;
static TestFrame s_over_air[1024];
static uint8_t s_frame_completed[1024];
static uint16_t s_over_air_count;
static uint8_t s_drop_start_ack;
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout)
{
    (void)timeout;
    s_simulated_tx_end_ms = s_tick_ms + Lora_PacketAirtimeMs(instance, length);
    if ((s_drop_start_ack != 0U) && (length == AIR_ACK_LEN) &&
        (SsTm_FrameTypeGet(data) == 0x40U) && (data[10] == AIR_CMD_START_MISSION))
    { s_simulated_tx_end_ms = 0U; s_drop_start_ack = 0U; }
    TEST_CHECK(length <= AIR_MAX_FRAME_LEN);
    TEST_CHECK(s_over_air_count < 1024U);
    if ((length <= AIR_MAX_FRAME_LEN) && (s_over_air_count < 1024U))
    { memcpy(s_over_air[s_over_air_count].data, data, length);
      s_over_air[s_over_air_count++].length = length; }
}
SystemDeviceResult SystemTelemetry_Send(const uint8_t *data, uint16_t length)
{ return Sx1281TelemetryInstance_Send(0U, data, length); }
SystemDeviceResult SystemTelemetry_Receive(uint8_t *data, uint16_t capacity, uint16_t *length)
{ return Sx1281TelemetryInstance_Receive(0U, data, capacity, length); }
void SystemTelemetry_Process(void) { (void)Sx1281TelemetryInstance_Process(0U); }
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
SystemDeviceResult SystemTelemetry_SendControl(const uint8_t *data, uint16_t length, uint32_t *id)
{ return Sx1281TelemetryInstance_SendControl(0U, data, length, id); }
SystemDeviceResult SystemTelemetry_TxResultGet(uint32_t id, uint32_t *age_ms)
{ return Sx1281TelemetryInstance_TxResultGet(0U, id, age_ms); }
#endif
static uint8_t s_estimator_available = 1U;
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    if ((snapshot == NULL) || (s_estimator_available == 0U)) { return 0U; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->initialized = 1U;
    snapshot->q_nb[0] = 1.0f;
    snapshot->velocity_enu_mps[0] = -0.0981511548f;
    snapshot->velocity_enu_mps[1] = 0.0991782993f;
    snapshot->velocity_enu_mps[2] = 0.0932015106f;
    snapshot->position_enu_m[0] = -0.467806935f;
    snapshot->position_enu_m[1] = 0.483857244f;
    snapshot->position_enu_m[2] = 0.072262131f;
    return 1U;
}

#include "platform_boot_session.h"
#include "system_power_if.h"
#include "system_storage_if.h"
#include "system_log_sink_if.h"
#include "project_device_instances.h"
PlatformResult PlatformBootSession_Get(uint32_t *session)
{ *session = 0x12345678UL; return PLATFORM_OK; }
SystemDeviceResult SystemTelemetry_ModeSet(SystemTelemetryMode mode)
{ return Sx1281TelemetryInstance_ModeSet(0U, mode); }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *mask)
{ *mask = SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT; return SYSTEM_DEVICE_OK; }
static SystemPowerSample s_power_sample;
static SystemLifecycleStartDiagnostic s_tm_mock_diagnostics[3];
uint8_t SystemLifecycle_GetLastStartDiagnostic(SystemStartSource source,
    SystemLifecycleStartDiagnostic *diagnostic)
{ *diagnostic = s_tm_mock_diagnostics[(uint8_t)source]; return diagnostic->valid; }
SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health)
{ (void)health; return SYSTEM_DEVICE_NOT_PRESENT; }
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample)
{ *sample = s_power_sample; return SYSTEM_DEVICE_OK; }
uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass kind)
{ (void)kind; return 0U; }
SystemDeviceResult ProjectDeviceInstance_HealthGet(SystemDeviceClass kind, uint8_t instance, SystemDeviceHealth *health)
{ (void)kind; (void)instance; (void)health; return SYSTEM_DEVICE_NOT_PRESENT; }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{ (void)health; return SYSTEM_DEVICE_NOT_PRESENT; }
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health)
{ (void)health; return SYSTEM_DEVICE_NOT_PRESENT; }
/* Explicit Host power-provider scenario. The generated H743 no-power build
 * separately verifies that its unconfigured provider is never linked/called. */
#undef SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE
#define SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE 1U
#include "telemetry_tm.c"
#include "telemetry_service.c"
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
#define s_capability_sequence s_capability_tx.latest_sequence
#endif
static void Radio_Clock(uint32_t ms)
{ s_tick_ms = ms; s_now_us = (uint64_t)ms * 1000ULL; }

static void Radio_Init(void)
{
    Test_Reset(); s_radio_bus_failure = 0U; Radio_Clock(0U);
    TEST_CHECK(Sx1281TelemetryInstance_Init(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(Sx1281TelemetryInstance_Start(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.SpreadingFactor == LORA_SF10);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.Bandwidth == LORA_BW_0800);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.CodingRate == LORA_CR_4_5);
    TEST_CHECK(s_contexts[0].pkt_params.Params.LoRa.PreambleLength == 0x18U);
    TEST_CHECK(s_contexts[0].pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON);
    TEST_CHECK(LORA_RF_FREQUENCY_HZ == AIR_LINK_FREQUENCY_HZ);
}


#include "project_resources.c"

static void Tm_ClockRun(uint32_t start, uint32_t end)
{
    for (uint32_t ms = start; ms <= end; ms++)
    {
        Radio_Clock(ms);
        if ((s_simulated_tx_end_ms != 0U) && (ms >= s_simulated_tx_end_ms))
        {
            s_simulated_tx_end_ms = 0U; s_raw_irq = IRQ_TX_DONE; s_dio1_pending = 1U;
            TEST_CHECK(s_over_air_count > 0U);
            s_frame_completed[s_over_air_count - 1U] = 1U;
        }
        TelemetryService_Process();
        TEST_CHECK(s_contexts[0].tx_count <= 1U);
    }
}

static uint32_t Tm_Count(uint8_t type)
{
    uint32_t count = 0U;
    for (uint16_t index = 0U; index < s_over_air_count; index++)
    { if ((s_frame_completed[index] != 0U) && (SsTm_FrameTypeGet(s_over_air[index].data) == type)) { count++; } }
    return count;
}

int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    Radio_Init();
    s_over_air_count = 0U;
    if (strcmp(argv[1], "preflight") == 0)
    {
        s_lifecycle_state = SYSTEM_STATE_READY;
        s_alignment_status_result = SYSTEM_DEVICE_OK;
        s_quaternion_available = 1U;
        s_capability_state = TELEMETRY_CAPABILITY_ACKED;
        /* Sustained admitted command feedback, in addition to the actual
         * preflight CAP/state/status/position/health service and RX grants. */
        for (uint32_t ms = 1U; ms < 20000U; ms += 100U)
        {
            (void)TelemetryService_AckRawQueue((TelemetrySequence)(ms & 0xFFFFU), AIR_CMD_PING, AIR_ACK_RESULT_OK, NULL);
            Tm_ClockRun(ms, ms + 99U);
        }
        printf("preflight profile=%u cap=%lu state=%lu health=%lu position=%lu ack=%lu completed=%lu\n",
            (unsigned int)SYSTEM_TELEMETRY_TM_PROFILE,(unsigned long)Tm_Count(0x12U),
            (unsigned long)Tm_Count(0x11U),(unsigned long)Tm_Count(0x19U),
            (unsigned long)Tm_Count(0x18U),(unsigned long)Tm_Count(0x40U),
            (unsigned long)s_diagnostics.completed_tx_count);
        TEST_CHECK(Tm_Count(0x12U) >= 8U); TEST_CHECK(Tm_Count(0x11U) >= 14U);
        TEST_CHECK(Tm_Count(0x19U) >= 7U); TEST_CHECK(Tm_Count(0x18U) >= 7U);
        TEST_CHECK(Tm_Count(0x40U) <= 20U);
        TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_HalfDuplex);
        return Test_Finish(argv[1]);
    }
    if (strcmp(argv[1], "lost_start_ack") == 0)
    {
        Radio_Clock(1000U);
        s_lifecycle_state = SYSTEM_STATE_FLIGHT;
        s_start_request_pending = 1U; s_start_cmd_sequence = 0xBEEFU;
        s_start_command.seq = s_start_cmd_sequence; s_start_command.cmd_id = AIR_CMD_START_MISSION;
        s_start_response.source = SYSTEM_START_SOURCE_AIR;
        s_start_response.request_id = s_start_cmd_sequence;
        s_start_response.result = SYSTEM_LIFECYCLE_START_OK;
        s_start_response.timestamp_us = s_now_us; s_start_response_pending = 1U;
        s_tm_mock_diagnostics[0].response = s_start_response;
        s_tm_mock_diagnostics[0].valid = 1U; s_tm_mock_diagnostics[0].sequence = 1U;
        s_drop_start_ack = 1U;
        Tm_ClockRun(1000U, 1100U);
        TEST_CHECK(s_tm_start_ack_completed == 0U);
        TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_HalfDuplex);
        Tm_ClockRun(1101U, 5000U);
        TEST_CHECK(s_diagnostics.failed_tx_count != 0U);
        TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_FLIGHT);
        if (SYSTEM_TELEMETRY_TM_PROFILE == 0U)
        { TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_TransmitOnly); }
        else { TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_HalfDuplex); }
        TEST_CHECK(Tm_Count(0x18U) != 0U);
        return Test_Finish(argv[1]);
    }
    if (strcmp(argv[1], "local_start") == 0)
    {
        s_lifecycle_state = SYSTEM_STATE_FLIGHT;
        s_tm_mock_diagnostics[2].valid = 1U;
        s_tm_mock_diagnostics[2].sequence = 11U;
        s_tm_mock_diagnostics[2].response.source = SYSTEM_START_SOURCE_LOCAL;
        s_tm_mock_diagnostics[2].response.result = SYSTEM_LIFECYCLE_START_OK;
        s_tm_mock_diagnostics[2].response.timestamp_us = 1000ULL;
        s_tm_mock_diagnostics[2].response.request_id = 0xBEEFU;
        Tm_ClockRun(500U, 5000U);
        uint8_t repeats = 0U;
        uint32_t identity = 0U;
        for (uint16_t index = 0U; index < s_over_air_count; index++)
        {
            const uint8_t *frame = s_over_air[index].data;
            if ((SsTm_FrameTypeGet(frame) == 0x20U) && (frame[20] == AIR_STATUS_MISSION_START))
            {
                uint32_t event_id = Test_GetU32Le(&frame[8]);
                if (repeats == 0U) { identity = event_id; }
                TEST_CHECK(event_id == identity);
                TEST_CHECK(Test_GetU32Le(&frame[12]) == 1000U);
                TEST_CHECK(Test_GetU32Le(&frame[16]) == 0U);
                TEST_CHECK(frame[28] == 0xEFU && frame[29] == 0xBEU);
                TEST_CHECK(frame[30] == SYSTEM_START_SOURCE_LOCAL);
                repeats++;
            }
        }
        TEST_CHECK(repeats == 3U);
        return Test_Finish(argv[1]);
    }
    if (strcmp(argv[1], "observations") == 0)
    {
        uint8_t frame[61], length = 0U;
        s_gnss_sample.valid_fields = SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HEIGHT;
        s_gnss_sample.position_usable = 1U; s_gnss_sample.online = 1U;
        s_gnss_sample.latitude_e7 = 0; s_gnss_sample.longitude_e7 = 0;
        s_gnss_sample.sample_timestamp_us = 1000000ULL;
        s_gnss_sample.receive_timestamp_us = 1100000ULL;
        s_gnss_sample.measurement_timestamp_trusted = 1U;
        s_gnss_sample.ellipsoid_height_mm = -100;
        s_power_sample.valid_mask = SYSTEM_POWER_VALID_VOLTAGE;
        s_power_sample.voltage_v = 0.0f; s_power_sample.sample_timestamp_us = 1000000ULL;
        TelemetryTm_Observe(1200000ULL);
        TEST_CHECK(TelemetryTm_PositionBuild(1200000ULL, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        TEST_CHECK(frame[26] == 15U); TEST_CHECK(Test_GetU32Le(&frame[20]) == 200U);
        s_gnss_sample.position_usable = 0U;
        TelemetryTm_Observe(7200000ULL);
        TEST_CHECK(TelemetryTm_PositionBuild(7200000ULL, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        TEST_CHECK(frame[26] == 27U); TEST_CHECK(Test_GetU32Le(&frame[20]) == 6200U);
        TEST_CHECK(TelemetryTm_HealthBuild(7200000ULL, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        TEST_CHECK(frame[8] == 0U && frame[9] == 0U);
        TEST_CHECK(frame[10] == 62U && frame[11] == 0U);
        TelemetryTm_Init();
        s_gnss_sample.position_usable = 1U; s_gnss_sample.sample_timestamp_us = 0U;
        s_gnss_sample.receive_timestamp_us = 0U; TelemetryTm_Observe(9000000ULL);
        TEST_CHECK(TelemetryTm_PositionBuild(9000000ULL, frame, sizeof(frame), &length) == AIR_BUILD_OK);
        TEST_CHECK(Test_GetU32Le(&frame[20]) == UINT32_MAX);
        TEST_CHECK((frame[26] & 8U) == 0U);
    }
    else
    {
        s_lifecycle_state = SYSTEM_STATE_FLIGHT;
        TelemetryService_PreflightDisable();
        if (strcmp(argv[1], "burst") == 0)
        {
            for (uint8_t index = 0U; index < 12U; index++)
            { TEST_CHECK(TelemetryService_StatusQueue(AIR_STATUS_MISSION_START, index, 0U, 3U) != 0U); }
        }
        else if (strcmp(argv[1], "landed") == 0)
        { s_lifecycle_state = SYSTEM_STATE_LANDED; }
        else if (strcmp(argv[1], "ack") == 0)
        {
            s_start_cmd_sequence = 0xBEEFU;
            TEST_CHECK(TelemetryService_AckRawQueue(s_start_cmd_sequence, AIR_CMD_START_MISSION, AIR_ACK_RESULT_OK, NULL) != 0U);
            Tm_ClockRun(1U, 500U);
            TEST_CHECK(s_tm_start_ack_completed != 0U);
            TEST_CHECK((SYSTEM_TELEMETRY_TM_PROFILE != 0U) || s_tm_mode_transmit_only != 0U);
        }
        uint32_t duration = strcmp(argv[1], "long") == 0 ? 60000U : 10000U;
        Tm_ClockRun(501U, duration);
        printf("TM profile=%u scenario=%s flight=%lu position=%lu health=%lu event=%lu completed=%lu failed=%lu mode=%u rx=%u\n",
            (unsigned int)SYSTEM_TELEMETRY_TM_PROFILE, argv[1], (unsigned long)Tm_Count(0x10U),
            (unsigned long)Tm_Count(0x18U), (unsigned long)Tm_Count(0x19U), (unsigned long)Tm_Count(0x20U),
            (unsigned long)s_diagnostics.completed_tx_count, (unsigned long)s_diagnostics.failed_tx_count,
            (unsigned int)Lora_OperatingModeGet(0U), (unsigned int)s_contexts[0].tx_count);
        if (strcmp(argv[1], "landed") == 0)
        { TEST_CHECK(Tm_Count(0x10U) == 0U); TEST_CHECK(Tm_Count(0x18U) >= 9U); TEST_CHECK(Tm_Count(0x19U) >= 2U); }
        else
        { TEST_CHECK(Tm_Count(0x10U) >= ((SYSTEM_TELEMETRY_TM_PROFILE == 0U) ? 43U : 16U));
          TEST_CHECK(Tm_Count(0x18U) >= ((SYSTEM_TELEMETRY_TM_PROFILE == 0U) ? 8U : 4U));
          TEST_CHECK(Tm_Count(0x19U) >= 4U); }
        if (SYSTEM_TELEMETRY_TM_PROFILE == 0U)
        { TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_TransmitOnly); }
        else { TEST_CHECK(Lora_OperatingModeGet(0U) == LoraOperatingMode_HalfDuplex); }
        if (duration == 60000U)
        {
            TEST_CHECK(Tm_Count(0x10U) >= ((SYSTEM_TELEMETRY_TM_PROFILE == 0U) ? 295U : 115U));
            TEST_CHECK(Tm_Count(0x18U) >= ((SYSTEM_TELEMETRY_TM_PROFILE == 0U) ? 59U : 29U));
            TEST_CHECK(Tm_Count(0x19U) >= 29U);
        }
        for (uint16_t index = 0U; index < s_over_air_count; index++)
        {
            TEST_CHECK(Air_FrameValidate(s_over_air[index].data, (uint8_t)s_over_air[index].length) == AIR_PARSE_OK);
        }
    }
    return Test_Finish(argv[1]);
}
