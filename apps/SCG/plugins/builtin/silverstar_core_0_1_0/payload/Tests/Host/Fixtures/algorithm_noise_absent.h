#ifndef __ALGORITHM_NOISE_ABSENT_H
#define __ALGORITHM_NOISE_ABSENT_H

/* Each negative declares one missing group; other groups retain their explicit
 * positive overrides, so a different class cannot make the rejection pass. */
#include "project_flight_config.h"
#if defined(TEST_NOISE_MISSING_IMU)
#undef SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_OVERRIDE
#undef SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_OVERRIDE
#undef SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_OVERRIDE
#elif defined(TEST_NOISE_MISSING_GNSS)
#undef SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE
#undef SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE
#undef SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE
#elif defined(TEST_NOISE_MISSING_BAROMETER)
#undef SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE
#else
#error "Noise fixture must declare exactly one absent group"
#endif

#endif /* __ALGORITHM_NOISE_ABSENT_H */
