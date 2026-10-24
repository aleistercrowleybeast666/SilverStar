#ifndef __CAPTURE_PORT_H
#define __CAPTURE_PORT_H
#include <stdint.h>
uint8_t CapturePort_Try(volatile uint8_t *gate);
void CapturePort_Leave(volatile uint8_t *gate);
uint8_t CapturePort_LostTake(volatile uint8_t *flag);
void CapturePort_LostSet(volatile uint8_t *flag);
uint32_t CapturePort_WordTake(volatile uint32_t *value);
uint32_t CapturePort_WordRead(const volatile uint32_t *value);
void CapturePort_WordSet(volatile uint32_t *value,uint32_t token);
uint8_t CapturePort_WordPublish(volatile uint32_t *value,uint32_t token);
#endif
