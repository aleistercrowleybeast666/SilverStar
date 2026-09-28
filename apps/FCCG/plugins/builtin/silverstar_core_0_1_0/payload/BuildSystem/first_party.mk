BUILD_MANIFESTS += BuildSystem/first_party.mk

C_SOURCES += \
  Core/Src/main.c \
  Core/Src/gpio.c \
  Core/Src/dma.c \
  Core/Src/usart.c \
  Core/Src/stm32f4xx_it.c \
  Core/Src/stm32f4xx_hal_msp.c \
  Core/Src/stm32f4xx_hal_timebase_tim.c \
  Core/Src/system_stm32f4xx.c \
  Core/Src/syscalls.c \
  Core/Src/spi.c \
  Core/Src/adc.c \
  Core/Src/sdio.c \
  APP/Src/device_task.c \
  APP/Src/device_native_log.c \
  APP/Src/diagnostic_log.c \
  APP/Src/app_tasks.c \
  APP/Src/estimator_barometer_pending.c \
  APP/Src/estimator_bus.c \
  APP/Src/estimator_task.c \
  APP/Src/flight_task.c \
  APP/Src/imu_sample_bus.c \
  APP/Src/ins_task.c \
  APP/Src/logger_bus.c \
  APP/Src/logger_task.c \
  APP/Src/serial_task.c \
  APP/Src/telemetry_task.c \
  Common/Src/common_format.c \
  Common/Src/common_ringbuf.c \
  Common/Src/common_spsc_queue.c \
  Common/Src/silverstar_assert.c \
  Common/Src/debug_log.c \
  Modules/Src/telemetry_service.c \
  Protocol/Src/air_protocol.c \
  Protocol/SSLOG/Src/sslog_protocol.c \
  Protocol/SSLOG/Src/sslog_records.c \
  System/Src/system_barometer.c \
  System/Src/system_capabilities.c \
  System/Src/system_console.c \
  System/Src/system_estimator_diagnostics.c \
  System/Src/system_estimator_profile.c \
  System/Src/system_gnss_quality.c \
  System/Src/system_health.c \
  System/Src/system_log_policy.c \
  System/Src/system_navigation_profile.c \
  System/Src/system_profile.c \
  System/Src/system_sensor_status.c \
  System/Src/system_startup.c \
  System/Src/system_time.c \
  System/Alignment/Src/system_alignment.c \
  System/Alignment/Src/system_alignment_source.c \
  System/Calibration/Src/system_calibration.c \
  System/Calibration/Src/system_calibration_correction.c \
  System/Indicator/Src/system_indicator.c \
  System/Inertial/Src/system_inertial.c \
  System/User/system_user_inertial_config.c \
  OS/FreeRTOS/freertos_hooks.c \
  Targets/SilverStar_F407/Src/freertos_target_irq.c

C_INCLUDES += \
  Core/Inc \
  OS/FreeRTOS \
  Targets/SilverStar_F407/Inc \
  APP/Inc \
  Common/Inc \
  Modules/Inc \
  Protocol/Inc \
  Protocol/SSLOG/Inc \
  Interfaces/Inc \
  System/Inc \
  System/Alignment/Inc \
  System/Calibration/Inc \
  System/Indicator/Inc \
  System/Inertial/Inc \
  System/User \
  Devices
