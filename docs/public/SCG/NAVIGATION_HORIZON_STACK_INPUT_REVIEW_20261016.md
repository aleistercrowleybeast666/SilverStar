# Navigation horizon stack input review v19

This review covers the exact compiled input combinations for the mode2 KF6 and
ESKF15 configurations retained at commit615d5052. It does not change task stack
sizes, reserves, margin thresholds, library frames, callback shapes, source
coverage, recursion/dynamic-frame rejection or unknown-indirect-call policy.
It is not a complete main/MSP/ISR or hardware stack qualification.

The original v18 rejection is correct and retained: the selected JY901S no-baro
model and separate mode2 implementation differ from its reviewed mode0/1 inputs.
The read-only compiler census identifies14 KF /16 ESKF changed C sources,
26/28 changed complete input paths and2/3 changed dependency graphs. This is
more than a generated header hash change. Full ordered compiler closures,
normalized and raw source identities, exact changed bytes and reviewed baseline
diffs are retained under `.work/dev013_navclosure02` and formal evidence.

## Review of the changes

| Input class | Binding/stack consequence checked |
|---|---|
| KF/ESKF horizon kernels and ESKF numerical extension | Fixed-dimension direct numerical calls, explicit CPU-only transaction/ring storage and bounded work. Actual compiled changed objects contain zero indirect-call sites. Actual `.su` frames and linked direct paths are re-evaluated; old frame estimates are not substituted. |
| Estimator task/backend/bus and health | Direct mode2 dispatch, copied value receipts, bounded completions and coherent publication/fault withdrawal. No task entry pointer, runtime callback table or registration is added. The existing task/ISR and library proof limits remain explicit. |
| SSLOG structs and codecs | Separate explicit field codecs, bounded148/88-byte payloads and checked payload limits. They add direct functions, not callbacks. Actual logger/filter frame paths remain included. |
| Generated algorithm/configuration/capability/instance inputs | Exact mode2/HMS300 and JY901S no-baro constants, changed descriptors/routes/logging metadata. The complete generated files are captured, including the existing uncommitted catalog's physical IDs; no future generated/user bytes are learned automatically. |
| Generated identity/profile/configuration data | Complete arrays, descriptors and fixed getters. Identity differences are preserved, never relabeled as old decoder bytes. The selected compiler/header combinations are bound together. |

The changed object review uses actual ARM `objdump -dr` output for all14/16 C
translation units, not just source-pattern searches. Zero indirect sites in
those configured objects is a limited compiled-code fact, not a proof for other
preprocessor configurations or of every numerical contract. The unchanged
checker still verifies selected SD_Driver tables/registrations, startup table
bytes, target/register/slot shapes, MPU bindings and every reachable indirect
site against the actual ELF. No new callback exception is granted.

The candidate-only diagnostic temporarily supplied the exact proposed tuples
inside an isolated process to expose later stack failures; it was explicitly
not an emitted gate or acceptance. Production registration is separate and
limited to these reviewed complete source/header/dependency tuples. Old v18
records remain dated and intact. Independently approved headers and sources
cannot be mixed into an unreviewed closure, even when every individual hash is
known. Negative tests require missing, changed, added and cross-version inputs
to fail; neither fixtures nor production checks may silently approve them.

Fresh normal generation, original emitted stack reports and relevant negative
regressions must confirm the installed owner change. A later recovery or mode0/1
configuration requires its own source/object/closure review. Successful task
budgets do not close main/MSP/ISR nesting, dynamic-library provenance, WCET,
hardware margin or critical-contract manual acceptance; unresolved items remain
NOT PROVEN. No source or diagnostic is hidden to improve the result.
