This isolated increment builds a private F103 Ground candidate from the
reviewed complete native source profile: one FS CDC transport, one bare M12
SX1281, actual native clock/startup/linker/USB/HAL/GPIO owners, and no RTOS or
extra LED owners. Normal `GroundFiles_Render` still rejects the capability
marker. No user project, daily branch, GUI, FINAL candidate or board is changed.

The native runtime gates publication until clock/platform/bridge initialization
and the driver's coherent verified-chip postcondition all succeed. A fresh
unmasked clock-progress probe precedes each PC publication. Unknown bridge
results fail closed. Clock and initialization faults reset PC sessions, stop
USB, retire the started radio, hold radio RESET even before platform success,
and retain a permanent fault. Radio/PC transient errors keep ordinary diagnostic
paths; this internal publication state does not substitute for protocol READY.

The radio main owner now samples seven stored timestamps before its existing
critical sections. Its wake-up SPI/Busy operations keep tick/USB IRQs live;
the native DIO ISR only latches a flag. A complete control result is constructed
locally and published under the same lock on timeout and normal completion.
No density assertions, threshold changes or new gate exemptions were added.

Known HAL source derivatives retain the original licensed input and replayable
patches. Used SPI polling paths gain finite bounds while preserving ordinary
timeouts/unlocking; the UART alternate data pointer is checked before access.
The original `_sbrk` is excluded from compilation and a forced strong rejecting
ABI is linked. The normal and analyzer ELFs have no retained dynamic allocation
entry points. Static USB class storage and fixed native ST callbacks remain
controlled vendor exceptions; they are not an authorization for a heap or
runtime callback registry.

The separate CDC bulk derivative checks class initialization, endpoint opening,
application initialization, TX, RX rearming, packet bounds and cleanup results.
An ambiguous LL/close failure retains TX/class ownership, cancels publication
and prevents false successful reinitialization. LL initialization and actual
core/data-stage return paths propagate failure. Original inputs, derived owners,
same-path patches and immutable-byte manifests identify every replacement.

No shared EP0 patch is integrated. Class Setup and EP0 RxReady functions are
byte-identical to the native input, verified as preservation only. The b66 EP0
independent review was interrupted by platform safety; it has no review outcome
and was not retried. Reset/control/complete asynchronous lifecycle acceptance
remains NOT PROVEN. This private compiled candidate is separated from that
unreviewed dependency by the normal generation block and explicit metadata.

The final generated directory and verification manifest record one auditable
source snapshot based on 7c6ae5653c4b9696d9da80a20df5297a92b2deb0. Real GCC ARM
compilation, saved-assembler CPP/GAS dependency closure, normal and `-fanalyzer`
linking, object/ELF attributes, independent IRQ positions and physical section
bounds were executed. Artifact checks rehash both generated files and build
artifacts. Retained library members are taken only from positive-size sections
in physical memory; paths containing spaces and archive digests are preserved,
and loaded/discarded members or wildcard selectors are not called linked code.

The generated Power-of-Ten command is unchanged and run exactly as emitted.
Its text scope is 18 first-party C files and 179 functions, with 507 checks,
126 syntactically eligible runtime candidates and 48 nonblocking recommendations.
Its semantic critical-contract review explicitly remains NOT PROVEN. The
existing text checker excludes imported/derived vendor owners: entry/class/LL
derivative contracts therefore still need explicit manual review. A text PASS
does not prove whole-firmware source coverage, recursion, checked returns,
assertion usefulness or acceptance of those controlled exceptions.

Full current native tests, existing Ground runtime regressions, generated Host
executables, pre-fix runtime failures and all intermediate compiler/test/gate
failures are saved separately in
[the evidence manifest](evidence/native_classic_cdc_runtime_20261010/verification.json).
The final 12c native suite had 164 passes in 241.23 seconds, and the separately
executed existing Ground runtime suite had 83 passes in 55.27 seconds. Neither
suite skipped a case. All five generated Host executables and the architecture,
artifact and unchanged Power-of-Ten commands exited zero. The fresh receipt
records 333 successful commands, zero compiler warnings, 113 generated-file
hashes and 545 build-artifact hashes, all rechecked before evidence copying.
The Host ports use MMIO/USB/radio mocks; terminal-trap interception in the Host
contract harness is test-only, never target recovery. The existing pytest
`cache_dir` configuration warning is retained. This is not a whole-monorepo pass.
Earlier missing `sd_sdio_fatfs_f1` fixture failure and older gate failures keep
their original scope and outcome.

F407 is still rejected for this runtime candidate. Its actual HAL TIM1 timebase
has no implemented native clock contract here; its distinct class/LL profile
also needs review. The earlier strict ABI probe reports missing
`USBD_CLASS_BOS_ENABLED` and `USBD_USER_REGISTER_CALLBACK`. No SysTick substitute,
invented clock, `-Wundef` suppression or new broad default was used.

Whole-program library/indirect-call stack bounds, task/MSP/ISR nesting, STM32
WCET, clock/SPI/radio waveforms and hardware/flight qualification remain NOT
PROVEN. No physical MCU recovery, timing margin or original Power-of-Ten/NASA
certification is claimed. Any failed or unresolved critical contract still
blocks normal publication. No independent review of this runtime increment has
been claimed.
