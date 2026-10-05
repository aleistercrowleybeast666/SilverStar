BUILD_MANIFESTS += Devices/Telemetry/SX1281/module.mk
C_SOURCES += \
  Devices/Telemetry/SX1281/Src/sx1281_device.c \
  Devices/Telemetry/SX1281/Src/sx1281_bus.c \
  Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c \
  Middlewares/Third_Party/SX1280lib/sx1280.c \
  Middlewares/Third_Party/SX1280lib/sx1280-hal.c
C_INCLUDES += \
  Devices/Telemetry/SX1281/Inc \
  Middlewares/Third_Party/SX1280lib
