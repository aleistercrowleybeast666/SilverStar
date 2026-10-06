# InputVoltage adapter relocation, 2026-10-06

Base: e811e0a04d371e57f26f315a9e35ceacb2b62f72, isolated branch
`codex/scg-legacy-gates`. No hardware, daily branch, GSHC or FLP changes.

`power_service.c` implements the System power interface, so it now lives in
`Devices/Power/InputVoltage/Adapter/Src`. The manifest, reference import aliases
and Host source/include paths follow that ownership. The normalized complete
source is identical: SHA256
`d375930dbb1d1efe7d73640f3e1c9b90b6d862b36b92db39843bade31bc08e6c`.
Conversion, synchronization, assertions and failure paths did not change.

Fresh generated `.work/power_verified/Flight_Controller` was produced by
`.work/generate_health.py power_verified`, using the verified official Q2 F407
model, KF6 and unchanged M0 parameters. The V7 task-stack binding adds only the
exact moved source, compiled dependency graph and resulting decoder profile
hash. Record layout is unchanged; generation/profile identity changes, so this
project requires its newly generated exact decoder package.

`python -X utf8 .work/run_health_gates.py power_verified` ran actual ARM GCC
14.3.Rel1 compilation/linking, GCC `-fanalyzer` compilation, emitted architecture,
Power10, artifact, task-stack and memory targets; every exit was 0. Full commands,
UTC times and log hashes are in `.work/evidence/power_verified/results.json`.
The baseline architecture failure was the two forbidden System includes in
Device core; both are now permitted Adapter dependencies without gate changes.

The emitted Host power case compiled the real moved source and passed all 15
checks. Its explicitly selected wrapper prefix excludes the unconditional
storage child; this is power coverage, not a full Host-suite result. Evidence:
`.work/evidence/power_verified_host/{selected.log,results.json}`.

Linked Flash is 331008 bytes (+8 against e811), main SRAM 112756 and CCM 46760
(both unchanged). Main SRAM spare is 18316/131072 (13.974%), below the 20% target.
All seven configured task budgets pass; Estimator remains 3260/4096. These are
scoped task estimates, not a whole-system MSP/ISR or hardware stack proof.
Power10 critical-contract review remains NOT PROVEN despite exit 0.

Intermediate attempts are retained in evidence: an initially generated V6
checker rejected the new path; normal regeneration correctly preserved the
project-owned checker. Deleting that disposable checker made the plan invalid;
it was restored and final validation used a new directory. No generator
ownership protection was changed. The unrelated pre-existing import-adapter
pytest rejects its newer architecture EIDE regex before reaching the Host
adapter; it remains a recorded failure pending the next contract batch.
