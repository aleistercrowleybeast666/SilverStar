# CHECKER PROJECTION ONLY; compiled by the recorded direct commands.
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
C_SOURCES := D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Native\Core\Src\main.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\gpio.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\dma.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\spi.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\usart.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\stm32f1xx_it.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\stm32f1xx_hal_msp.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\USB_DEVICE\App\usb_device.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\USB_DEVICE\App\usbd_desc.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Native\USB_DEVICE\App\usbd_cdc_if.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Native\USB_DEVICE\Target\usbd_conf.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_gpio_ex.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_pcd.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_pcd_ex.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_ll_usb.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_rcc.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_rcc_ex.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_gpio.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_dma.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_cortex.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_pwr.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_flash.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_flash_ex.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_exti.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_spi.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Src\stm32f1xx_hal_uart.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\system_stm32f1xx.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Native\Middlewares\ST\STM32_USB_Device_Library\Core\Src\usbd_core.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Middlewares\ST\STM32_USB_Device_Library\Core\Src\usbd_ctlreq.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Middlewares\ST\STM32_USB_Device_Library\Core\Src\usbd_ioreq.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Native\Middlewares\ST\STM32_USB_Device_Library\Class\CDC\Src\usbd_cdc.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\sysmem.c \
  D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Src\syscalls.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Generated\UsbTransport\Src\usb_cdc_transport.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Generated\UsbTransport\Src\usb_cdc_port.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Generated\UsbTransport\Src\usb_cdc_retire.c \
  D:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Common\Src\silverstar_assert.c
ASM_SOURCES := D:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\startup_stm32f103xb.s
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
CFLAGS := -std=c11 -Os -ffunction-sections -fdata-sections -fstack-usage -Wvla -Werror=vla -mcpu=cortex-m3 -mthumb -mfloat-abi=soft -ID:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Generated\UsbTransport\Inc -ID:\python_software\SilverStar\.work\0.1.3-software-completion-20261101\usb\generic-before-v1\native\f103\Common\Inc -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Core\Inc -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\USB_DEVICE\App -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\USB_DEVICE\Target -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Inc -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\STM32F1xx_HAL_Driver\Inc\Legacy -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Middlewares\ST\STM32_USB_Device_Library\Core\Inc -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Middlewares\ST\STM32_USB_Device_Library\Class\CDC\Inc -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\CMSIS\Device\ST\STM32F1xx\Include -ID:\Codex_Work\2026-10-08\task\usb-validation\cube-f103-usb\Drivers\CMSIS\Include -DUSE_HAL_DRIVER -DSTM32F103xB
LDFLAGS := -mcpu=cortex-m3 -mthumb -mfloat-abi=soft -Wl,--gc-sections,-Map=$(BUILD_DIR)/ground.map -TNative/STM32F103XX_FLASH.ld -specs=nano.specs -lc -lm -lnosys

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
	$(PYTHON) Tools/check_ground.py architecture

host-tests:
	$(PYTHON) Tools/check_ground.py host --host-cc "$(HOST_CC)"

artifact-check: all
	$(PYTHON) Tools/check_ground.py artifact --prefix "arm-none-eabi-"
	$(PYTHON) Generated/memory_audit.py --elf $(BUILD_DIR)/ground.elf --map $(BUILD_DIR)/ground.map --linker Native/STM32F103XX_FLASH.ld --contract Generated/memory_contract.json --output $(BUILD_DIR)/memory-report.json --prefix "arm-none-eabi-"
	@echo "FIRMWARE_MEMORY_REPORT|$(BUILD_DIR)/memory-report.json"

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
	$(CC) -mcpu=cortex-m3 -mthumb -mfloat-abi=soft -x assembler -Wa,--MD,$(@:.o=.gas.d) -c $(@:.o=.s) -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

$(BUILD_DIR)/%.o: %.s
	@$(MKDIR_P)
	$(CC) $(CFLAGS) -save-temps=obj -MD -MP -Wa,--MD,$(@:.o=.gas.d) -x assembler-with-cpp -c $< -o $@
	$(PYTHON) Tools/check_ground.py dependencies --build-dir $(BUILD_DIR) --compiler "$(CC)" --source $<

# Only gate-produced prerequisites enter Make; raw compiler/GAS manifests are data.
-include $(OBJECTS:.o=.deps.mk)
