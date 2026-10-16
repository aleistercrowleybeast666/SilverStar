# Navigation receipt and disabled recovery: exact stack input review

Status: v20 registered and emitted; six recorded task-stack gates and 49 input/
historical regression tests passed. Complete stack and critical-contract
acceptance remain NOT PROVEN.

Development evidence dated 2026-10-16. Stable v0.1.2 remains frozen. This review
covers the recorded STM32F407 Release configurations, not all STM32 targets or
hardware/flight qualification. The separate v19 horizon review remains historical
evidence for its original source revision.

## Scope and safety boundary

The final matrix is `kf6_{0,1,2}_default01` and
`eskf15_{0,1,2}_default03` in `.work/dev013_navclosure02`. They are new validation
instances using current owning payloads and configuration derived from read-only
earlier models; no earlier project payload was overwritten. Every new ESKF
configuration has `gnss_recovery_enabled=0`. Project validation, rendering and
metadata declaration reject active recovery even with logging disabled.

The production change captures GNSS source, sample and native metadata in one
nested-safe critical section, and atomically publishes selector identity with its
freshness barrier. Internal selector corruption returns `BAD_STATE`, preserves
caller outputs and withdraws backend readiness. The backend checks this boundary
even when the mission lacks a GNSS origin. Ordinary missing origin, missing
source, invalid external packets and unsupported native time retain ordinary
paths. A later moving fix still cannot establish the mission frame.

The optional recovery receiver, qualifier, configuration codec and replay/horizon
companions are preparatory code. The backend does not activate them. Active
integration, action/receipt wire records and the complete 1/5/30/120-second outage
matrix remain unfinished. Their critical contracts are **NOT PROVEN**.

## Review of compilation changes

The v20 input registration uses the final `default_stack_census02.json`, complete
source/header tuples and actual ARM objects. The associated input archive retains
full changed sources, prior sources, dependency reports and disassembly. The
review adds exact tuples rather than a filename, directory or callback exception.
All selected first-party sources remain covered, including unused recovery code.

Reviewed changes are limited to:

- Atomic GNSS receipt and selector state handling. Locks protect coherent
  snapshots; device processing and recovery I/O remain outside the publication
  lock. Global reinitialization requires quiesced consumers.
- The backend's captured metadata use, owned-input fault latch and no-origin
  fault check. Existing normal and fault expectations are retained.
- Optional recovery companion paths in ESKF replay and horizon code. Ordinary
  entry points supply a NULL companion. Some shared recovery helpers remain
  linked in modes 1 and 2; the conservative stack analysis includes their linked
  direct-call paths. Activation state and companion global storage are not
  introduced into the default backend lifecycle.
- Generated configuration, mission parameters, descriptors and decoder metadata
  for the explicit disabled policy and the new validation identities. The
  104-byte configuration and CRC identify actual binary32 values. These values
  are not an approved flight policy.

Actual disassembly of every changed compiled object is checked for indirect
calls. The new code introduces no callback registry, task entry pointer, linked
library, allocation, stack allocation policy or third-party exception. Existing
HAL, FreeRTOS, FatFs, radio library and toolchain provenance/licensing remain in
their owning packages and existing inventories; those dependencies are not
original Power of Ten compliant firmware by implication.

Only the exact input registration and revision label change in the stack
checker. All other analyzer functions, callback bindings, task stack capacities,
context allowance, minimum margin, source coverage and failure expectations must
remain AST-equivalent. Negative tests reject changed sources, changed headers,
changed dependency graphs and mixtures of individually known compiler inputs.
An active-policy header is not admitted by this disabled-policy registration.

The recorded build commands, flags, compiler version, real ELF/.su files and
artifact hashes are part of the evidence. A source tuple by itself does not prove
the compiler options or a semantic safety contract. Diagnostic candidate probes
are labelled as such and are not emitted gate passes.

## Evidence and limits

Final commands, gate results, task figures and hashes are indexed by the
navigation acceptance entry and its evidence manifest. All initial gate failures,
fixture failures and superseded revisions remain distinguishable. The generator
correctly rejected a partial generation after its owning Host harness changed;
that partial project is not a successful validation input.

Power10 is the SilverStar F Prime-inspired project adaptation. Text checks and
assertion candidates do not establish useful assertion density, every checked
return, guard dominance, bounded STM32 timing, an acyclic whole program or manual
critical-contract acceptance. The checker explicitly retains critical-contract
review **NOT PROVEN**. Complete main/MSP and relevant ISR nesting, physical stack
high-water marks, WCET, navigation accuracy and hardware/flight acceptance remain
**NOT PROVEN**. CPU fixtures, including 5 ms stress inputs, do not establish the
actual device's nominal sampling schedule.
