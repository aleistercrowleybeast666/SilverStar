# SCG freeze contract repair - final software evidence, 2026-10-10

Code base: `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`. Main repair: `a0afca6a11a9cf7066baf62afecf95fd549c9736`.
Final code: `819eec98347e96aa6548012be159e6a6c58bd435`; isolated branch `fix/scg-freeze-contract-20261010`.
Worktree: `D:\Codex_Work\2026-10-10\task\r`. No merge/push/tag/publication or hardware action.

## Six-failure classification and repair

| Original failure | Actual repair and final evidence |
| --- | --- |
| F103 full model equality | Positive fixture uses the actual unified importer and pinned authority. Full equality assertion retained. Complete backend modules pass. |
| F103 unified Export/Build from legacy facts | Explicit legacy preflight refusal before output/worker/SaveAs. GUI, refresh and Plan agree; actionable original CubeMX source reimport is exercised through save/reload and real UI. Old identities and pinned hashes are not rewritten. F103 first-batch actual build passes. |
| Duplicate physical facts in platform variants | Production Scan accepts duplicate hardware only with proven finite disjoint exact MCU-part domains from mandatory dependencies. Overlap, missing, optional, broad and wildcard domains reject. Full platform identity/cache/security and round2 modules pass. |
| Importer tools package missing from test entry | Pyproject exposes application root and src. Direct root python -m pytest without import shim or PYTHONPATH passes both original importer/doc cases. Full runtime module passes. |
| Documentation replay destination policy | Test destination has destination-root WorkspacePolicy. Guard, byte idempotence and heading-count assertions retained; full runtime module passes. |
| Stack-report overlay stale | Overlay matches the existing authoritative core payload byte-for-byte: SHA256 8de5e90798c76a53c3acd3f178726cf6d0a94ed06b996ea717e892748c23bb47. No allowlist/hash/limit expanded. Full runtime and stack modules plus generated artifact targets pass. |

## Complete affected modules

| Run | Passed | Failed | Skipped | Source commit |
| --- | ---: | ---: | ---: | --- |
| srb02 | 51 | 0 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| srgn03 | 138 | 0 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| sru02 | 150 | 0 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| ds-flight01 | 271 | 0 | 10 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| srgui01 | 13 | 0 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| ds-async03 | 16 | 0 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |

Total: **639 passed, 0 failed, 10 skipped**, 649 explicit affected-scope cases.
Additional direct root entries: srentry02 two cases; D entry ds-entry01 sixteen cases. Not counted in complete-module totals. Earlier source-version runs are not counted twice.
This covers every case in the recorded complete affected modules, not all SCG test files.

Every final complete group, final first-batch F103/C071 receipt and final private
F103/F407 build/gate runs at `819eec98347e96aa6548012be159e6a6c58bd435`. Earlier a0afca6 and
24462e4 runs remain separately archived, with their actual source identities.

Ordinary review of 24462e4 found a further catalog P2: case/separator spellings
could appear disjoint despite matching one runtime MCU. The original matcher token
function body is unchanged and shared from core/platform_tokens.py. Catalog domain
sets, collision owners and identity keys use that same rule; empty canonical tokens
remain rejected. Three equivalent spellings reject in actual Scan before publication,
with runtime equivalence proved; distinct normalized model and original negatives pass.
Complete physical identity and internal platform refactor modules run in final Flight.

## First-batch actual F103/C071 evidence

| API / part | Normal + analyzer executed commands | Recorded warning diagnostics | Source commit |
| --- | ---: | ---: | --- |
| Unified first-batch / STM32F103C8T6 | 339 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| Unified first-batch / STM32C071FBP6 | 351 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| Private regression / STM32F103C8T6 | 339 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |
| Private regression / STM32F407VET6 | 387 | 0 | `819eec98347e96aa6548012be159e6a6c58bd435` |

Private F407 is a regression only; it does not substitute for first-batch C071.
The archive contains each actual compile/backend receipt, normal/analyzer ELF and
vector bytes with hashes. CPU/IRQ architecture and artifact checks use the actual
candidate and independent SDK evidence; no hardware behavior is claimed.

All **28 original software gate commands returned 0**: private F103/F407 eight,
unified F103/C071 eight, fresh Flight/GroundUART twelve (PoT, architecture, Host,
normal ARM, analyzer, artifact). Actual launcher and Qt startup/normal shutdown passed.

## Preserved baselines, skips and warnings

Original baseline: **560 passed, 6 failed, 12 skipped**. All raw original logs,
commands, classification and compact artifacts remain under `baseline/`. Initial
repair trial srpre01 retains 11 passes and one new fixture setup failure: settings
outside the service workspace. The fixture was corrected without relaxing policy;
srpre02 and the final complete GUI group pass. Initial Flight srf01 retains
215 passes, five failures and ten skips: sparse checkout lacked the unchanged GSHC
parser and two committed historical fixtures. Actual failure tracebacks and exact
Git/SHA256 identities are retained; the original test bodies run on checked-out
baseline dependencies in final Flight, with no GSHC code change or test redirect.
P2 precommit srnorm01 retains an import-cycle error before collection. Moving the
shared function from hardware to core corrects that dependency; srnorm02 fourteen
checks pass, and final complete groups rerun afterward. Receipt discovery initially included
unified receipts, then was corrected using actual unified index exclusion; product
code and gate behavior were unchanged.

sra01 retains two synchronous rendering threshold failures: 0.7795494 / 0.8358071
seconds versus the unchanged 0.75 second bound while the owned backend compile
sequence was active. Final ds-async03 runs the entire unchanged async module serially
after verified migration and actual quality rechecks. No threshold/skip/xfail was changed.
Final sync refresh: F103 0.528781 seconds; C071 0.526871 seconds (< original 0.75).
Max Qt interval: 0.074654/0.083199 seconds (< original 0.5), 57/83 ticks, one
Plan each on the worker. Exact measured JSON bytes are in async-final-response/.
Serial GUI responsiveness evidence does not guarantee timing under unrelated
concurrent heavy compile load; the prior failures remain visible for review.

C-disk emergency interrupted srf02 and Flight analyzer without completed outcomes.
The independent migration task terminated all fourteen owned paused processes.
D continuation preserves completed source-819 evidence and reuses actual generated
Flight output; static-analysis forces a complete serial recompile; artifact is
the original target. New TEMP/TMP/logs remain on D with an 8 GiB stop threshold.
ds-async01 preserves 12 passes/four alias refusals in original XML. Updating only
verified output locators leaves model/receipt/ELF hashes unchanged. ds-async02
preserves 14 passes/two stale record failures because the pointer path is part of
the real input digest. Original quality records are saved; actual architecture
and artifact operations regenerate new records with no stale/hash guard bypass.
Ordinary independent review of 819 closes catalog P2: six tests, exit 0, unchanged
HEAD/source hashes/clean worktree, archived under ordinary-catalog-review-819.
Evidence limitation: importing the orchestration helper accidentally reran entry
and aborted async before collection due existing basetemp, overwriting two early
D logs/command files. The original failed async XML and initial sequence metadata
remain; original log bytes are unavailable. Sideeffect files and correction record
are archived; no product code or test body was changed. The runner now has a
main guard. Final ds-async03 command/log/XML are separate complete evidence.

Skip explanations (original test assertions remain):

- `tests.test_firmware_artifact_protocols::test_real_artifact_matches_maintenance_selection[ENABLED]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_matches_maintenance_selection[DISABLED]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_opposite_maintenance_selection[ENABLED]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_opposite_maintenance_selection[DISABLED]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[ENABLED-missing]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[ENABLED-duplicate]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[ENABLED-invalid]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[DISABLED-missing]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[DISABLED-duplicate]`: Explicit real ARM Release artifact fixture required
- `tests.test_firmware_artifact_protocols::test_real_artifact_rejects_ambiguous_selection[DISABLED-invalid]`: Explicit real ARM Release artifact fixture required

The ten artifact-protocol fixture cases require explicitly supplied independent
maintenance-enabled/disabled real Release roots; this run does not supply that pair.
Fresh generated Flight artifact-check is separately executed and is not counted as
passing these skipped cases. Previously skipped private Native build cases now ran.
Wrapped pytest runs retain the pre-existing cache_dir warning after disabling
cacheprovider. Original srentry02 direct root entry has no such warning; D entry
ds-entry01 disables cacheprovider and retains that warning. Native receipts have
zero warning diagnostics. Legacy diagnostics are preserved without claiming a zero-warning gate:

- `srlegacy-Flight-host-tests`: 1 warning lines; see exact log.
- `srlegacy-GroundUART-all`: 4 warning lines; see exact log.
- `srlegacy-GroundUART-static-analysis`: 4 warning lines; see exact log.

## Reviewable freeze scope and remaining limits

Candidate for ordinary review/integration: these six contract/test-source repairs
plus the subsequently reported catalog normalization P2 closure,
the current private first-batch F103/C071 software workflows and verified emitted
normal gates. Parent owns independent ordinary review and serial SCG/GSHC/FLP integration.
No daily merge or freeze approval has been performed. UI widgets/layout, flight math,
FINAL, GSHC/FLP and daily source remain outside this edit scope.

**Formal USB release remains BLOCKED.** b66 independent safety review is
**NO_PASSED_OUTCOME**, has not been retried/bypassed and is not marked reviewed.
No malformed USB/owner-expression research was executed. PoT uses the project's
F Prime-inspired text adaptation; critical-contract acceptance **NOT PROVEN**.
Whole-program stack/WCET, PCD/IRQ physical scheduling and hardware remain outside
software evidence. Passing builds does not admit generic unknown configurations.
Original guards, assertions, source identity hashes and limits remain intact.

Evidence directory: `docs/evidence/scg-freeze-contract-repair-20261010/`.
Reproduction scripts retain actual original absolute paths and source inputs; use
the recorded D process environment/migration maps for continuation. They are
evidence of exact executed commands, not a self-contained vendor distribution.
The manifest hashes original saved bytes; its local `* -text` attributes preserve
new evidence bytes in Git and do not modify source attributes or admission identities.

The original startup record retained an inaccurate inherited daily/merged scope
phrase. Its metadata correction names the actual isolated checkout and preserves
the original record/hash; all source identities, timestamps and results are unchanged.
