#ifndef __SYSTEM_INSTALLATION_CAPTURE_IF_H
#define __SYSTEM_INSTALLATION_CAPTURE_IF_H
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#ifndef SYSTEM_INSTALLATION_CAPTURE_ENABLED
#define SYSTEM_INSTALLATION_CAPTURE_ENABLED 0U
#endif

typedef enum {
    SystemInstallationOperation_LogFile=2U,
    SystemInstallationOperation_MagWrite=3U,
    SystemInstallationOperation_Calibration=4U,
    SystemInstallationOperation_Alignment=5U,
    SystemInstallationOperation_Start=6U,
    SystemInstallationOperation_Configuration=7U,
    SystemInstallationOperation_Store=11U
} SystemInstallationOperation;

/* No provider currently declares all of these proofs for installation capture.
 * A caller must not infer them from an existing online/READY flag. */
typedef struct
{
    uint32_t epoch;
    uint32_t uncertainty_us;
    uint8_t every_native_frame;
    uint8_t measurement_time_known;
    uint8_t raw_definition_known;
    uint8_t physical_body_units_known;
} SystemInstallationCaptureProof;

#if (SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U)
SystemDeviceResult SystemInstallationCapture_OperationBegin(
    SystemInstallationOperation operation,uint8_t continuation);
void SystemInstallationCapture_OperationEnd(SystemInstallationOperation operation);
uint8_t SystemInstallationCapture_OperationHeld(SystemInstallationOperation operation);
void SystemInstallationCapture_DependenciesChanged(void);
void SystemInstallationCapture_ImuObserve(const SystemImuSample *sample,
    const SystemInstallationCaptureProof *proof, uint64_t now_us);
void SystemInstallationCapture_MagObserve(const SystemMagnetometerSample *sample,
    const SystemInstallationCaptureProof *proof, uint64_t now_us);
void SystemInstallationCapture_Process(uint64_t now_us);
uint8_t SystemInstallationCapture_CommandBlocked(void);
void SystemInstallationCapture_ExecuteLine(const char *line, char *response,
    uint16_t capacity, uint64_t now_us);
#else
static inline SystemDeviceResult SystemInstallationCapture_OperationBegin(
    SystemInstallationOperation operation,uint8_t continuation)
{ (void)operation;(void)continuation;return SYSTEM_DEVICE_OK; }
static inline void SystemInstallationCapture_OperationEnd(SystemInstallationOperation operation)
{ (void)operation; }
static inline uint8_t SystemInstallationCapture_OperationHeld(SystemInstallationOperation operation)
{(void)operation;return 0U;}
static inline void SystemInstallationCapture_DependenciesChanged(void){}
static inline void SystemInstallationCapture_ImuObserve(
    const SystemImuSample *sample, const SystemInstallationCaptureProof *proof,
    uint64_t now_us)
{ (void)sample; (void)proof; (void)now_us; }
static inline void SystemInstallationCapture_MagObserve(
    const SystemMagnetometerSample *sample,
    const SystemInstallationCaptureProof *proof, uint64_t now_us)
{ (void)sample; (void)proof; (void)now_us; }
static inline void SystemInstallationCapture_Process(uint64_t now_us)
{ (void)now_us; }
static inline uint8_t SystemInstallationCapture_CommandBlocked(void)
{ return 0U; }
static inline void SystemInstallationCapture_ExecuteLine(const char *line,
    char *response, uint16_t capacity, uint64_t now_us)
{ (void)line; (void)response; (void)capacity; (void)now_us; }
#endif
#endif
