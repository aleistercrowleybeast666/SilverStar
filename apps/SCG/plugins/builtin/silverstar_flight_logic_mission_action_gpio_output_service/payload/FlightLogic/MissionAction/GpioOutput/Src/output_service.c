#include "system_output_if.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "mission_action_output_config.h"
#include "platform_critical.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "silverstar_assert.h"

#define OUTPUT_CHANNEL_CAPACITY 2U

typedef struct
{
    PlatformGpioId gpio;
    uint64_t deactivate_at_us;
    SystemOutputStatus status;
} GpioOutputChannel;

static GpioOutputChannel s_channels[OUTPUT_CHANNEL_CAPACITY];
static volatile uint8_t s_initialized;

static uint8_t SilverStarOutputService_ChannelAvailable(uint8_t channel)
{
    if (channel == MISSION_ACTION_START_OUTPUT_CHANNEL)
    {
        return PROJECT_FEATURE_LAUNCH_IGNITION_OUTPUT;
    }
    if (channel == MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL)
    {
        return PROJECT_FEATURE_PARACHUTE_PYRO_OUTPUT;
    }
    return 0U;
}

static uint32_t SilverStarOutputService_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SilverStarOutputService_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static GpioOutputChannel *SilverStarOutputService_ChannelGet(uint8_t channel)
{
    if ((channel == 0U) || (channel > OUTPUT_CHANNEL_CAPACITY) ||
        (SilverStarOutputService_ChannelAvailable(channel) == 0U))
    {
        return NULL;
    }
    return &s_channels[channel - 1U];
}

static void SilverStarOutputService_ChannelSafe(GpioOutputChannel *channel)
{
    (void)PlatformGpio_Write(channel->gpio, 0U);
    channel->deactivate_at_us = 0ULL;
    channel->status.timestamp_us = PlatformTime_Us();
    channel->status.sequence++;
    channel->status.requested_duration_ms = 0U;
    channel->status.remaining_duration_ms = 0U;
    channel->status.state = SYSTEM_OUTPUT_SAFE;
    channel->status.commanded_active = 0U;
    channel->status.physical_active = 0U;
    channel->status.fault = 0U;
}

static SystemDeviceResult SilverStarOutputService_Init(void)
{
    uint32_t primask;

    SILVERSTAR_ASSERT(PROJECT_FEATURE_LAUNCH_IGNITION_OUTPUT <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(PROJECT_FEATURE_PARACHUTE_PYRO_OUTPUT <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    primask = SilverStarOutputService_IrqLock();
    (void)memset(s_channels, 0, sizeof(s_channels));
    s_channels[0].gpio = PROJECT_RESOURCE_LAUNCH_IGNITION_OUTPUT;
    s_channels[0].status.channel = 1U;
    s_channels[1].gpio = PROJECT_RESOURCE_PARACHUTE_PYRO_OUTPUT;
    s_channels[1].status.channel = 2U;
    s_initialized = 1U;
    if (PROJECT_FEATURE_LAUNCH_IGNITION_OUTPUT != 0U)
    {
        SilverStarOutputService_ChannelSafe(&s_channels[0]);
    }
    if (PROJECT_FEATURE_PARACHUTE_PYRO_OUTPUT != 0U)
    {
        SilverStarOutputService_ChannelSafe(&s_channels[1]);
    }
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarOutputService_SetSafe(void)
{
    uint32_t primask;
    uint8_t index;

    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    primask = SilverStarOutputService_IrqLock();
    for (index = 0U; index < OUTPUT_CHANNEL_CAPACITY; index++)
    {
        if (SilverStarOutputService_ChannelAvailable(index + 1U) != 0U)
        {
            SilverStarOutputService_ChannelSafe(&s_channels[index]);
        }
    }
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarOutputService_Arm(uint8_t channel)
{
    GpioOutputChannel *output = SilverStarOutputService_ChannelGet(channel);
    uint32_t primask;

    if (output == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    SILVERSTAR_ASSERT_OBJECT(output, GpioOutputChannel,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    primask = SilverStarOutputService_IrqLock();
    if (output->status.fault != 0U)
    {
        SilverStarOutputService_IrqUnlock(primask);
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (output->status.state == SYSTEM_OUTPUT_ARMED)
    {
        SilverStarOutputService_IrqUnlock(primask);
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    if (output->status.state != SYSTEM_OUTPUT_SAFE)
    {
        SilverStarOutputService_IrqUnlock(primask);
        return SYSTEM_DEVICE_BAD_STATE;
    }
    output->status.timestamp_us = PlatformTime_Us();
    output->status.sequence++;
    output->status.state = SYSTEM_OUTPUT_ARMED;
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarOutputService_Activate(uint8_t channel,
                                                       uint32_t duration_ms)
{
    GpioOutputChannel *output = SilverStarOutputService_ChannelGet(channel);
    uint64_t now_us;
    uint32_t primask;

    if ((output == NULL) || (duration_ms == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(output, GpioOutputChannel,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    primask = SilverStarOutputService_IrqLock();
    if (output->status.state != SYSTEM_OUTPUT_ARMED)
    {
        SilverStarOutputService_IrqUnlock(primask);
        return SYSTEM_DEVICE_BAD_STATE;
    }

    now_us = PlatformTime_Us();
    if (PlatformGpio_Write(output->gpio, 1U) != PLATFORM_OK)
    {
        SilverStarOutputService_IrqUnlock(primask);
        return SYSTEM_DEVICE_IO_ERROR;
    }
    output->deactivate_at_us = now_us + ((uint64_t)duration_ms * 1000ULL);
    output->status.timestamp_us = now_us;
    output->status.sequence++;
    output->status.requested_duration_ms = duration_ms;
    output->status.remaining_duration_ms = duration_ms;
    output->status.state = SYSTEM_OUTPUT_ACTIVE;
    output->status.commanded_active = 1U;
    output->status.physical_active = 1U;
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarOutputService_Deactivate(uint8_t channel)
{
    GpioOutputChannel *output = SilverStarOutputService_ChannelGet(channel);
    uint32_t primask;

    if (output == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    primask = SilverStarOutputService_IrqLock();
    SilverStarOutputService_ChannelSafe(output);
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarOutputService_GetStatus(
    uint8_t channel,
    SystemOutputStatus *status)
{
    GpioOutputChannel *output = SilverStarOutputService_ChannelGet(channel);
    uint64_t now_us;
    uint32_t primask;

    if ((output == NULL) || (status == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemOutputStatus,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    primask = SilverStarOutputService_IrqLock();
    now_us = PlatformTime_Us();
    if ((output->status.state == SYSTEM_OUTPUT_ACTIVE) &&
        (output->deactivate_at_us > now_us))
    {
        output->status.remaining_duration_ms = (uint32_t)
            ((output->deactivate_at_us - now_us + 999ULL) / 1000ULL);
    }
    *status = output->status;
    SilverStarOutputService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static void SilverStarOutputService_Process(void)
{
    uint64_t now_us;
    uint32_t primask;
    uint8_t index;

    if (s_initialized == 0U) { return; }
    primask = SilverStarOutputService_IrqLock();
    now_us = PlatformTime_Us();
    for (index = 0U; index < OUTPUT_CHANNEL_CAPACITY; index++)
    {
        if ((SilverStarOutputService_ChannelAvailable(index + 1U) != 0U) &&
            (s_channels[index].status.state == SYSTEM_OUTPUT_ACTIVE) &&
            (now_us >= s_channels[index].deactivate_at_us))
        {
            SilverStarOutputService_ChannelSafe(&s_channels[index]);
        }
    }
    SilverStarOutputService_IrqUnlock(primask);
}

const char *SystemOutput_NameGet(void) { return "GPIO Output"; }
SystemDeviceResult SystemOutput_Init(void) { return SilverStarOutputService_Init(); }
SystemDeviceResult SystemOutput_SafeSet(void)
{ return SilverStarOutputService_SetSafe(); }
SystemDeviceResult SystemOutput_Arm(uint8_t channel)
{ return SilverStarOutputService_Arm(channel); }
SystemDeviceResult SystemOutput_Activate(uint8_t channel,
                                         uint32_t duration_ms)
{ return SilverStarOutputService_Activate(channel, duration_ms); }
SystemDeviceResult SystemOutput_Deactivate(uint8_t channel)
{ return SilverStarOutputService_Deactivate(channel); }
SystemDeviceResult SystemOutput_StatusGet(uint8_t channel,
                                          SystemOutputStatus *status)
{ return SilverStarOutputService_GetStatus(channel, status); }
void SystemOutput_Process(void) { SilverStarOutputService_Process(); }
