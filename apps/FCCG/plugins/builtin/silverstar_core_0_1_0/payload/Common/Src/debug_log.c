#include "debug_log.h"
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
#include "system_console_if.h"
#endif
#include "system_user_config.h"
#include "common_format.h"
#include "silverstar_assert.h"
#include <stdarg.h>
#include <string.h>

void DebugLog_Init(void)
{
}

uint16_t DebugLog_Write(const uint8_t *data, uint16_t len)
{
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    if (SystemConsoleDevice_Write(data, len) != SYSTEM_DEVICE_OK)
    {
        return 0U;
    }
    return len;
#else
    (void)data;
    (void)len;
    return 0U;
#endif
}

uint16_t DebugLog_WritePriority(const uint8_t *data, uint16_t len)
{
    return DebugLog_Write(data, len);
}

void DebugLog_Print(const char *fmt, ...)
{
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    char buf[SYSTEM_DEBUG_LOG_LINE_SIZE];
    int len = 0;
    va_list ap;

    if ((SYSTEM_DEBUG_LOG_ENABLE == 0U) || (fmt == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(fmt, char, SILVERSTAR_ASSERT_MODULE_COMMON);

    len = CommonFormat_Print(buf, sizeof(buf), "%s", SYSTEM_DEBUG_LOG_PREFIX);
    if (len < 0)
    {
        return;
    }

    va_start(ap, fmt);
    len += CommonFormat_VPrint(&buf[len], sizeof(buf) - (size_t)len, fmt, ap);
    va_end(ap);

    if (len < 0)
    {
        return;
    }

    if ((size_t)len >= sizeof(buf))
    {
        len = (int)(sizeof(buf) - 1U);
        buf[len] = '\0';
    }

    if ((SYSTEM_DEBUG_LOG_AUTO_CRLF != 0U) &&
        ((len + 2) < (int)sizeof(buf)))
    {
        if ((len < 2) || !(buf[len - 2] == '\r' && buf[len - 1] == '\n'))
        {
            buf[len++] = '\r';
            buf[len++] = '\n';
            buf[len] = '\0';
        }
    }
    (void)DebugLog_Write((const uint8_t *)buf, (uint16_t)len);
#else
    (void)fmt;
#endif
}

uint16_t DebugLog_Read(uint8_t *data, uint16_t len)
{
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    uint16_t read_length = 0U;

    if (SystemConsoleDevice_Read(data, len, &read_length) == SYSTEM_DEVICE_OK)
    {
        return read_length;
    }
    return 0U;
#else
    (void)data;
    (void)len;
    return 0U;
#endif
}

uint16_t DebugLog_GetRxCount(void)
{
    return 0U;
}

uint16_t DebugLog_GetDiscarded(void)
{
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    SystemConsoleHealth health;

    if (SystemConsoleDevice_HealthGet(&health) == SYSTEM_DEVICE_OK)
    {
        return (uint16_t)health.transmit_error_count;
    }
    return 0U;
#else
    return 0U;
#endif
}

void DebugLog_ResetDiscarded(void)
{
    /* Device health counters are monotonic by contract. */
}

