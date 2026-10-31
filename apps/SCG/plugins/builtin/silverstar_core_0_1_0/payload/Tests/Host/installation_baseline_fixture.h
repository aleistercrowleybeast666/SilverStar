#ifndef __INSTALLATION_BASELINE_FIXTURE_H
#define __INSTALLATION_BASELINE_FIXTURE_H
/* Host integration of the owning CAL collector/getter used by Alignment/INS.
 * The hardware/maintenance/descriptor facade below is explicitly synthetic. */
#include "platform_critical.h"
#include "system_descriptor_if.h"
#include "system_installation_capture_if.h"
#include "system_lifecycle.h"
#define main Calibration_OriginalMain
#include "test_system_calibration.c"
#undef main

static uint32_t s_configuration = 77U;
static uint8_t s_active_instance;
static uint8_t s_configuration_busy;
#ifndef ACTIVE_INTEGRATION
uint8_t SystemInstallationActive_ApplyOwnerHeld(uint32_t token) {(void)token;return 0U;}
uint8_t SystemInstallationActive_RuntimeReady(uint32_t generation) { return (uint8_t)(generation != 0U); }
#endif
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState value) { (void)value; }
SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = s_active_instance; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemAlignment_CalibrationYield(void) { return SYSTEM_DEVICE_BUSY; }
SystemDeviceResult SystemLifecycle_ConfigurationBegin(SystemConfigurationAction action)
{ (void)action;
#ifdef ACTIVE_INTEGRATION
    if(SystemLifecycle_MaintenanceGet()!=SystemMaintenanceState_Off){return SYSTEM_DEVICE_BUSY;}
#endif
    return s_configuration_busy ? SYSTEM_DEVICE_BUSY : SYSTEM_DEVICE_OK; }
#ifdef ACTIVE_INTEGRATION
static uint8_t s_change_on_apply;
#include "installation_capture.h"
void SystemInstallationActive_DependenciesChanged(void);
#endif
void SystemLifecycle_ConfigurationEnd(SystemConfigurationAction action) {
    (void)action;
#ifdef ACTIVE_INTEGRATION
    /* Active publication fault injection is at the real CAL return boundary. */
#endif
}
SystemDeviceResult SystemInstallationCapture_OperationBegin(SystemInstallationOperation operation, uint8_t continuation)
{ (void)operation; (void)continuation;
#ifdef ACTIVE_INTEGRATION
    return InstallationCapture_OperationBegin((uint8_t)operation,continuation)==InstallationCaptureResult_Ok?SYSTEM_DEVICE_OK:SYSTEM_DEVICE_BUSY;
#endif
    return SYSTEM_DEVICE_OK; }
void SystemInstallationCapture_OperationEnd(SystemInstallationOperation operation) { (void)operation;
#ifdef ACTIVE_INTEGRATION
    InstallationCaptureResult result=InstallationCapture_OperationEnd((uint8_t)operation);
    TEST_CHECK(result==InstallationCaptureResult_Ok||result==InstallationCaptureResult_Stale);
#endif
}
uint32_t SystemDescriptor_ConfigDigestGet(void) { return s_configuration; }
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass kind, uint8_t instance, SystemDeviceDescriptor *descriptor)
{
    (void)kind; (void)memset(descriptor, 0, sizeof(*descriptor));
    descriptor->instance_id = instance; descriptor->descriptor_id = 101U;
    descriptor->physical_device_id = 9U; descriptor->driver_name_hash = 22U;
    descriptor->model_name_hash = 33U; return SYSTEM_DEVICE_OK;
}

#ifndef ACTIVE_INTEGRATION
int main(void)
{
    SystemCalibrationBaselineIdentity identity = {77U, 22U, 33U, 101U, 9U, 0U};
    SystemCalibrationBaselineIdentity actual_identity;
    SystemCalibrationImuCorrection baseline = {
        .accel_bias_mps2 = {0.3f, -0.2f, 0.1f}, .accel_scale = {1.02f, 0.99f, 1.01f},
        .gyro_bias_radps = {0.01f, -0.02f, 0.03f}, .gyro_scale = {1.0f, 1.0f, 1.0f}, .ready = 1U};
    SystemCalibrationImuCorrection actual;
    SystemCalibrationStatus status;
    float raw[3] = {1.3f, 1.8f, 3.1f}, gyro[3] = {0.11f, 0.18f, 0.33f};
    float acceleration[3], angular_rate[3];
    uint32_t generation = 0U;
    TEST_CHECK(Calibration_OriginalMain() == 0);
    TEST_CHECK(SystemCalibration_BaselineApply(&identity, &baseline, 0U, &generation) == SystemCalibrationBaselineResult_Ok);
    TEST_CHECK(generation == 1U && SystemCalibration_IsReady() == 0U);
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&actual) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&actual) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_ImuCorrectionApply(raw, gyro, &actual, acceleration, angular_rate) == SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(acceleration[0], 1.02f, 0.00001f);
    TEST_CHECK_NEAR(acceleration[1], 1.98f, 0.00001f);
    TEST_CHECK_NEAR(angular_rate[0], 0.1f, 0.00001f);
    /* This runs the real raw-sample six-face collector with another absolute
     * bias/scale. Its expected values detect any second baseline subtraction. */
    Test_SixFace();
    Test_OneFace();
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&actual) == SYSTEM_DEVICE_OK);
    TEST_CHECK(actual.mode == SYSTEM_CALIBRATION_MODE_ONE_FACE);
    TEST_CHECK(SystemCalibration_ImuCorrectionApply(raw, gyro, &actual, acceleration, angular_rate) == SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(acceleration[0], 1.22f, 0.0001f);
    TEST_CHECK(SystemCalibration_BaselineGet(&actual_identity, &actual, &generation) == SystemCalibrationBaselineResult_Ok);
    TEST_CHECK(generation == 1U && actual.accel_bias_mps2[0] == baseline.accel_bias_mps2[0]);
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_OK);
    s_configuration++;
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&actual) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemCalibration_IsReady() == 0U);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK && status.ready == 0U);
    TEST_CHECK(SystemCalibration_BaselineApply(&identity, &baseline, 1U, &generation) == SystemCalibrationBaselineResult_DependencyChanged);
    s_configuration--;
    s_active_instance = 1U;
    TEST_CHECK(SystemCalibration_IsReady() == 0U);
    s_active_instance = 0U;
    baseline.accel_scale[1] = NAN;
    TEST_CHECK(SystemCalibration_BaselineApply(&identity, &baseline, 1U, &generation) == SystemCalibrationBaselineResult_InvalidArgument);
    baseline.accel_scale[1] = 0.99f;
    s_configuration_busy = 1U;
    TEST_CHECK(SystemCalibration_BaselineApply(&identity, &baseline, 1U, &generation) == SystemCalibrationBaselineResult_Busy);
    s_configuration_busy = 0U;
    TEST_CHECK(SystemCalibration_BaselineGet(&actual_identity, &actual, &generation) == SystemCalibrationBaselineResult_Ok && generation == 1U);
    TEST_CHECK(SystemCalibration_BaselineApply(&identity, &baseline, 0U, &generation) == SystemCalibrationBaselineResult_Busy);
    return Test_Finish("installation_baseline_consumer");
}

#endif

#endif
