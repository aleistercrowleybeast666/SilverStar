#ifndef __NAVIGATION_AUGMENTED_BACKEND_H
#define __NAVIGATION_AUGMENTED_BACKEND_H
#include "navigation_session.h"
#include "system_magnetometer_if.h"

typedef enum {
    NavigationAugmentedMag_Ok=0, NavigationAugmentedMag_Missing=1,
    NavigationAugmentedMag_UntrustedClock=2, NavigationAugmentedMag_UnboundCalibration=3,
    NavigationAugmentedMag_IdentityChanged=4, NavigationAugmentedMag_Rejected=5
} NavigationAugmentedMagResult;
/* Private single-EstimatorTask-owner ingress. The existing canonical MAG getter
 * has no trusted clock contract and is NEVER promoted to this type implicitly.
 * Caller supplies native physical sensor axes, not canonical corrected samples. */
typedef struct {
    NavigationInputEvent event;
    uint16_t physical_device_id,descriptor_id;
    float sensor_uT[3],covariance_sensor_uT2[9];
    NavigationMagStage stage;
} NavigationAugmentedMagneticInput;
typedef struct {
    uint64_t state_us,last_magnetic_fusion_us;
    uint32_t generation,calibration_generation,magnetic_updates,magnetic_rejections,journal_failures;
    uint8_t algorithm_id,error_dimension,initialized,active,timing_qualified,magnetic_bound;
    NavigationAugmentedMagResult magnetic_result;
    NavigationSessionResult last_result;
    double gyro_bias[3],accel_bias[3],installation[9],inclination,declination;
    double covariance_diagonal[20];
} NavigationAugmentedDiagnostics;
/* Getter is called only by EstimatorTask; its publisher owns any cross-task copy. */
SystemDeviceResult NavigationAugmented_DiagnosticsGet(NavigationAugmentedDiagnostics *output);
NavigationSessionResult NavigationAugmented_MagneticApply(const NavigationAugmentedMagneticInput *input);
#endif
