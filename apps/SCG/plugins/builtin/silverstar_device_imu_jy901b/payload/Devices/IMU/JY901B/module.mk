BUILD_MANIFESTS += Devices/IMU/JY901B/module.mk
C_SOURCES += \
  Devices/IMU/JY901B/Src/jy901b_device.c \
  Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c \
  Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c \
  Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c \
  Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c
C_INCLUDES += \
  Devices/IMU/JY901B/Inc \
  Devices/IMU/JY901B/Adapter/Inc
