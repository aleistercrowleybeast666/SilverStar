# SCG isolated repair checkpoint — 2026-10-10 11:04 UTC

Parent requested a checkpoint without interrupting running tests. This is a
checkpoint, not final freeze approval or a completed full-regression report.

## Exact checkout

- Worktree: `C:/Users/chdxm/Documents/Codex/2026-10-10/task/r`
- Branch: `fix/scg-freeze-contract-20261010`
- Base/daily HEAD: `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`
- Main repair: `a0afca6a11a9cf7066baf62afecf95fd549c9736`
- Current/final code: `24462e4aaede867e70dbecef4ab67e2a1c8adf8b`
- Current worktree is clean. Daily HEAD still equals base and has only its original
  three untracked inventory files. No merge/push/tag/PR, hardware or publication.
- Previous ccdi worktree remains separate at `5b99438ba4005ea02935e9734307e749e2e758e7`.

## Six causes addressed

1. F103 full-model equality: unified positive fixture now uses the actual unified
   importer and its verified facts authority; original full equality assertion stays.
2. F103 unified Export/Build: same real importer repair plus explicit legacy refusal
   before output/worker/SaveAs. GUI, Plan and refresh share actionable source-directory
   reimport guidance. Old model/hash is not rewritten. New regression performs actual
   saved legacy reload and source reimport. One-line status is compact; full text remains
   in tooltips and wrapped quality status. No widget or layout change.
3. Catalog physical uniqueness: identical hardware facts may have only proven,
   disjoint exact platform-part domains from one mandatory platform dependency.
   Production Scan refuses overlapping/missing/broad domains before publication.
   Original uniqueness/mixed-interface assertions remain and collision negatives added.
4. Root pytest entry: application root and src are exposed via pyproject pythonpath.
   Direct root `python -m pytest` without shim/PYTHONPATH passed both importer/doc cases.
5. Documentation replay: temporary destination gets its own WorkspacePolicy, keeping
   original path guard, byte idempotence and heading-count assertions.
6. Stack report: stale overlay synchronized to existing authoritative core payload.
   Payload, source-identity allowlists, stack thresholds and rejection checks unchanged.

## Finished checks

- `srb01`: complete two backend modules, **51 passed**, no skips/failures, at a0afca6.
  Includes previously skipped private F103/F407 real ARM/analyzer build cases.
- `srgn01`: complete GUI/native group, **138 passed**, at a0afca6.
- `srentry01`: direct root importer/doc entry, **2 passed**, at a0afca6, no warning.
- `sru01`: complete UART group, **150 passed**, at 24462e4; completed naturally
  at 11:03:35 UTC before entering Flight.
- `srpg01`: private F103/F407 architecture, Host, artifact and PoT, **8/8 exit 0**.
  Gates use actual compiled a0afca6 receipts, not regenerated/relabelled receipts.
- `srpre01`: historical repair trial **11 passed, 1 failed**. The new GUI fixture had
  settings outside its service workspace; fixture was corrected, policy retained.
- `srpre02`: corrected new GUI case **1 passed** before a0afca6 commit.

Wrapped pytest runs intentionally disable cacheprovider and retain the existing
`Unknown config option: cache_dir` warning. Earlier commentary mistakenly called it
pythonpath; corrected after reading actual warning. New pythonpath works in direct entry.
No remaining failure is confirmed in completed full groups. Flight-wide six-cause
closure and final GUI/build evidence remain pending; do not report all six fully verified.

Original baseline **560 passed, 6 failed, 12 skipped** and all diagnostics are retained
in `SCG_FREEZE_VERIFICATION_20261010.json`, `SCG_SIX_FAILURE_CLASSIFICATION_20261010.md`
and fz-prefixed logs/receipts. No failed baseline, assertion or guard was removed.

## Running jobs — do not restart or terminate

Owned exec session **1478**: `python -B run_repair_sequence.py`.
`sr-sequence.json` is its live stage record. At checkpoint it has naturally completed
UART and is executing Flight `srf01`. Its remaining automatic queue is:

1. Flight complete modules `srf01` (includes catalog identity/cache/security modules).
2. Actual GUI full 13 cases `srgui01`, including real F103/C071 ARM/analyzer builds.
3. Async full module `sra01` against srgui01 fresh receipts.
4. Unified native eight gates `srng01`.
5. Actual startup, launcher, fresh reference Flight/GroundUART generation.
6. Original PoT, architecture, Host, normal ARM, analyzer, artifact targets for each
   generated Flight/GroundUART (12 target commands).

Owned exec session **99313**: complete GUI/native group repeat `srgn02` at final
24462e4 code, currently running (more than 50 dots at checkpoint, no failure output).
This repeat is necessary because compact status/tooltip changed after srgn01.

Session **7922** private gates has finished exit 0. Root-entry session **50990**,
Git commit session **93878** and receipt discovery session **92393** are finished.
Temporary group-boundary pause file was removed after clean 24462e4 commit; no pause
remains. Original test processes were not interrupted and no duplicate GUI build started.

Use `write_stdin` for live sessions if accessible. Otherwise read C-task sr logs and
command JSONs. Wrapper exit is not authoritative: inspect pytest exit and JUnit, gate
JSON and actual logs. Do not re-run the sequence while its original process is live.

## Resume and finish

Workspace for all runners/evidence is `C:/Users/chdxm/Documents/Codex/2026-10-10/task`.
Python: `D:/python_software/SilverStar/apps/FLP/.venv/Scripts/python.exe`, always `-B`.
Runners use normal ACL fixture from the original read-only daily evidence, offscreen Qt,
unique C Temp roots, native inputs/SDK read-only, and correct mingw32-make executable.

1. Wait/poll 1478 and 99313 to completion. Inspect every module XML/command receipt
   and all 28 expected gate exits (8 private + 8 unified + 12 generated legacy).
   Preserve genuine failures/skips; original Flight artifact tests may retain ten
   skips when explicit artifact fixtures are not supplied. Actual generated artifact
   target runs separately, which is not equivalent to passing skipped tests.
2. Fix any confirmed authorized regression minimally, commit and rerun affected full
   modules with new labels. Do not weaken original checks or relabel prior evidence.
3. Run `collect_repair_artifact_evidence.py` after completed builds. It preserves actual
   expected source SHAs: private a0afca6 and unified 24462e4. Copies only receipts,
   ELF/vector files into `repair-artifact-evidence/`, no vendor duplication. An initial
   discovery helper trial included unified receipts; corrected using actual unified
   index exclusion, without product/gate changes. `srprivate01-build-index.jsonl` is exact.
4. Run `summarize_scg_repair.py` only after all expected receipts exist. It records
   per-run SHAs, versions, every skip, baseline, diagnostics and untouched daily state.
   It is prepared, not yet executed; no final aggregate currently exists.
5. Finish `apps/SCG/docs/SCG_FREEZE_CONTRACT_REPAIR_20261010.md`, copy baseline/repaired
   logs/metadata and compact artifacts into a repository evidence directory, hash
   them and commit evidence separately. Parent asked code and evidence hashes, before
   merge/push/tag. No final evidence commit yet.

Backend tests and private builds ran at a0afca6; only compact UI status/tooltip and its
GUI assertion changed afterward. Final other groups, full GUI/native repeat and unified
receipts use 24462e4. Exact source revisions must remain explicit, not advertised as one
all-final-version run. Repeating ten-minute backend builds is unnecessary for a status
string change unless new evidence establishes a backend concern.

## Non-negotiable remaining limits

Formal USB stays **BLOCKED**, b66 independent safety review **NO_PASSED_OUTCOME**.
Do not retry/bypass stopped review or run malformed USB/owner-expression research.
PoT remains F Prime-inspired adaptation, critical-contract **NOT PROVEN**; whole-program
stack/WCET and hardware remain outside this software evidence. Do not mark freeze approved.
No GSHC/FLP, FINAL, flight math, GUI layout or daily source changes. No DAPLink/serial/
flashing/START. Only isolated code and evidence commits; parent reviews integration.
