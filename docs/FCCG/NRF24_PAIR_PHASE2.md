# NRF24 paired transport: second source checkpoint, 2026-10-06

This isolated branch started from dailycd76d8e. Historical source checkpoint
0bb06c94cf40dac9c18f04807938a1aef963d5f2 and its Library evidence remain unchanged.
The user subsequently approved the minimum shared GSP/GSHC and typed SSMS extension.
No merge, push, hardware programming, daily-workspace changes or FLP source edits occur.
This document describes source scope; the final evidence manifest identifies the exact
validated source commit, commands, exit codes, complete logs and artifact hashes.

## Protocol and ownership

The single NRF24L01+ pair uses a32-byte physical payload and61-byte logical datagram.
M0 Capability/FLIGHT_STATE/CMD/ACK bytes and business handling remain unchanged.
The fragmentv1 contract owns the bounded assembly below AIR. Each compiled endpoint
has one static driver context; ISR does no SPI. Control/data queues each hold two
complete logical datagrams; control has priority between datagrams, not within an
in-progress datagram. Receipts require TX_DS for every fragment and are not business
ACKs. MAX_RT flushes the retained FIFO; recovery discards queued/in-progress traffic.
No transport or recovery code automatically replays a business command.

The approved new GSP type0x05 carries `[backend1, flags0, logical_length]` followed by
original AIR bytes. It fits the existing64-byte payload, has no numeric RSSI/SNR,
and leaves all old message types and GS_STATUS byte layouts unchanged. Old GSHC
safely ignores the unknown type but cannot display NRF: both endpoints and GSHC need
upgrading. GSHC explicitly clears prior SX metrics on NRF reception, records absent
metrics, suppresses explicitly unsupported parsed placeholders and handles raw-log
fallback without fake measurements. Existing SX values including -128 remain valid.
Link-export axes have no measurement curves. Existing GIF/trajectory code receives
unchanged inertial/position data; no vertical-error feature was added.

Ground core declares its two owned backend adapter payloads; the generator includes
only the selected one. GroundRadio_MetricsSupportedGet provides the selected backend
capability as an ordinary interface, keeping the bridge independent of chip calls.
The Ground gate checks the actual selected adapter, device sources, NRF single-context
bounds, generated header, distinct CSN/CE bindings and metric dispatch. No exception
was added to Power of Ten. The Flight/SX-specific ownership and source-graph checks
remain on their original paths.

## Stored profile

NRF SSMS uses schema3 on all sections; section0offset66 contains a typed tag1/version1/
length14 followed by the NRF channel, rate, signed power, five address bytes, encoded
ARD/ARC, CRC16, physical/logical MTUs and fragment version. The generator serializes
exact bytes into the existing generated storage-binding configuration. This avoids
unused LoRa macros and target C conditional compilation. SX remains schema2 with the
exact historical15-byte profile; other SX snapshot fields retain their offsets.
PersistentStorage atomic slots/banks, outer CRC32 and section hashes are unchanged.
MissionRadioProfile_Read requires an already accepted outer object, validates the
bounded profile into a private candidate, rejects unknown schema/backend/version and
publishes once on success. It is not a parser for every other SSMS section.
FLP currently consumes SSLOG mission identity and declarative decoder packages,
not this SSMS AirProfile. Its recorded sources and GUI were not modified.

## Timing and reproducible fault findings

A fixed60ms timeout lost late sticky TX_DS events and rejected valid250kbps/ARD4ms/
ARC15 configurations. The fix reads terminal STATUS first; conflicting TX_DS/MAX_RT
is a device fault. The deadline uses the actual physical payload, ESB73-bit overhead,
configured rate, ARD/ARC and a conservative per-attempt ACK/turnaround allowance:
`130 + (ARC+1)*(ceil((73+8N)*1000/rate)+130+ceil(73000/rate)) + ARC*ARD` microseconds.
It is a radio deadline, not proof of bounded task scheduling. Compile-time constraints
reject unsupported/zero rates and an out-of-register retry setting.

The old fixed250ms total assembly timeout failed a stream arriving at1/90/265ms.
A unique new fragment refreshes250ms inactivity; duplicates never extend it. A750ms
hard limit derives from the three-fragment bound. Unsigned millisecond subtraction
handles counter wrap under the documented service-time assumption. Completed-frame
duplicate history remains250ms. Independent Host processes test three physical
fragments arriving200ms apart (400ms span), full M0 golden bytes and61-byte boundaries.

Fault publication previously cleared queues before clearing the published READY flag;
a pre-fix interleaving test admitted a command during that gap. READY now clears in
that same critical section. GPIO failures during accepted static initialization now
enter the owner recovery state, keep READY false and retry in bounded rounds. Tests
include pre-fix failures, late MAX_RT, conflicting terminal flags, exact deadline,
65,537 sequence transitions, SPI/width/FIFO faults, normal and slow configurations.
Hardware-originated failures retain ordinary error paths.

Initial emitted gates rejected new C#if directives. Their complete failure logs are
retained. Those directives were removed from target C; no checker allowlist or
threshold was relaxed. A temporary additional generated profile header was rejected
by the reviewed thin-glue gate; its constants now belong to the existing storage
binding header. A Host storage runner hardcoded FATFS/Target and failed for the
imported hardware path; it now requires exactly one safe source-graph-declared diskio
path and uses that file byte-for-byte. No production source or decoder fallback was
introduced. Test-only failures and unsuccessful earlier revisions are retained.

## Acceptance boundary

HARDWARE_UNVERIFIED. No RF range, STM32 timing, flight accuracy, electrical wiring or
LoRa distance is inherited from earlier acceptance. Nordic Product Specificationv1.0
is the hardware reference: https://docs.nordicsemi.com/r/bundle/pdf_ps_nrf24l01p/;
vendor-authored mirror https://cdn.sparkfun.com/assets/3/d/8/5/1/nRF24L01P_Product_Specification_1_0.pdf.

Cross-reboot partial-frame isolation is NOT PROVEN: the volatile session starts at1
and can repeat. CRC16 can collide for old/new/mixed complete datagrams; the regression
counterexample is retained. History expiration can admit a complete stale command,
while the unchanged M0 ACK cache has its separate finite lifetime. This is neither
authentication nor permanent anti-replay. One pair, ordered physical transmission,
finite duplicate/reassembly windows and timely owner service are explicit assumptions.

Generated Power of Ten text checks, Host mocks, -fanalyzer and ARM linking establish
only their recorded scopes. Critical-contract semantics, whole-program acyclic call
closure, complete main/MSP/ISR/library callback stack proof and MCU WCET remain NOT
PROVEN. A generated stack-budget tool PASS or free linked RAM is not safe-stack proof.
Ground has existing newlib system-call stub link warnings; no zero-warning
whole-firmware or NASA/strict-original-Power-of-Ten compliance is asserted.
Final manual acceptance is incomplete while these blockers remain.


A final field-boundary regression against frozen8dae22c found that the existing
Ground CRC counter had been mapped to NRF's broader integrity counter (including
invalid payload width and conflicting TX flags). The follow-up keeps that generic
integrity diagnostic, adds a complete-logical-CRC-only counter, and maps only that
counter to Ground's existing CRC field. Invalid width leaves CRC count unchanged;
a corrupted complete logical frame increments it once and publishes no AIR bytes.
This preserves the existing GSP field meaning and wire size, without claiming a
hardware bad-CRC count that the NRF cannot expose. The countercase is a retained
pre-fix failure; the follow-up source commit and fresh check scope are in the final
manifest. Results from8dae22c remain attributed to that historical revision.
