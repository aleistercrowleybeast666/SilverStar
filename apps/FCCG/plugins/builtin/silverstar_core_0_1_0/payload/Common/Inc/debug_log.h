#ifndef __DEBUG_LOG_H
#define __DEBUG_LOG_H

#include <stdint.h>

void DebugLog_Init(void);

/* 原始字节发送 */
uint16_t DebugLog_Write(const uint8_t *data, uint16_t len);
uint16_t DebugLog_WritePriority(const uint8_t *data, uint16_t len);

/* 字符串日志 */
void DebugLog_Print(const char *fmt, ...);

/* 原始字节读取 */
uint16_t DebugLog_Read(uint8_t *data, uint16_t len);
uint16_t DebugLog_GetRxCount(void);

/* 获取丢弃的数据字节数 */
uint16_t DebugLog_GetDiscarded(void);

/* 置零丢弃的数据字节数 */
void DebugLog_ResetDiscarded(void);

#endif /* __DEBUG_LOG_H */
