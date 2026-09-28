#ifndef __JY901B_IMU_BUILD_CAPABILITIES_H
#define __JY901B_IMU_BUILD_CAPABILITIES_H

/* Structural data availability owned by the JY901B IMU package. */
#define JY901B_IMU_BUILD_ACCEL_AVAILABLE                         1U
#define JY901B_IMU_BUILD_GYRO_AVAILABLE                          1U

/* The current driver owns one static parser/context.  Multiple logical
 * capabilities from that context do not make the same plugin repeatable. */
#define JY901B_BUILD_MULTI_INSTANCE_READY                        1U

/* Algorithm qualification is deliberately separate from runtime health. */
#define JY901B_IMU_BUILD_SOFTWARE_PROPAGATION_QUALIFIED          1U
#define JY901B_IMU_BUILD_SOFTWARE_ALIGNMENT_QUALIFIED            1U
#define JY901B_IMU_BUILD_LANDING_STILLNESS_QUALIFIED             1U
#define JY901B_IMU_BUILD_LANDING_IMPACT_QUALIFIED                0U

/* Package-owned static estimator recommendation. */
#define JY901B_IMU_BUILD_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE 1U
#define JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_E_STD_MPS2          1.5f
#define JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_N_STD_MPS2          1.5f
#define JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_U_STD_MPS2          2.0f

#endif /* __JY901B_IMU_BUILD_CAPABILITIES_H */
