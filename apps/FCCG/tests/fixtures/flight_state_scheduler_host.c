/* Real generated service, SX transport and radio driver. Only hardware ports
 * and unrelated flight subsystems are supplied by existing host fixtures. */
#include <stdio.h>
#include <string.h>
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
static TestFrame s_over_air[128];
static uint8_t s_over_air_count;
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout)
{
    (void)timeout;
    s_simulated_tx_end_ms = s_tick_ms + Lora_PacketAirtimeMs(instance, length);
    TEST_CHECK(length <= AIR_MAX_FRAME_LEN);
    TEST_CHECK(s_over_air_count < 128U);
    if ((length <= AIR_MAX_FRAME_LEN) && (s_over_air_count < 128U))
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

static uint8_t s_navigation_request = 1U;
static void Flight_Init(void)
{
    Radio_Init();
    s_over_air_count = 0U;
    s_simulated_tx_end_ms = 0U;
    s_estimator_available = 1U;
    s_capability_state = TELEMETRY_CAPABILITY_ACKED;
    s_gnss_state_known = 1U;
    s_gnss_position_usable = 0U;
    s_navigation_preparation.algorithm_id = 1U;
    s_navigation_preparation.initialized = 1U;
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    if (s_navigation_request != 0U)
    {
        Test_CommandQueue(20U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
        TEST_CHECK(Lora_RxQueuePush(0U, s_rx[s_rx_tail].data,
            (uint8_t)s_rx[s_rx_tail].length, -60, 3) != 0U);
        s_rx_tail = Test_Next(s_rx_tail, TEST_RX_DEPTH);
        TelemetryService_ReceiveProcess();
    }
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TelemetryService_PreflightDisable();
    s_next_stream_us = 0ULL;
}
static unsigned int Flight_Count(uint8_t type)
{
    unsigned int count = 0U;
    for (uint8_t i = 0U; i < s_over_air_count; i++)
    { if (s_over_air[i].data[0] == type) { count++; } }
    return count;
}
static void Flight_Run(uint32_t end_ms)
{
    for (uint32_t ms = 1U; ms <= end_ms; ms++)
    {
        Radio_Clock(ms);
        if ((s_simulated_tx_end_ms != 0U) && (ms >= s_simulated_tx_end_ms))
        { s_simulated_tx_end_ms = 0U; s_raw_irq = IRQ_TX_DONE; s_dio1_pending = 1U; }
        TelemetryService_Process();
        TEST_CHECK(((uint32_t)s_contexts[0].tx_count - (uint32_t)s_contexts[0].tx_control_count) <= 2U);
        TEST_CHECK(s_contexts[0].tx_count <= 8U);
    }
}
static void Flight_Contended(void)
{
    Flight_Init(); Flight_Run(14005U);
    printf("CONTENDED ms=14005 FLIGHT=%u NAV_HEALTH=%u NAV_CAP=%u NAV_PREP=%u queued=%u stream_deadline=%llu\n",
        Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH),
        Flight_Count(AIR_TYPE_NAV_CAPABILITY), Flight_Count(AIR_TYPE_NAV_PREPARATION),
        s_contexts[0].tx_count, (unsigned long long)s_next_stream_us);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_CAPABILITY) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_PREPARATION) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
    for (uint8_t i = 0U; i < s_over_air_count; i++)
    {
        if (s_over_air[i].data[0] != AIR_TYPE_FLIGHT_STATE) { continue; }
        TEST_CHECK(s_over_air[i].length == AIR_FLIGHT_STATE_LEN);
        printf("FLIGHT_HEX ");
        for (uint8_t j = 0U; j < s_over_air[i].length; j++) { printf("%02x", s_over_air[i].data[j]); }
        printf("\n");
    }
}
static void Flight_NoNavigation(void)
{
    s_navigation_request = 0U; Flight_Init(); Flight_Run(1500U);
    printf("NO_NAV FLIGHT=%u GNSS_USABLE=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), s_gnss_position_usable);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
}
static void Flight_Unavailable(void)
{
    Flight_Init(); s_estimator_available = 0U; Flight_Run(1500U);
    printf("NO_ESTIMATOR FLIGHT=%u NAV=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH));
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) == 0U);
    }
static void Flight_NoImu(void)
{
    Flight_Init(); s_imu_sample.valid_mask = 0U; Flight_Run(1500U);
    printf("NO_IMU FLIGHT=%u NAV=%u\n", Flight_Count(AIR_TYPE_FLIGHT_STATE), Flight_Count(AIR_TYPE_NAV_HEALTH));
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) == 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) == 0U);
}
static void Flight_Recovery(void)
{
    Flight_Init(); s_lifecycle_state = SYSTEM_STATE_RECOVERY; Flight_Run(1500U);
    TEST_CHECK(Flight_Count(AIR_TYPE_FLIGHT_STATE) > 0U);
    TEST_CHECK(Flight_Count(AIR_TYPE_NAV_HEALTH) == 0U);
}
static void Flight_OutsideMission(void)
{
    LoraTxPacket packet;
    static const SystemLifecycleState states[] = {SYSTEM_STATE_PREFLIGHT,
        SYSTEM_STATE_LANDED, SYSTEM_STATE_POSTFLIGHT, SYSTEM_STATE_FAULT};
    s_navigation_request = 0U; Flight_Init();
    for (uint8_t i = 0U; i < 4U; i++)
    {
        s_lifecycle_state = states[i]; Radio_Clock(1000U + 250U * i);
        TelemetryService_StreamSend();
        TEST_CHECK(s_contexts[0].tx_count == 0U);
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) == 0U);
        TEST_CHECK(s_next_stream_us == 0ULL);
    }
}

int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    if (strcmp(argv[1], "contended") == 0) { Flight_Contended(); }
    else if (strcmp(argv[1], "no_navigation") == 0) { Flight_NoNavigation(); }
    else if (strcmp(argv[1], "unavailable") == 0) { Flight_Unavailable(); }
    else if (strcmp(argv[1], "no_imu") == 0) { Flight_NoImu(); }
    else if (strcmp(argv[1], "recovery") == 0) { Flight_Recovery(); }
    else if (strcmp(argv[1], "outside_mission") == 0) { Flight_OutsideMission(); }
    else { return 2; }
    return Test_Finish(argv[1]);
}
