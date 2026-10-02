# JY901B register read repair — real configuration candidate

Production/test commit: dde622b5ab49889304bb1ec159cfffd065db731a. Base 492f30880e9936a7b72091b14354a21b32af33c4.
Independent fix/imu-startup-20261002. No hardware/COM/DAP access, flash, push, merge,
main modification, tag/reset/clean or shared-venv change. Production difference is
only jy901b_device.c; two repository Host regression files are added. GUI/RF/M9N,
optional GNSS START, all receiver writes and baud strategy are unchanged.

Actual user ssproject is the RadioRuntimeFaultHotfix post Flight configuration,
all fields equal except candidate name. F407/KF6, deployment=[Delay], delay=10.0,
memory_layout=legacy. Configuration proof records both input hashes. No new default
parachute project or sensor setting was substituted.

## Results

Accepted old generated counter: 26 checks / 4 expected failures. Corrected new
counter: 26 / 0; expanded real generated driver: 4371 / 0. Targeted JY startup,
UART DMA/recovery and checker regression: 117 passed, one preserved pytest cache
configuration warning. Full generated Host: 75 executable tests, 4,402,431 checks,
0 failures, 7 positive compile cases, 17 expected compile rejections and storage
byte/logger integrity. ARM Release, architecture, unchanged emitted PoT, actual
analyzer, artifact and stack/memory commands all exit zero; raw results and logs
are included. PoT critical-contract review and complete MCU WCET/stack/flight
qualification remain NOT PROVEN. Default firmware contains no diagnostic trace.

Initial v1 counter had an invalid acceleration checksum and persisted contexts;
it is explicitly rejected as proof and its log preserved in earlier checkpoint.
Only v2 with CRC-valid (additive checksum) frames and explicit BSS reboot fixture
is accepted. Initial expanded-test command duplicated the real Host mock linkage;
compile failure is preserved, corrected command removes duplicate TU. No failing
gate is counted as a pass and no skipped scope is represented as complete.

## Production behavior and bounds

IMU_ReadResponseChecksumValid validates only the fixed 11-byte additive checksum,
not response type. Parser consumes whole checksum-valid ordinary frames and returns
success only for type 5F. On invalid candidate it preserves the earliest bounded
55 suffix. Parser index is checked <11 before writing. It uses the existing frame
and 64-byte temporary buffer without enlarging queues or state.

AsyncPoll snapshots RxCount once, then drains at most 16*64 bytes before timeout.
F4 RxCount returns actual ring used count under critical section. Real UART1 ring
is 512 bytes, usable511, hence <=8 reads for an intact snapshot. Host mock has a
larger capacity; reply-position tests explicitly cap injected queue at511. The
F1 RxCount symbol exists but returns0 and async transmit is UNSUPPORTED; F1 is not
newly claimed as a supported JY async backend.

Pending with no reply becomes Timeout at elapsed600ms; elapsed>600 rejects before
dequeue. Drain checks elapsed before each chunk and before committing a reply.
At exactly600ms it can inspect the existing snapshot. Millisecond time is not a
byte receive timestamp: strict arrival-time acceptance is NOT PROVEN, and a reply
queued earlier but not polled until after600ms is conservatively rejected. New
arrivals cannot enlarge the snapshot or extend the finite loop indefinitely.

Completion immediately returns, discarding the remaining tail of the already
popped chunk, matching the previous implementation. It does NOT establish zero
byte/sample loss. During configuration stream polling is suppressed, register
operations are single-outstanding, all ten read/write/verify steps remain, then
WaitingSample requires fresh accel+gyro counts before Ready. Dropping the current
normal-sample tail is acceptable in this startup phase; preserving general runtime
sample tails was not silently added or claimed.

## Reader/caller audit

Three actual JY UART consumption sites: normal IMU_Poll, async drain, synchronous
IMU_ReadRegister. Ordinary IMU_Poll exits while register-read active or write phase
is nonzero. DeviceTask advances startup before activating runtime owner; before
completion it delays1ms and continues. SharedProcess first invokes guarded Poll,
then the startup controller. Probe/Sample callbacks use the same normal Poll.
ReadStep invokes actual async start/poll for ten registers and fails on nonComplete;
there is no finite ConfigRead retry/reprobe added in this patch.

SystemStartup stages logical Apply as delegated, then IMU ConfigApply starts the
controller. Its deferred IMU ConfigVerify returns BUSY until controller Ready,
then checks verified configuration cache. Baro/Mag/Quaternion synchronous Verify
callbacks exist and use ReadOutputRate/ReadAlgorithm, but current generated startup
does not call their System*_ConfigVerify entry points (inventory records definitions
and callsites). Their GetConfig operations return effective/cached data, not UART.
ConfigAccessCheck rejects runtime owner access but does not itself check async-read
active; arbitrary external concurrent direct driver calls are NOT proven safe.
Current selected startup calls are sequential in DeviceTask; this is not a general
mutex or whole-program concurrency proof. GNSS and console read distinct assigned
UARTs. Legacy config/read API paths share the corrected parser; they retain their
existing synchronous polling deadline and do not acquire new runtime guarantees.

## Hardware and optional diagnostics

Hardware first BAUD04 read started109ms, failed709ms, TX FFAA270400 atUSART1/230400.
Early raw RX is unavailable. Normal stream remains valid; no transport mismatch,
TF cause, absent response or particular counter trigger is established. Neither
software counter is claimed to prove the actual board's root cause.

Separate optional_trace_proposal is reviewable saved owner-source snapshots/diffs,
default-off, at most2KiB by static bound. It is NOT built, measured or included in
this repair release. Parent requested diagnostic work be independent and after
the minimal repair. Do not flash that proposal as validated firmware.

## Resource report

```text
python Tools/check_task_stacks.py --config Release --memory-layout legacy --prefix "arm-none-eabi-"
powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_firmware_artifact.ps1 -TargetProfile SilverStar_F407 -Config Release 
FCCG_PROGRESS|STACK_REPORT|PLAN|1
FCCG_PROGRESS|STACK_REPORT|BEGIN|1|1|ELF and stack budget
FCCG_PROGRESS|ARTIFACT|PLAN|8
FCCG_PROGRESS|ARTIFACT|BEGIN|1|8|ELF_MAP_BIN_HEX
FCCG_PROGRESS|ARTIFACT|DONE|1|8|ELF_MAP_BIN_HEX
FCCG_PROGRESS|ARTIFACT|BEGIN|2|8|ELF
FCCG_PROGRESS|ARTIFACT|DONE|2|8|ELF
FCCG_PROGRESS|ARTIFACT|BEGIN|3|8|MAP
Device: configured=2560 estimate=2128 margin=432
INS: configured=3072 estimate=2240 margin=832
Estimator: configured=4096 estimate=3244 margin=852
Flight: configured=4096 estimate=3600 margin=496
Logger: configured=3072 estimate=2104 margin=968
Serial: configured=6144 estimate=4944 margin=1200
Telemetry: configured=4096 estimate=2136 margin=1960
Idle: configured=512 estimate=256 margin=256
{
  "indicator_in_production_init": true,
  "alignment_start_deferred": true,
  "flight_processes_alignment": true,
  "communication_does_not_process_alignment": true,
  "all_enabled_tasks_budgeted": true
}
FCCG_PROGRESS|STACK_REPORT|DONE|1|1|ELF and stack budget
FCCG_PROGRESS|ARTIFACT|DONE|3|8|MAP
FCCG_PROGRESS|ARTIFACT|BEGIN|4|8|FLASH
FCCG_PROGRESS|ARTIFACT|DONE|4|8|FLASH
FCCG_PROGRESS|ARTIFACT|BEGIN|5|8|MAIN_SRAM
FCCG_PROGRESS|ARTIFACT|DONE|5|8|MAIN_SRAM
FCCG_PROGRESS|ARTIFACT|BEGIN|6|8|CCMRAM
FCCG_PROGRESS|ARTIFACT|DONE|6|8|CCMRAM
FCCG_PROGRESS|ARTIFACT|BEGIN|7|8|heap
SilverStar memory report:
  FLASH     used=324788 remaining=199500 capacity=524288
  main SRAM used=102048 remaining=29024 capacity=131072
  CCMRAM    used=55904 remaining=9632 capacity=65536
  heap      reserved=0 runtime_symbols=0
FCCG_PROGRESS|ARTIFACT|DONE|7|8|heap
FCCG_PROGRESS|ARTIFACT|BEGIN|8|8|summary
  largest static objects:
    s_replay                         bytes= 19304 address=0x20003400 main SRAM
    s_logger_storage                 bytes= 16000 address=0x2000CD60 main SRAM
    s_estimator                      bytes= 10944 address=0x10009740 CCMRAM
    s_replay_storage                 bytes= 10368 address=0x10006EC0 CCMRAM
    s_estimator_logger_storage       bytes=  9600 address=0x2000A7C0 main SRAM
    s_hal_contexts                   bytes=  8190 address=0x20014924 main SRAM
    s_serial_stack                   bytes=  6144 address=0x10001000 CCMRAM
    s_io_baselines                   bytes=  4864 address=0x1000C760 CCMRAM
    s_aggregate_buffer               bytes=  4096 address=0x20000470 main SRAM
    s_estimator_stack                bytes=  4096 address=0x10004400 CCMRAM
SilverStar artifact check passed: target=SilverStar_F407 config=Release elf_bytes=3268476 bin_bytes=324800 heap_symbols=0
FCCG_PROGRESS|ARTIFACT|DONE|8|8|summary

```

