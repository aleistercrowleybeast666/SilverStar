# STM32C071FBP6 native PCD and classic CDC experiment

**Software acceptance is BLOCKED.** Real ARM compilation, analyzer compilation,
three generated-source Host regressions, CDC callback fault tests and actual
C071 artifact checks pass. Power10 fails on the authored permanent main and
Error_Handler loops. UART230400 initialization and IRQ exist, but a bounded UART
receive/session implementation does not. Whole-program stack, ISR nesting,
critical contracts, MCU WCET and physical USB/radio behavior remain NOT PROVEN.
This checkpoint must not authorize manufacture or be described as completed
firmware qualification. Evidence is in `ground-usb-evidence/c071-evidence-summary.json`.

## Official installation and native input

User-approved official CubeMX CLI installation combined FW.C0.1.4.0 and patch
FW.C0.1.4.1 in `C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1`.
package.xml identifies Release=FW.C0.1.4.0, Patch=FW.C0.1.4.1; HAL and device
headers identify 1.4.1. The package contains 21,535 files / 399,096,236 bytes.
Installed Package_license.html SHA256 is
`df7fe7ac0c4ef8eb509bdb203b80b5ddff91328afaeb40eec15a65b76ee2fec3`, exactly the
approved patch license. Both complete agreements and the Azure licensed hardware
list were delivered to personal Library. The native install log explicitly
records acceptance of the base; a separate patch acceptance line is absent.
No independently retained whole-archive checksum is claimed.

CubeMX 6.15.0 / DB6.0.150 generated the complete native v2 IOC project. A first
relocated-generation attempt had duplicate absolute Makefile paths and missing
syscalls/sysmem. That log is retained. Loading a fresh copied IOC directly from
its output directory produced relative paths, Drivers, Core, GNU startup,
linker and a working native Makefile. Optional unrelated PDSC/import messages
remain visible in the log. The unchanged native Makefile was actually built:
text=12928, data=12, bss=3068. This native result initializes PCD only; it does not
contain CDC descriptors, CDC sessions or the Ground bridge.

The native snapshot is hashed per file in the evidence. The canonical v2 IOC
was preserved. Native GPIO/SPI/UART/IRQ code is imported unchanged; adapted
main/MSP/CDC/usbd_conf code belongs to `Platform/STM32C0/Src/` and receives the
same first-party strict warnings, real -fanalyzer compilation and Power10 scan
as the existing owned sources. All 19 first-party C files are covered. No shared
F103/F407 renderer, dependency gate or Power10 allowlist was changed.

## CDC integration and limits

[ST's classic C0 repository](https://github.com/STMicroelectronics/stm32c0-classic-coremw-apps)
provides CDC_Standalone for NUCLEO-C071RB with no IOC. Pinned parent revision:
`334655ed5eb719db18fa5990a5044332eeca59dc` (V1.1.0). USB device middleware revision:
`947131e000d1ecebc260f22010fa75486c50b423` (2.11.5). The frozen cache also records
original HAL/device 1.4.0, but the linked HAL/CMSIS device files are overwritten
by the complete native CubeC0 1.4.1 snapshot. Upstream notices/licenses remain.
This explicit experiment is not normal SCG C0 importer, GUI or USBX support.

Native usb.c defines a separate PCD handle and is retained in NativeCubeMX for
provenance, but is not linked into CDC. The pinned classic usbd_conf owns that
handle and the CDC stack. REGISTER_CALLBACKS is fixed to zero; the recipe
materializes the exact active branches and omits unused registration branches.
The static CDC allocation rejects zero/oversize requests and uses fixed storage;
there is no target heap allocation. CDC retains a 64-byte callback RX buffer,
512-byte bounded session RX ring and 70-byte TX storage. Callback tests exercise
init/deinit/reset, length and pointer bounds, line coding, submission and rearm
failures. HAL/radio Host paths use mocks and prove no physical recovery.

The linked target has 51 C sources plus one GNU startup ASM source. Actual ELF
is ARMv6-M/Thumb-1 soft float, initial SP=0x20006000. Required USB, SysTick,
EXTI2_3 and USART2 strong handlers resolve to the real vector entries. Actual
PCD, CDC, Ground/session and UART/SPI initialization symbols are required.
Paired CPP/GAS dependencies and exact saved assembler source checks pass both
before link and on an unchanged Make rerun. The first artifact-check attempt
used the old compiler-less API and rejected toolchain stdint.h; its invocation
was corrected to pass the selected compiler, preserving the gate. A Windows GBK
reader failure was corrected to explicit UTF-8. Fresh regeneration after that
reader correction produces identical input bytes (recorded in evidence).

Release and analyzer binaries match byte for byte. text=41644, data=256,
bss=9696 (including 2048-byte reserved stack), Flash=41900, unallocated RAM=14624.
Heap reservation is zero. These RAM bytes are not a stack bound or safe stack
margin. Strict C/analyzer compilation emitted no diagnostics; link logs retain
libnosys _close/_lseek/_read/_write warnings. Actual linked-symbol checks reject
heap/stdio implementations. No warning-free whole-link claim is made.

## Native pin and clock contract

[ST DS14693](https://www.st.com/resource/en/datasheet/stm32c071c8.pdf) supplies
C071FBP6 TSSOP20, 128KB Flash and 24KB SRAM constraints. Native HSI system clock
is 48MHz; USB uses separate HSI48 with USB SOF CRS trimming. PMA regions
0x14/0x54/0x94/0xD4/0x114 hold disjoint 64/64/64/64/8-byte buffers in 2KB PMA.

| Function | MCU pin | TSSOP20 position | Software setting |
| --- | --- | --- | --- |
| E28 RESET | PA0 | 7 | High idle, push-pull output |
| E28 BUSY | PA1 | 8 | Input, no pull |
| USART2 TX / RX | PA2 / PA3 | 9 / 10 | AF1, 230400 8N1, IRQ3; receive/session pending |
| E28 NSS | PA4 | 11 | High idle, software CS |
| E28 SCK / MISO / MOSI | PA5 / PA6 / PA7 | 12 / 13 / 14 | SPI1 AF0, mode0, 3MHz, NSS pulse off |
| USB DM / DP | PA11 / PA12 | 16 / 17 | GPIO remaps explicitly disabled |
| SWDIO / SWCLK | PA13 / PA14 | 18 / 19 | Preserved |
| E28 DIO1 | PB3 | 20 | Rising EXTI3, priority2 |
| NRST | PF2-NRST | 6 | Preserved |

The old illustrative DIO1=PA3 profile is superseded by native PB3. No production
PCB wiring is asserted. `D:/stm32_project/SS_0_5_TEST_FINAL` and the original
SilverStar checkout were untouched. No flash, serial, START, push, merge or EDA
editing occurred.

## Remaining blockers and mini handoff

Power10 explicitly fails on main scheduler/fault `while(1)` loops; no loop
syntax trick, hiding under vendor paths or new exception was used. AGENTS.md
states: "Do not enlarge these exceptions without explicit authorization."
A narrowly reviewed permanent-loop policy would require authorization; the
checks also retain critical-contract review NOT PROVEN regardless of tool exit.
UART configuration alone is insufficient for a UART session claim. Native C0
normal-import/GUI/USBX support remains outside this experiment.

The proposed mini is C071FBP6 plus E28-2G4M12S with SWD retained. The official
[E28 manual](https://www.cdebyte.com/pdf-down.aspx?id=2994) lists module VCC1,
GND2/7/8/14, MISO3, MOSI4, SCK5, NSS6, NRESET9, BUSY10 and DIO1/2/3=11/12/13.
Use the table only as provisional connection input. Its dimension/drawing
sections disagree with each other and the product page; exact module revision,
antenna selection and manufacturer land pattern must be verified before any
production footprint. MCU/module use 3.3V with local decoupling; USB5V needs a
suitable 3.3V supply. The module's documented TX current is 45mA, RX10mA and
supply guidance includes 30% margin. USB transceiver supply is 3.0-3.6V; preserve
native internal DP pull-up and review decoupling/USB layout from the datasheet.
No schematic or PCB has been committed to EDA and no future mini directory was
created. Software acceptance remains blocked, so the EDA design phase is paused.

## Reproduce (software only)

Run c071_fetch.py into an immutable official cache, then:

```text
python -B tools/validation/c071_ground_candidate.py --official <cache> --cubemx <complete-native-PCD-project> --output <new-empty-output>
make PYTHON="python -B" all
make PYTHON="python -B" ANALYZE=1 all
make PYTHON="python -B" architecture-check host-tests power10-check
python -B tools/validation/c071_callback_test.py <output> --host-cc <gcc>
python -B tools/validation/c071_artifact_check.py <output> --prefix <arm-none-eabi->
make PYTHON="python -B" all
```

The Power10 command currently fails as documented. Use the own C071 artifact
checker; the unchanged normal complete-CubeMX artifact target does not claim
C0 support. This is a separate C071 checkpoint on repair f274f24, not an amendment
to or requalification of the F103/F407 repair.
