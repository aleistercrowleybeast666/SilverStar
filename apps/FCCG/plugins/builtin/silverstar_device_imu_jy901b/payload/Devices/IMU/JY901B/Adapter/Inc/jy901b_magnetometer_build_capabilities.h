#ifndef __JY901B_MAGNETOMETER_BUILD_CAPABILITIES_H
#define __JY901B_MAGNETOMETER_BUILD_CAPABILITIES_H

/*
 * This switch controls both the logical JY901B magnetometer adapter and the
 * physical JY901B MAG return frame.  Raw diagnostics can be enabled without
 * claiming that the installed vehicle has an absolute-vector calibration.
 */
#ifndef JY901B_MAGNETOMETER_ADAPTER_ENABLE
#define JY901B_MAGNETOMETER_ADAPTER_ENABLE                       0U
#endif

#define JY901B_MAGNETOMETER_BUILD_RAW_OUTPUT_AVAILABLE            1U
#define JY901B_MAGNETOMETER_BUILD_PHYSICAL_UNIT_AVAILABLE         1U
#define JY901B_MAGNETOMETER_BUILD_ABSOLUTE_VECTOR_QUALIFIED       0U

#endif /* __JY901B_MAGNETOMETER_BUILD_CAPABILITIES_H */
