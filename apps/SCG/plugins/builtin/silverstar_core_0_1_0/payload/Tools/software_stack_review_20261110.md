# Current source stack input review, 2026-11-10

This supplements `software_stack_review.md` for the six exact
`convergence-20261110-{f4,capture,h7}-{Release,Debug}` cases. The previous ten
cases and their review bytes remain unchanged. It retains the same source,
artifact, toolchain, callback-origin, direct/library instruction, task/PSP,
reset/MSP and exception rules. It does not authorize another callback registry,
sensor profile, compiler, arbitrary configuration, stack exception or lower
margin. The 256-byte task context allowance and 256-byte minimum spare remain.

## Input and independent acceptance

The firmware source is SilverStar `e143188dbad9ca0a70dfdc27f52b4226a370cfe8`.
This change repairs proof tooling; it does not change that C firmware. Candidate
A was created through `FccgService` and `TargetGeneration_Apply`, then compiled
and linked with Arm GNU 14.3.Rel1. Its emitted old strict checker failed: the
F407 complete input no longer matched, and H743 selected SYNC400 rather than
the old raw-I2C instance. These are missing proofs, not observed stack overruns.

The three configurations are the F407 reference with E28, F407 reference plus
the existing installation-capture/JY901B capture profile, and imported H743
ESKF20 plus the existing BMI088 SYNC400 I2C and opt-in magnetic rotation plugin.
H743 uses the existing software-only synchronized sensor fixture. Its copied
GPIO/EXTI source is sealed input, not evidence that a board has these wires.
Neither SPI nor a raw/synchronized mixture is admitted by this review.

Each new case independently records all selected C, headers, assembly/linker
inputs, Make declarations, actual compiler and ABI headers, linked external
archives/CRT, every object/stack/dependency file, and complete ELF/map bytes.
The checker never creates a case. Its constant seals the full manifest and the
case seals this document. Delivery requires a new ordinary generation B in
another directory, an independent compilation, equality of every A/B sealed
artifact, and B's emitted strict `stack-report` without patching B. Until those
steps pass, candidate inspection is diagnostic, not acceptance.

## Source delta and ownership review

Relative to the prior F407 and installation cases, changes are logging event
IDs and bounded publication, magnetic calibration status/identity checks,
console status, optional installation interfaces, GPIO edge timestamps, and
generated configuration/decoder data. The capture case additionally adds the
fixed-installation magnetic base accessor and qualified-provider observations.
No UART/DMA/SD handle declarations, their BSS initialization, reciprocal MSP
links, IRQ handle arguments, HAL callback installers or registration settings
changed. The new source performs no handle copies or pointer replacement.
All those unchanged HAL inputs still participate in the new full closure.

The calibration apply path validates provider and sample instance, physical
units, descriptor and physical-device identity before indexed publication.
It rechecks current intrinsic generation/CRC/identity inside the critical
section, then applies the fixed/qualified rotation before publishing. The
new base accessor checks non-NULL output, active/pending/dependency state and
generation/CRC under the same lock, and copies nine matrix entries from the
already validated fixed record. No callback is stored in these records.

Qualified installation observations check active source, descriptor identity,
sequence/epoch, increasing time and bounded freshness. False admission uses
short-circuit and conditional expressions before reading a descriptor or NULL
sample. F407 JY901B remains unqualified for native synchronized installation;
compiling capture support does not manufacture that qualification.

For H743 the reviewed delta also contains MMC5983MA trigger timestamps,
SensorImuAdapter's synchronous provider publications, the fixed SYNC400
instance, GPIO input declarations/EXTI2/EXTI3 wrappers and magnetic rotation.
The new GPIO ISR loops over the fixed context capacity and calls the existing
critical-section time reader. ConsumedEdgeGet checks the mapped ID and both
outputs, then snapshots the timestamp and matching consumed/current count
under the interrupt lock. New IRQ handlers call HAL_GPIO_EXTI_IRQHandler with
their literal pin; they are actual ELF vector entries and are included in MSP
analysis. No ISR invokes fitting, allocation or another dynamic dispatcher.

The selected sensor adapter rejects invalid/missing edge pairs, timing gaps,
unverified/clipped frames and a pair crossed during the read before qualified
publication. Stop/error revoke qualification. MMC5983MA supplies its real
magnetic trigger before the temperature phase, validates raw/physical samples,
and passes fixed calls to the owner. Published timing remains explicitly
uncertain; GPIO timestamps are not measured sensor latency.

The magnetic rotation fit and eight-entry history are static DeviceTask-owned
state. All matrix/vector loops have fixed 3/4/9 bounds; history scans are
bounded by the owner-maintained count of at most eight. The 40-pair update has
finite/magnitude/time/observability checks and a bounded candidate step.
There is no function pointer, recursion, variable stack allocation or new
task. Maintenance revocation uses the existing critical section and requests
the DeviceTask owner to reset mutable fitting state. Adoption rechecks that
revocation has not occurred while publishing its bounded logger event.
Full logger queues are ordinary errors: adoption is revoked and deferred fixed
fallback records retain their time/revision for a later bounded retry.
`AppTask_Device` really reaches the selected preparation/readback, magnetic
observation, fit, service and logger routines; merely linked functions are not
used as proof of scheduling. Their complete normal, error and assertion call
paths and selected math library implementations are included in the budgets.

## Exact immutable SYNC400 callback binding

The common sensor initialization/bus bodies retain their prior exact hashes.
The separately checked SYNC400 instance only initializes the common adapter
with `Bmi088Sync400_ProfileGet`, whose entire wrapper is checked and returns
`SensorBmi088Sync_ProfileGet`. The complete synchronization implementation is
checked, including its bounded image writes and register verification. The
actual getter must load the one read-only 188-byte `s_sync_profile` object.
Its linked slots at offsets 16, 20 and 24 must equal the Thumb addresses of
`SensorBmi088Sync_Prepare`, `SensorBmi088Sync_FrameRead`, and
`SensorBmi088Sync_Readback`. The third callback is non-NULL and its readback
path is included; the raw profile's NULL-only extra verifier is not reused.

The exact initialization caller sets, sole indirect instruction per common
dispatch function, linked targets, profile layout and table bytes are checked
before resolving edges. Mixed raw/SPI sources, writable/wrong-sized tables,
altered wrapper/profile/body/caller, wrong slot, absent target and additional
indirect sites reject. Complete input/artifact admission remains an additional
requirement; this local binding alone cannot accept firmware.

## ABI parsing, priorities and remaining limits

GNU readelf writes raw non-UTF-8 byte constants in DW_AT_const_value for the
embedded decoder. The tool now preserves every byte through a one-to-one
Latin-1 decode only for the DWARF dump. ASCII DIE, type/member names, sizes,
offsets and reaching loads are still parsed and checked normally. No byte is
ignored/replaced, and other command outputs remain strict UTF-8.

The exact F407 priority source/vector inputs are unchanged: the reviewed
priority domain is still 0/5/6/15 and four configurable nesting levels. H743
retains the full 16-level conservative bound, including its added GPIO vectors;
this review does not reduce it to the handful of configured IRQs. Both add NMI
and HardFault, extended FP exception frames and main/reset usage. HAL object
provenance, NULL-only slots, actual DWARF ABI and all indirect load sites are
resolved separately for each real Release/Debug ELF.

These cases have control research disabled; they do not claim current PID/LQR
integration coverage. Existing enabled control cases remain separately sealed.
Stack proof is not a whole Power of Ten critical-contract acceptance, stack
high-water measurement, WCET, concurrent-fault proof or flight qualification.
The global manual critical-contract review remains NOT PROVEN unless its own
review explicitly closes it. Physical synchronization, actual IRQ nesting and
timing, cache/DMA behavior, storage/power-loss and board/flight validation
remain hardware tasks. No failure report is converted to a historical pass.
