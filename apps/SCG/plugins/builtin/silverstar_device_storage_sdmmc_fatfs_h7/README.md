# H743 SDMMC1 storage candidate

Version 0.1.1 owns `FATFS/Target/sd_diskio.c` and `bsp_driver_sd.c`.
The original CubeMX files remain byte-for-byte in `HardwareGenerated/STM32CubeMX`;
the explicit replacement contract removes exactly those two imported C units
from both Make and IDE compilation. It does not edit the user's imported tree.

This is an exact **static candidate**, not generic H7 or board qualification.
The manifest freezes ten reviewed CubeMX input files, including the SDMMC1
handle, bus width, IRQ priority/routing, FatFs configuration and old glue/header
identities. A changed or missing input is rejected before generation. Existing
edits to the owning glue are preserved and rejected for review, never overwritten.
Reimporting other CubeMX output requires a new explicit source review.

`generator/h7_storage.py` enforces the contract; its receipt belongs to
`.fccg/ownership.json` under `hardware.storage_replacement`. There is no new
architecture exclusion, generic source override, runtime registry or callback table.
The fixed `SD_Driver` table remains the required FatFs ABI.
Its five operations are file-local; the pinned ABI requires write and ioctl
support and rejects other configurations at compile time. The exact two owning
C files are first-party sources in both emitted Power10 and strict analyzer
compilation. This classification is selected by the H7 plugin/receipt, never
by a same-named user CubeMX file or by reclassifying all FatFs sources.

The disk interface permits one owner at a time, at most 128 sectors per request,
and always transfers one sector through a static 32-byte-aligned scratch buffer.
It never grants DMA ownership of caller memory. A request has a 30-second total
RTOS deadline; readiness also has a fixed 30,000-poll bound. Completion uses a
one-entry static queue. Wrong/missing completion, start failure, queue overflow,
abort/error or ready timeout leaves the scratch buffer permanently quarantined
and status NOT READY until MCU reset. A late callback cannot re-enable storage.

The BSP accepts only `hsd1` / SDMMC1 and one 512-byte sector. It checks range,
alignment, AXI SRAM DMA accessibility and disabled DCache before transfer.
HAL callbacks filter the exact handle; foreign handles and NULL do not release
the current transaction. `__DMB` orders scratch publication before IDMA starts
and completed receive data before the storage owner is awakened. Ordinary
external I/O failures retain ordinary error results, without fatal assertions.

The memory policy follows the existing H743 candidate's AXI-SRAM-only allocator
and disabled-DCache boundary. ST documents non-TCM SRAM for SD transfers and
cache coherency requirements in its [SD example](https://github.com/STMicroelectronics/STM32CubeH7/blob/master/Projects/STM32H743I-EVAL/Examples/SD/SD_ReadWrite_IT/readme.txt).
Barrier semantics are defined by [PM0253](https://www.st.com.cn/resource/en/programming_manual/pm0253-stm32f7-series-and-stm32h7-series-cortexm7-processor-programming-manual-stmicroelectronics.pdf).
These references and Host models do not establish electrical behavior, MCU
timing, interrupted-write recovery or a whole-firmware stack proof.

The existing emitted `storage_integrity/run_storage_integrity.py` runs the actual
owning diskio, FatFs and logger with delayed DMA, byte-offset integrity and the
unchanged timeout/wrong-event/start-failure/sync tests. Only its configuration
lookup follows the recorded H7 owner while retaining imported `ffconf.h`.
The Host clock is read-only in every mode. Modeled DMA/queue waits, explicit
task delays and existing producer-schedule steps advance time; repeated deadline
queries do not add milliseconds or producer work. Both disk and logger programs
exercise 1,000 repeated queries with zero elapsed ticks. All existing zero-drop,
overload-accounting, timeout, byte-integrity and no-reuse expectations remain.
The separate `tests/test_h7_storage_replacement.py` checks source identity,
nonmutation, ambiguous ownership, and real BSP calls against a Host HAL boundary.
Its actual-C boundary cases also cover late ready responses, an error after
completion, an error during initialization and an error during card-info lookup.

The new source graph intentionally invalidates the old H743 stack-input review.
No new input hashes are automatically added to that reviewed manifest. A failed
stack gate and critical-contract NOT PROVEN remain unresolved until an explicit
review covers the new compiler closures and task/MSP/ISR paths. Hardware and
flight validation remain absent.
