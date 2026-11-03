/* Test-only empty physical telemetry ports for unrelated isolated units. */
#include "system_mag_rotation_if.h"
#include <stddef.h>
void SystemMagRotation_ImuObserve(uint32_t source, uint32_t epoch, uint32_t sequence, uint32_t edge,
                                  uint64_t time, const float gyro[3], uint8_t valid)
{
    (void)source;
    (void)epoch;
    (void)sequence;
    (void)edge;
    (void)time;
    (void)gyro;
    (void)valid;
}
void SystemMagRotation_MagObserve(const SystemMagnetometerSample *sample, uint64_t start,
                                  uint64_t end)
{
    (void)sample;
    (void)start;
    (void)end;
}
void SystemMagRotation_SourceLost(void)
{
}
void SystemMagRotation_Service(uint64_t now)
{
    (void)now;
}
void SystemMagRotation_StatusWrite(char *response, uint16_t capacity)
{
    if (response != NULL && capacity)
    {
        response[0] = 0;
    }
}
uint8_t SystemMagRotation_TryApply(uint8_t instance, uint32_t generation, uint32_t crc,
                                   uint32_t seq, uint64_t stamp, float field[3])
{
    (void)instance;
    (void)generation;
    (void)crc;
    (void)seq;
    (void)stamp;
    (void)field;
    return 0U;
}
