# Independent release prerequisite: C runtime and project version identity

2026-10-24 status clarification: the OPEN statement below describes the retained
2026-10-18 candidate. Current normal generation calls `FirmwareIdentity_Resolve`
and emits version overrides before includes, with conflicting external overrides
rejected. See [current version management](../public/shared/VERSION_MANAGEMENT.md).
This source implementation does not retroactively repair the historical ELF,
prove every release gate, or constitute hardware acceptance. Preserve the
candidate identity and evidence below unchanged.

Status: OPEN, not implemented in the TF/UART diagnostic batch of 2026-10-18.
Owner: release/build identity workflow; separate from TF persistence and UART
recovery. No version strings, generated candidate files or flash contents were
changed to address this item.

The candidate project `SS_0_5_CAL_TF_CANDIDATE_20261018_01` declares project
firmware version `0.1.3` and target `SilverStar_0_1_3`. Its effective C defaults
remain version `0.1.2`, build `0`, log tag `SILV0102`, and empty explicit build
identity fields. `reference_provenance.test_build` is absent, so that optional
SCG override path emits no runtime version/build override. These defaults are
present in the actual candidate ELF/BIN and match the UART display; the mismatch
is not evidence that an earlier firmware was flashed.

Before release, establish a single explicit source of runtime/build identity,
validate consistency between project metadata, effective preprocessor values,
INFO/DIAG/CAPS literals, SSLOG build tag and diagnostic ELF binding, and fail
packaging on inconsistent or missing release identity. Keep display version,
maintenance/file-service schema versions, lineage metadata and exact build
source/artifact hashes distinct. Retain the auditable dirty source snapshot for
development builds; do not substitute the project lineage commit for it.

Proposed offline regression: generate into a separate versioned fixture; verify
ordinary release and explicit test-build paths, deliberate mismatches, missing
build metadata and log/diagnostic bindings. A future implementation belongs in
the owning generator/config payload and should be checked in fresh generated
output. No whole protocol upgrade is required by this item.

Recorded candidate ELF SHA-256:
`7056eac7d4de282eebf2f7b1f637ca1b30948e192eb086167121860d763c2f44`.
Detailed unchanged-source, preprocessor and binary evidence is retained in
`.work/dev013_tf_resume_20261018_v6/version_audit.json` and that batch's `REPORT.md`.
Current diagnostic evidence is retained in `.work/dev013_tf_uart_diag_20261018_v7/`.
