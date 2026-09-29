BUILD_MANIFESTS += Platform/STM32F4/module.mk

C_SOURCES += \
  Platform/STM32F4/Src/platform_adc_stm32f4.c \
  Platform/STM32F4/Src/platform_critical_stm32f4.c \
  Platform/STM32F4/Src/platform_gpio_stm32f4.c \
  Platform/STM32F4/Src/platform_i2c_stm32f4.c \
  Platform/STM32F4/Src/platform_memory_stm32f4.c \
  Platform/STM32F4/Src/platform_spi_stm32f4.c \
  Platform/STM32F4/Src/platform_time_stm32f4.c \
  Platform/STM32F4/Src/platform_uart_stm32f4.c

C_INCLUDES += \
  Platform/Inc \
  Platform/STM32F4/Inc
