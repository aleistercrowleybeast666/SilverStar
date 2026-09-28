#ifndef __UBX_SYSTEM_ADAPTER_H
#define __UBX_SYSTEM_ADAPTER_H

#include "ubx_receiver.h"
#include "platform_uart.h"
#include "system_gnss_if.h"

typedef struct
{
    UbxReceiver receiver;
    PlatformUartId uart;
    SystemDeviceHealth health;
    UbxReceiverSample published;
    uint8_t started;
    uint8_t owner_active;
    uint8_t io_busy;
    uint8_t maintenance_owner;
} UbxSystemAdapter;

SystemDeviceResult UbxSystemAdapter_Init(UbxSystemAdapter *adapter,
    PlatformUartId uart, UbxReceiverModel model);
SystemDeviceResult UbxSystemAdapter_Process(UbxSystemAdapter *adapter);
SystemDeviceResult UbxSystemAdapter_SampleGet(UbxSystemAdapter *adapter,
    SystemGnssSample *sample);
SystemDeviceResult UbxSystemAdapter_ConfigGet(UbxSystemAdapter *adapter,
    SystemGnssConfig *config);
SystemDeviceResult UbxSystemAdapter_ConfigCheck(UbxSystemAdapter *adapter,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult UbxSystemAdapter_ConfigApply(UbxSystemAdapter *adapter,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult UbxSystemAdapter_HardwareConfigRead(UbxSystemAdapter *adapter,
    SystemGnssHardwareConfig *config);
SystemDeviceResult UbxSystemAdapter_LastConfigReportGet(UbxSystemAdapter *adapter,
    SystemGnssConfigTransactionReport *report);
SystemDeviceResult UbxSystemAdapter_ConfigPersist(UbxSystemAdapter *adapter,
    uint8_t persistent_layer, SystemDeviceConfigReport *report);
SystemDeviceResult UbxSystemAdapter_HealthGet(UbxSystemAdapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult UbxSystemAdapter_TimeGet(UbxSystemAdapter *adapter,
    SystemGnssTime *time);

#endif /* __UBX_SYSTEM_ADAPTER_H */
