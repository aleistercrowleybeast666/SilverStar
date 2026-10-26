BUILD_MANIFESTS += BuildSystem/freertos.mk

C_SOURCES += \
  ThirdParty/FreeRTOS-Kernel/list.c \
  ThirdParty/FreeRTOS-Kernel/queue.c \
  ThirdParty/FreeRTOS-Kernel/tasks.c \
  ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c

C_INCLUDES += \
  ThirdParty/FreeRTOS-Kernel/include \
  ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F
