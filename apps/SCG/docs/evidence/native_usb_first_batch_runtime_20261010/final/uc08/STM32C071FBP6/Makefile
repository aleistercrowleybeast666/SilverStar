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
C_SOURCES := Ground/Core/Src/ground_bridge.c \
  Ground/Radio/Src/ground_radio_sx1281.c \
  Ground/Radio/Src/ground_radio_activity.c \
  Ground/Protocol/Src/gsp_min_protocol.c \
  Ground/Protocol/Src/protocol_crc16.c \
  Platform/STM32C0/Src/platform_critical_stm32c0.c \
  Platform/STM32C0/Src/platform_spi_stm32c0.c \
  Platform/STM32C0/Src/platform_gpio_stm32c0.c \
  Platform/STM32C0/Src/platform_time_stm32c0.c \
  Devices/Telemetry/SX1281/Src/sx1281_device.c \
  Devices/Telemetry/SX1281/Src/sx1281_bus.c \
  Middlewares/Third_Party/SX1280lib/sx1280.c \
  HardwareGenerated/ReviewedC071Radio/Middlewares/Third_Party/SX1280lib/sx1280-hal.c \
  Platform/STM32C0/Src/main.c \
  HardwareGenerated/STM32CubeMX/Core/Src/gpio.c \
  HardwareGenerated/STM32CubeMX/Core/Src/spi.c \
  HardwareGenerated/STM32CubeMX/Core/Src/usart.c \
  HardwareGenerated/STM32CubeMX/Core/Src/usb.c \
  HardwareGenerated/STM32CubeMX/Core/Src/stm32c0xx_it.c \
  Platform/STM32C0/Src/stm32c0xx_hal_msp.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_cortex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_rcc_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_flash_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_gpio.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_dma.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_dma_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pwr_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_exti.c \
  HardwareGenerated/ReviewedC071Hal/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_spi.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_spi_ex.c \
  HardwareGenerated/ReviewedC071Hal/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart.c \
  HardwareGenerated/ReviewedC071Hal/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_uart_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pcd.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_hal_pcd_ex.c \
  HardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Src/stm32c0xx_ll_usb.c \
  HardwareGenerated/STM32CubeMX/Core/Src/system_stm32c0xx.c \
  HardwareGenerated/STM32CubeMX/Core/Src/syscalls.c \
  HardwareGenerated/C071ClassicCDC/USB_Device/App/usb_device.c \
  Platform/STM32C0/Src/usbd_cdc_if.c \
  HardwareGenerated/C071ClassicCDC/USB_Device/App/usbd_desc.c \
  Platform/STM32C0/Src/usbd_conf.c \
  HardwareGenerated/C071ClassicCDC/Reviewed/Class/CDC/Src/usbd_cdc.c \
  HardwareGenerated/C071ClassicCDC/Reviewed/Core/Src/usbd_core.c \
  HardwareGenerated/C071ClassicCDC/Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_ctlreq.c \
  HardwareGenerated/C071ClassicCDC/Reviewed/Core/Src/usbd_ioreq.c \
  Common/Src/silverstar_assert.c \
  Generated/Src/project_resources.c \
  Generated/Src/platform_resources.c \
  Generated/Src/pc_byte_stream.c \
  Generated/Src/native_no_heap.c \
  Generated/Src/c071_context.c \
  Generated/Src/native_abi_probe.c
ASM_SOURCES := HardwareGenerated/STM32CubeMX/startup_stm32c071xx.s
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
CFLAGS := -std=c11 -Os -ffunction-sections -fdata-sections -fstack-usage -Wvla -Werror=vla -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -IPlatform/STM32C0/Inc -IGround/Core/Inc -IGround/Protocol/Inc -IPlatform/Inc -IDevices/Telemetry/SX1281/Inc -IMiddlewares/Third_Party/SX1280lib -IHardwareGenerated/STM32CubeMX/Core/Inc -IHardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Inc -IHardwareGenerated/STM32CubeMX/Drivers/STM32C0xx_HAL_Driver/Inc/Legacy -IHardwareGenerated/STM32CubeMX/Drivers/CMSIS/Device/ST/STM32C0xx/Include -IHardwareGenerated/STM32CubeMX/Drivers/CMSIS/Include -IHardwareGenerated/C071ClassicCDC/USB_Device/App -IHardwareGenerated/C071ClassicCDC/USB_Device/Target -IHardwareGenerated/C071ClassicCDC/Middlewares/ST/STM32_USB_Device_Library/Core/Inc -IHardwareGenerated/C071ClassicCDC/Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Inc -IGenerated/Inc -IDevices -ICommon/Inc -IInterfaces/Inc -DSILVERSTAR_AIR_LINK_ENABLED=1 -DUSE_HAL_DRIVER -DSTM32C071xx -DAIR_LINK_HAL_BUFFER_SIZE=260 -DUSE_HAL_PCD_REGISTER_CALLBACKS=0 -DUSBD_CLASS_BOS_ENABLED=0 -DUSBD_USER_REGISTER_CALLBACK=0
LDFLAGS := -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -Wl,-u,_sbrk -Wl,--gc-sections,-Map=$(BUILD_DIR)/ground.map -THardwareGenerated/STM32CubeMX/STM32C071XX_FLASH.ld -specs=nano.specs -lc -lm -lnosys

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
	$(PYTHON) Tools/check_c071_candidate.py

host-tests:
	$(PYTHON) Tools/check_c071_candidate.py host --host-cc "$(HOST_CC)"

artifact-check: all
	$(PYTHON) Tools/check_c071_candidate.py artifact --prefix "arm-none-eabi-"

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
	$(CC) -mcpu=cortex-m0plus -mthumb -mfloat-abi=soft -x assembler -Wa,--MD,$(@:.o=.gas.d) -c $(@:.o=.s) -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

$(BUILD_DIR)/%.o: %.s
	@$(MKDIR_P)
	$(CC) $(CFLAGS) -save-temps=obj -MD -MP -Wa,--MD,$(@:.o=.gas.d) -x assembler-with-cpp -c $< -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

# Only gate-produced prerequisites enter Make; raw compiler/GAS manifests are data.
-include $(OBJECTS:.o=.deps.mk)
