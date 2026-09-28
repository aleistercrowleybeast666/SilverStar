#define main UbxReceiverTests_Main
#include "test_ubx_receiver.c"
#undef main
#include "ubx_system_adapter.h"
#include "platform_time.h"
#include "platform_critical.h"

static MockReceiver s_mock;
static UbxSystemAdapter *s_adapter;
static uint64_t s_now;
static uint32_t s_epoch;
static uint8_t s_silent;

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t PlatformTime_Us(void) { return s_now; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_now += (uint64_t)delay_ms * 1000U; }
PlatformResult PlatformUart_Init(PlatformUartId id) { (void)id; return PLATFORM_OK; }
PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baud)
{ (void)id; s_mock.host_baud = baud; return PLATFORM_OK; }
PlatformResult PlatformUart_RxFlush(PlatformUartId id) { (void)id; return PLATFORM_OK; }
PlatformResult PlatformUart_Write(PlatformUartId id, const uint8_t *bytes, uint16_t length, uint32_t timeout)
{ (void)id; (void)timeout; return Mock_Send(&s_mock, bytes, length) == UBX_RECEIVER_OK ? PLATFORM_OK : PLATFORM_IO_ERROR; }
PlatformResult PlatformUart_Read(PlatformUartId id, uint8_t *bytes, uint16_t capacity, uint16_t *count)
{ (void)id; (void)bytes; (void)capacity; *count = 0U; return PLATFORM_OK; }
void PlatformUart_Process(PlatformUartId id)
{
    (void)id;
    if (s_silent) { s_mock.sent_length = 0U; return; }
    Mock_Pump(&s_adapter->receiver, &s_mock);
    if (s_adapter->receiver.state == UBX_RECEIVER_VERIFY_SAMPLE)
    { s_epoch += 1000U; assert(Mock_Pvt(&s_adapter->receiver, s_epoch) == UBX_RECEIVER_OK); }
}
SystemDeviceResult SystemGnssQuality_Evaluate(SystemGnssSample *sample, uint64_t now)
{ (void)sample; (void)now; return SYSTEM_DEVICE_OK; }

static void Adapter_Init(UbxSystemAdapter *adapter, UbxReceiverModel model)
{
    s_adapter = adapter; s_now = 0U; s_epoch = 0U; s_silent = 0U;
    Mock_Factory(&s_mock, UbxReceiver_ProfileGet(model));
    assert(UbxSystemAdapter_Init(adapter, PLATFORM_UART_1, model) == SYSTEM_DEVICE_OK);
    adapter->started = 1U;
    for (unsigned i = 0U; i < 10000U && adapter->receiver.state != UBX_RECEIVER_READY; i++)
    { SystemDeviceResult r = UbxSystemAdapter_Process(adapter); assert(r == SYSTEM_DEVICE_OK || r == SYSTEM_DEVICE_NOT_READY); PlatformTime_DelayMs(1U); }
    assert(adapter->receiver.state == UBX_RECEIVER_READY);
    assert(s_mock.nvm_writes == 0U);
}

static void Adapter_Test(UbxReceiverModel model)
{
    UbxSystemAdapter adapter;
    SystemGnssHardwareConfig hardware;
    SystemGnssConfig actual;
    SystemGnssConfigTransactionReport transaction;
    SystemDeviceConfigReport report;
    Adapter_Init(&adapter, model);
    uint32_t writes = s_mock.writes;
    uint32_t sends = s_mock.sends;
    assert(UbxSystemAdapter_HardwareConfigRead(&adapter, &hardware) == SYSTEM_DEVICE_OK);
    assert(s_mock.sends > sends && s_mock.writes == writes);
    assert(hardware.valid_mask == 0x7FU && hardware.transaction_id == 1U);
    assert(hardware.response_length != 0U && hardware.received_class == 6U);
    assert(hardware.baudrate == adapter.receiver.profile->target_baud);
    assert(UbxSystemAdapter_ConfigGet(&adapter, &actual) == SYSTEM_DEVICE_OK);
    assert(actual.navigation_rate_hz == 1000U / adapter.receiver.profile->measurement_ms);
    assert(UbxSystemAdapter_LastConfigReportGet(&adapter, &transaction) == SYSTEM_DEVICE_OK);
    assert(transaction.verify_result == SYSTEM_DEVICE_OK && transaction.verify_valid_mask == 0x7FU);
    assert(transaction.uart_settle_result == SYSTEM_DEVICE_NOT_EXECUTED);
    adapter.owner_active = 1U;
    assert(UbxSystemAdapter_HardwareConfigRead(&adapter, &hardware) == SYSTEM_DEVICE_BUSY);
    assert(UbxSystemAdapter_ConfigPersist(&adapter, UBX_RECEIVER_LAYER_BBR, &report) == SYSTEM_DEVICE_BUSY);
    adapter.owner_active = 0U;
    if (model == UBX_RECEIVER_NEO_M8N)
    { assert(UbxSystemAdapter_ConfigPersist(&adapter, UBX_RECEIVER_LAYER_BBR, &report) == SYSTEM_DEVICE_UNSUPPORTED); }
    else
    {
        assert(UbxSystemAdapter_ConfigPersist(&adapter, UBX_RECEIVER_LAYER_BBR, &report) == SYSTEM_DEVICE_OK);
        assert(report.persisted == 1U && report.success == 1U && s_mock.nvm_writes != 0U);
        uint32_t nvm = s_mock.nvm_writes;
        assert(UbxSystemAdapter_ConfigPersist(&adapter, UBX_RECEIVER_LAYER_BBR, &report) == SYSTEM_DEVICE_OK);
        assert(s_mock.nvm_writes == nvm);
    }
    writes = s_mock.writes;
    if (model == UBX_RECEIVER_NEO_M8N) { s_mock.legacy[0][0] = 0xE8U; s_mock.legacy[0][1] = 3U; }
    else { s_mock.values[0][3] = 1000U; }
    assert(UbxSystemAdapter_HardwareConfigRead(&adapter, &hardware) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(s_mock.writes == writes && adapter.maintenance_owner == 0U);
    assert(adapter.receiver.readback.measurement_ms == 1000U);
    assert(UbxSystemAdapter_ConfigGet(&adapter, &actual) == SYSTEM_DEVICE_NOT_READY);
    Adapter_Init(&adapter, model); s_silent = 1U; writes = s_mock.writes;
    assert(UbxSystemAdapter_HardwareConfigRead(&adapter, &hardware) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(hardware.read_result == SYSTEM_GNSS_CONFIG_READ_TIMEOUT && hardware.valid_mask == 0U);
    assert(s_mock.writes == writes && adapter.maintenance_owner == 0U);
    printf("%s: adapter fresh read/response evidence/zero-write mismatch/timeout/explicit persistence PASS\n", adapter.receiver.profile->model);
}

int main(void)
{
    assert(UbxReceiverTests_Main() == 0);
    for (int model = 0; model < UBX_RECEIVER_MODEL_COUNT; model++) { Adapter_Test((UbxReceiverModel)model); }
    return 0;
}
