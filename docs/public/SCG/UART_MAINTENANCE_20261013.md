# UART maintenance safety checkpoint, 2026-10-13

This development checkpoint follows `f2ce541382589cb606e1f5b21f6fd982357eaa54`.
The local branch is `feature/usb-transport-0.1.3-20261013`. Frozen v0.1.2,
the user's FINAL project and UNDERLINE packages are unchanged. No port or SWD
session was opened; there was no reset, halt, flash, actuator action or publication.

## Runtime boundary

`LOGFILE ENTER` reserves a boot-latched maintenance state under the same interrupt
lock as queued and direct START admission. An existing START or configuration
transaction rejects entry. AIR, Console and local START requests received while
maintenance is Draining/Ready/Failed return BUSY immediately and are not queued.
Configuration admission is also blocked. Fault cannot upgrade Failed to Ready.

Only LoggerTask performs filesystem work. It finishes bootstrap/recovery, closes
record-producer admission, drains the queue and aggregate, flushes/closes the
writer, and writes final status. Publication of maintenance Ready checks actual
finalization, inactive writer, empty aggregate and empty LoggerBus. Failed close,
I/O, boot-disabled logging or final-status write never authorizes file reading.
The F1/F4 storage adapters additionally require maintenance Ready, mounted healthy
storage, no open writer, and PREFLIGHT/READY/POSTFLIGHT. Boot-time historical reads
are supported after this transition; they are not restricted to POSTFLIGHT.

The lifecycle observation may still say READY; START authorization separately
checks maintenance. Cancellation, completion and disconnect leave the maintenance
lock latched. Physical reboot is required before flight preparation. This is an
explicit first-version policy, not an implemented in-session EXIT operation.

`STATUS` copies a LoggerTask RAM snapshot, its sequence and elapsed sample age.
It never calls FatFs or probes media. `CANCEL cleanup_complete=0` acknowledges
acceptance; `cleanup_pending` stays set until the owner has returned from reset/
close. Close failure latches Failed. These facts do not establish cancellation
latency, FatFs/task WCET or watchdog margin. READ is at most 64 data bytes and META
hashes at most 512 bytes per step, but open/seek/directory/close can perform more
filesystem work. Timeout bounds and byte bounds are different claims.

The mailbox formatter is 256 bytes, verified with maximal uint32 fields and a
64-byte READ response (255 text bytes plus NUL). Scratch is a 512-byte union;
hash/read bytes are fully consumed before formatting reuses it. Logger CPU state
and its record serializer move to CCM. The existing 4096-byte DMA aggregate and
storage DMA bounce sector remain DMA-accessible. This is not spare-stack proof.

## GSHC and compatibility

The fourth page has separate FC maintenance and Ground/AIR sources. A single
Refresh Ports button at the left of the Ground selector updates both COM lists
without collapsing their independent selections. Both editable baud controls
share the same candidates and positive signed-32-bit input validation. Candidate
membership is not a support gate; the serial driver/device can reject a rate.
Both defaults are 230400. SWD is labeled unavailable/unimplemented and is not a
third COM connection. It may eventually use a different device from maintenance.

New firmware: CAPS, RAM STATUS, explicit ENTER, then LIST/META/READ with PENDING/
POLL. The single background owner serializes polling and downloads; the GUI thread
does no serial parsing or filesystem transfer. Old/missing maintenance capabilities
disable downloads. Unknown device/boot identity prohibits resume and remote delete.
Partial files remain distinct; completed files require whole size/CRC and local
SHA-256/readback before atomic publication. See the [wire contract](../../../contracts/log_file_service_v1.json).

FINAL compatibility: the read-only source at
`D:/stm32_project/SS_0_5_TEST_FINAL/Flight_Controller/System/Src/system_console.c`
has SHA-256 `aa9b84db6a525fc3cb0263fabc20b89168bc220f06128c0a8b4280f2a7227077`.
It supports SYSTEM INFO/STATUS/CAPABILITIES and LOG STATUS, but not LOGFILE.
The legacy adapter uses exactly those four allowlisted queries, preserves unknown
values, and keeps system status available if LOG STATUS fails. It labels host
receive age separately from unknown firmware sample age; separate responses are
not an atomic sample. FINAL's local USART3 PB10 TX/PB11 RX configuration is 230400,
8N1 without flow control. This is static project evidence, not verified flashed
identity, wiring, or a successful physical connection. Legacy LIST is not a file
directory. No maintenance 0.1 or dynamic variable directory is claimed here.

## Fresh evidence

Retained package: `apps/SCG/docs/evidence/uart_maintenance_20261013/evidence.zip`.
The manifest records exact dirty-source bytes, command/environment/tool versions,
input inventories, artifacts and hashes. Local generation/builds are under
`.work/dev013_safety2/uart_project01`; the generator produced 622 files / 16.5 MB
without a workspace/SDK copy. Payload refreshes touched only inventoried generated
validation files, never the user's project. Earlier failed attempts remain in the
package and are not reported as full-suite passes.

| Validation | Actual result |
| --- | --- |
| Pre-fix replay against f2ce541 | Normal and full-chunk pass; the start-capable-state zero-I/O assertion fails. Original failure and exact repeat retained. |
| Generated Host `uart-host05` | 80 executables, 4,446,508 checks, 0 failures; 11 compile-pass, 18 expected compile failures, 8 not applicable. Includes actual LoggerTask/LoggerBus/FatFs mock maintenance success and finalization fault modes. |
| SCG `scg_pytest03` | 47 passed: file service, maximal format, disabled logging, source ownership and exact stack identities. |
| GSHC `gshc09` | 67 passed, 12 subtests: old/new protocol, bad/stale status, disconnect, cancellation, serial ownership, refresh/custom baud, CN/EN and DPI. Mock ports only. |
| ARM `uart-arm02` | Actual Cortex-M4 F407 compile/link, GCC 14.3.Rel1. |
| Analyzer `uart-analyzer01` | Actual ARM `-fanalyzer -c` compile and link, separate StaticAnalysis artifacts; not syntax-only. |
| Emitted `uart-gates02` | One actual command ran power10-check, architecture-check, artifact-check, stack-report; exit 0. 6427 text checks, 113 first-party C files, 2803 functions, 839 nonblocking recommendations. Architecture 356 checks. Critical-contract review explicitly NOT PROVEN. |

Final Release ELF SHA-256:
`7176c21d370c866588e2545b4a5ac2293781f9247f9c719997fbdc36340bfe7d`.
FLASH 339616 bytes; main SRAM 101892 (508 below the 102400 project budget);
CCM 59152 (6384 physical bytes free); heap symbols zero. These are linked-artifact
measurements for this configuration, not universal chip compatibility or timing.

## Stack review revision v16

The old emitted gate failed on unknown full-source inputs before budgeting.
`uart_maintenance_20261013_v16` registers eleven exact reviewed complete inputs
and four compiler-derived dependency graphs, preserving v2-v15 records. Changes
cover logger bus/header, logger task, lifecycle/header, file service/header,
storage adapter, console dispatch and two generated identity payloads. New call
edges are direct; there is no callback registry, recursion or new indirect-call
exception. Existing SD/FatFs and startup bindings remain concrete linked checks.
The final logger Ready assertions have their own retained source-hash revision.
Minimum margin/context reserve remain 256 bytes; task sizes are unchanged.
Unknown input, changed input, unresolved indirect calls and dynamic frames still
fail. Regression tests reject altered full input bytes.

Actual task margins (bytes): Device 416, INS 832, Estimator 844, Flight 448,
Logger 1288, Serial 1200, Telemetry 1944, Idle 256. The checker retains
`whole_program_stack_acceptance=NOT PROVEN`: MSP/main, interrupt nesting, dynamic
hardware high-water marks and hardware margin need separate evidence. Linked
third-party HAL/FreeRTOS/FatFs/libc/libm and their controlled indirect paths remain
in the linked report; the first-party Power-of-Ten adaptation is not whole-firmware
original-rule compliance or certification. F1 Flight compilation was not run for
this checkpoint; the F1/F4 service adapters are byte-identical, which is weaker.

USB callback drafts are deferred by the user. Four unverified files and their
hashes live in `.work/dev013_safety2/usb_deferred_20261013`; they are removed from
the active source paths and excluded from this checkpoint. PMA/OTG retirement and
stale completion isolation remain NOT PROVEN. No old USB binary is credited here.
