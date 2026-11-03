#ifndef __SYSTEM_MAG_ROTATION_IF_H
#define __SYSTEM_MAG_ROTATION_IF_H
#include <stdint.h>
#include "system_magnetometer_if.h"
#ifndef SYSTEM_MAG_ROTATION_ENABLED
#define SYSTEM_MAG_ROTATION_ENABLED 0U
#endif
void SystemMagRotation_ImuObserve(uint32_t source, uint32_t epoch, uint32_t sequence, uint32_t edge,
                                  uint64_t ready_us, const float gyro_radps[3], uint8_t frame_ok);
void SystemMagRotation_MagObserve(const SystemMagnetometerSample *sample, uint64_t trigger_us,
                                  uint64_t available_us);
void SystemMagRotation_SourceLost(void);
void SystemMagRotation_Service(uint64_t now_us);
void SystemMagRotation_StatusWrite(char *response, uint16_t capacity);
uint8_t SystemMagRotation_ProviderQualified(float R_GA[9]);
uint8_t SystemMagRotation_TryApply(uint8_t instance, uint32_t generation, uint32_t crc,
                                   uint32_t sequence, uint64_t sample_us, float field[3]);
#endif
