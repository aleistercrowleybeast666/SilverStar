# Generated Ground target; source graph is Generated/ground_source_graph.json.
CC := arm-none-eabi-gcc
unexport CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH DEPENDENCIES_OUTPUT SUNPRO_DEPENDENCIES GCC_EXEC_PREFIX COMPILER_PATH
OBJCOPY := arm-none-eabi-objcopy
SIZE := arm-none-eabi-size
PYTHON ?= python
HOST_CC ?= gcc
ANALYZE ?= 0
BUILD_DIR := build
ifeq ($(ANALYZE),1)
BUILD_DIR := build/analysis
ANALYZER_FLAGS := -fanalyzer
endif
C_SOURCES := HardwareGenerated/ReviewedNativeEntry/Core/Src/main.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/gpio.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/adc.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/dma.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/spi.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/usart.c \
  HardwareGenerated/ReviewedNativeTime/Core/Src/stm32f4xx_it.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/stm32f4xx_hal_msp.c \
  HardwareGenerated/ReviewedNativeTime/Core/Src/stm32f4xx_hal_timebase_tim.c \
  HardwareGenerated/NativeClassicCdc/USB_DEVICE/App/usb_device.c \
  HardwareGenerated/NativeClassicCdc/USB_DEVICE/App/usbd_desc.c \
  HardwareGenerated/ReviewedNativeData/USB_DEVICE/App/usbd_cdc_if.c \
  HardwareGenerated/ReviewedNativeBulk/USB_DEVICE/Target/usbd_conf.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pcd_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_usb.c \
  HardwareGenerated/ReviewedNativeTime/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c \
  HardwareGenerated/ReviewedNativeTime/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_exti.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c \
  HardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_adc.c \
  HardwareGenerated/ReviewedNativeHal/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c \
  HardwareGenerated/ReviewedNativeHal/Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/system_stm32f4xx.c \
  HardwareGenerated/ReviewedNativeBulk/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c \
  HardwareGenerated/NativeClassicCdc/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c \
  HardwareGenerated/NativeClassicCdc/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ioreq.c \
  HardwareGenerated/ReviewedNativeBulk/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c \
  Generated/Src/native_no_heap.c \
  HardwareGenerated/NativeClassicCdc/Core/Src/syscalls.c \
  Common/Src/silverstar_assert.c \
  Generated/Src/native_clock.c \
  Generated/Src/native_clock_port.c \
  Generated/Src/native_critical.c \
  Generated/Src/native_platform.c \
  Generated/Src/native_runtime.c \
  Generated/Src/native_usb_state.c \
  Generated/Src/project_resources.c \
  Generated/Src/pc_byte_stream.c \
  Ground/Core/Src/ground_bridge.c \
  Ground/Radio/Src/ground_radio_sx1281.c \
  Ground/Radio/Src/ground_radio_activity.c \
  Ground/Protocol/Src/gsp_min_protocol.c \
  Ground/Protocol/Src/protocol_crc16.c \
  Devices/Telemetry/SX1281/Src/sx1281_device.c \
  Devices/Telemetry/SX1281/Src/sx1281_bus.c \
  Middlewares/Third_Party/SX1280lib/sx1280.c \
  Middlewares/ReviewedNativeRadio/SX1280lib/sx1280-hal.c \
  Generated/Src/native_abi_probe.c
ASM_SOURCES := HardwareGenerated/NativeClassicCdc/startup_stm32f407xx.s
FIRST_PARTY_C_SOURCES := $(filter Common/% Devices/% Generated/% Ground/% Platform/%,$(C_SOURCES))
VENDOR_C_SOURCES := $(filter Core/% Drivers/% HardwareGenerated/% Middlewares/%,$(C_SOURCES))
CLASSIFIED_C_SOURCES := $(FIRST_PARTY_C_SOURCES) $(VENDOR_C_SOURCES)
ifneq ($(words $(C_SOURCES)),$(words $(CLASSIFIED_C_SOURCES)))
$(error Ground compiler policy does not classify every C source)
endif
OBJECTS := $(patsubst %.c,$(BUILD_DIR)/%.o,$(C_SOURCES)) $(patsubst %.s,$(BUILD_DIR)/%.o,$(ASM_SOURCES))
FIRST_PARTY_WARNINGS := -Wall -Wextra -Wpedantic -Werror \
  -Wconversion -Wsign-conversion -Wshadow -Wundef -Wformat=2 \
  -Wdouble-promotion -Wcast-align -Wcast-qual -Wstrict-prototypes \
  -Wmissing-prototypes -Wswitch-enum -Wvla $(ANALYZER_FLAGS)
VENDOR_WARNINGS := -Wall -Werror=implicit-function-declaration \
  -Werror=incompatible-pointer-types -Werror=return-type
CFLAGS := -std=c11 -Os -ffunction-sections -fdata-sections -fstack-usage -Wvla -Werror=vla -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -IHardwareGenerated/ReviewedNativeConfig/USB_DEVICE/Target -IHardwareGenerated/NativeClassicCdc/Core/Inc -IHardwareGenerated/NativeClassicCdc/USB_DEVICE/App -IHardwareGenerated/NativeClassicCdc/USB_DEVICE/Target -IHardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Inc -IHardwareGenerated/NativeClassicCdc/Drivers/STM32F4xx_HAL_Driver/Inc/Legacy -IHardwareGenerated/NativeClassicCdc/Middlewares/ST/STM32_USB_Device_Library/Core/Inc -IHardwareGenerated/NativeClassicCdc/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc -IHardwareGenerated/NativeClassicCdc/Drivers/CMSIS/Device/ST/STM32F4xx/Include -IHardwareGenerated/NativeClassicCdc/Drivers/CMSIS/Include -IGenerated/Inc -ICommon/Inc -IInterfaces/Inc -IPlatform/Inc -IGround/Core/Inc -IGround/Protocol/Inc -IDevices/Telemetry/SX1281/Inc -IMiddlewares/Third_Party/SX1280lib -DUSE_HAL_DRIVER -DSTM32F407xx -DSILVERSTAR_AIR_LINK_ENABLED=1 -DAIR_LINK_HAL_BUFFER_SIZE=260
LDFLAGS := -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -Wl,-u,_sbrk -Wl,--gc-sections,-Map=$(BUILD_DIR)/ground.map -THardwareGenerated/NativeClassicCdc/STM32F407XX_FLASH.ld -specs=nano.specs -lc -lm -lnosys

ifeq ($(OS),Windows_NT)
MKDIR_P = if not exist "$(dir $@)" mkdir "$(dir $@)"
else
MKDIR_P = mkdir -p "$(dir $@)"
endif

all: $(BUILD_DIR)/ground.elf $(BUILD_DIR)/ground.bin $(BUILD_DIR)/ground.size

.PHONY: all architecture-check host-tests artifact-check power10-check static-analysis dependency-check
.DELETE_ON_ERROR:

$(OBJECTS): Makefile Generated/ground_source_graph.json Tools/ground_artifact_contract.py Tools/check_ground.py

dependency-check: $(OBJECTS)
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)"

static-analysis:
	$(MAKE) ANALYZE=1 all
	$(PYTHON) Tools/check_ground.py dependencies --build-dir build/analysis --compiler "$(CC)"

architecture-check:
	$(PYTHON) Tools/check_native_ground.py

host-tests:
	$(PYTHON) Tools/check_native_ground.py host --host-cc "$(HOST_CC)"

artifact-check: all
	$(PYTHON) Tools/check_native_ground.py artifact --prefix "arm-none-eabi-"

power10-check:
	powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1 -TargetKind Ground

$(BUILD_DIR)/ground.elf: $(OBJECTS) | dependency-check
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(BUILD_DIR)/ground.bin: $(BUILD_DIR)/ground.elf
	$(OBJCOPY) -O binary $< $@

$(BUILD_DIR)/ground.size: $(BUILD_DIR)/ground.elf
	$(SIZE) $< > $@

$(BUILD_DIR)/%.o: %.c
	@$(MKDIR_P)
	$(CC) $(CFLAGS) $(if $(filter $<,$(FIRST_PARTY_C_SOURCES)),$(FIRST_PARTY_WARNINGS),$(VENDOR_WARNINGS)) -MD -MP -MF $(@:.o=.d) -MT $@ -S $< -o $(@:.o=.s)
	$(PYTHON) Tools/check_ground.py assembler-source --build-dir $(BUILD_DIR) --source $<
	$(CC) -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard -x assembler -Wa,--MD,$(@:.o=.gas.d) -c $(@:.o=.s) -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

$(BUILD_DIR)/%.o: %.s
	@$(MKDIR_P)
	$(CC) $(CFLAGS) -save-temps=obj -MD -MP -Wa,--MD,$(@:.o=.gas.d) -x assembler-with-cpp -c $< -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

# Only gate-produced prerequisites enter Make; raw compiler/GAS manifests are data.
-include $(OBJECTS:.o=.deps.mk)
