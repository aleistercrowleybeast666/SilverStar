# Six failure classification

Tested daily commit: `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`. SCG tree: `e03ca99998df2d9d75ad3e817d25d83daba2bd8a`. This is read-only diagnosis; no product, test, checker or source identity was edited. Original full-run failures remain recorded.

## F103 complete-model equality

Minimal original case: `test_usb_ground_backend.py::test_f103_dispatch_reuses_plan_f407_stays_private[f103-usb]`, with the exact fzb01 environment and command receipt. Expected: generic/private import and pinned/unified reimport yield identical full model dictionaries. Actual: false; six model fields differ, including evidence path/SHA256, binding facts hash and immutable snapshot/source digests. `fz-f103-contract-repro.json` records the exact differences and a fresh ordinary API reproduction.

Classification: known baseline, producer/consumer identity-contract disagreement; raw Windows newline bytes contribute to the evidence SHA mismatch, but absolute evidence paths also differ. The two MCU plugin JSON values and their LF-normalized bytes are equal (`fz-f103-plugin-byte-comparison.json`). Identity rules deliberately bind the full trusted facts record, not just CPU/memory/IRQ semantics. Equality cannot be obtained by merely ignoring a hash or path.

User reachability: fresh supported unified GUI import/save/reload works and its full new GUI build test passes. The legacy explicit-facts private API also plans successfully using its original facts. Saved legacy generic models are recognized by `UsbGroundBound_Is` and can be offered to the unified path, which rejects them. Complete cross-API/legacy-model compatibility is therefore not established. This is not evidence that the guard is wrong; it is a concrete unresolved compatibility boundary.

## F103 generic-model unified Export

Minimal original case: `test_usb_ground_backend.py::test_real_unified_backend_build_exact_first_batch[f103-usb]`, with `SILVERSTAR_USB_BACKEND_ARM=1`. Expected: `RenderedCandidate`, followed by real normal/analyzer build. Actual: Export raises `CubeMxImportError: Native Ground binding differs from trusted facts/profile` before writing output or compiling. The fresh minimal reproduction confirms rejected output does not exist; saved/reloaded generic model is rejected identically; unified reimport returns `RenderedCandidate`.

Classification: newly observed failing test with the same provenance-contract cause as the equality baseline, not a demonstrated new firmware/data-path regression. The unified backend selects its pinned facts, whereas the imported generic model was bound by another trusted facts record. The mismatch should remain fail-closed. No promise of interchangeable arbitrary explicit-facts models is implemented. However, the legacy saved-model GUI reachability above prevents treating this as an irrelevant test failure.

Minimum closure: explicitly settle support for legacy generic models. If supported, implement a verified reimport/migration from admitted native source to the pinned authority and exercise save/reload/GUI paths. If outside the unified contract, provide an explicit reimport-required outcome and contract tests for both supported unified positive flow and rejected cross-authority flow. Do not rewrite `facts_sha256` in place, weaken `_Snapshot_Inspect`, or silently waive the two existing failed cases. Any code/test contract change requires a separately authorized repair batch.

## Broad catalog physical identity assertion

Minimal case: `test_round2_targets.py::test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources`. Expected: every catalog device has a globally unique `(vendor, model, chipset)`. Actual: both `silverstar.device.storage.sd_sdio_fatfs` and `silverstar.device.storage.sd_sdio_fatfs_f1` use `('Generic','SD/TF Card','STM32 SDIO')`. The assertion fails before its BMI088-specific resolution checks.

Classification: old catalog/test contract issue, proved present at fixed pre-merge commit `56448bd35736221d7885a26704f2f953b0fe5055`. Both manifest JSON values/dependencies and the test body are unchanged from that baseline. One variant requires the exact F407 MCU; the other requires the F1 Flight family. `fz-catalog-baseline.json` preserves this evidence. This probe did not repair or investigate old storage functionality.

User reachability: the duplicate metadata exists in the real catalog. Because the platform dependencies differ, this global assertion alone does not prove duplicate sources or ambiguity in a supported target. New USB GUI/build paths do not select either storage plugin. Whether global physical uniqueness or platform-scoped variant identity is the intended catalog contract must be settled before changing metadata or the assertion; do not simply delete the test.

## Runtime reference importer unavailable

Minimal case: `test_runtime_safety.py::test_runtime_sources_survive_reference_import`. Expected: import `tools.import_reference_components`, then verify retained owned runtime sources. Actual under `daily_backend_pytest.py`: `ModuleNotFoundError: No module named 'tools'` at the first import.

Classification: invocation environment. The external test launcher inserts only `apps/SCG/src`; the monorepo execution CWD does not itself expose the application-level `apps/SCG/tools` package. Adding `apps/SCG` to the diagnostic launcher's `sys.path` makes the exact current importer module importable. The complete original source-retention case then passes in `fztools01` (overall two-case result: one pass, one failure). No product/test source is changed. The diagnostic command/log/XML remain separate from the original full run.

User reachability: ordinary generated firmware/runtime operations do not execute this test-time import. The SCG-root maintenance importer is available from its normal application root. No current application startup failure was observed. The body of this test is unchanged from `56448bd`.

## Runtime documentation importer unavailable

Minimal case: `test_runtime_safety.py::test_imported_documentation_replay_is_idempotent`. Expected: import `_ImportedDocumentation_Adapt`, copy only its test document to Temp, replay twice and compare bytes/section counts. Actual under the original launcher: the same missing `tools` package before adaptation executes.

Classification: the initial import failure shares the invocation cause above, but the corrected external launcher exposes a second, old test-setup error. The untouched case creates `WorkspacePolicy(workspace_root)` for the SCG source root and attempts to copy into the C-drive Temp destination, which correctly raises `WorkspacePolicyError: Path escapes authorized workspace`. It does not reach replay. The fixed `56448bd` policy source rejects the same call identically, and the test body is unchanged.

User reachability: this exact failing source-policy-to-external-destination call is in the historical test setup, not normal generated runtime operations. A separate ordinary diagnostic creates `WorkspacePolicy(temporary destination root)`, copies the same real document, executes `_ImportedDocumentation_Adapt` twice and preserves both original heading-count expectations. It passes byte idempotence and each heading occurs exactly once (`fz-doc-policy-repro.json`). This does not turn the untouched original test green. Minimum correction is the test's destination policy root plus normal importer lookup in the external launcher, never weakening the real workspace boundary guard.

## Generated stack-report source mismatch

Minimal case: `test_runtime_safety.py::test_runtime_generation_includes_stack_report`; or compare fresh `fzf01/runtime_*/Tools/check_task_stacks.py` against `apps/SCG/tools/reference_overlays/check_task_stacks.py`.

Expected: generated script bytes equal the reference overlay. Actual: generated script equals the canonical core-plugin payload exactly, SHA256 `8de5e90798c76a53c3acd3f178726cf6d0a94ed06b996ea717e892748c23bb47`; overlay SHA256 is `394c3d3b977d0b02efcd663b0d31ad1004235abe7f8ea38db06929e9bd065576`. LF normalization does not make them equal. The payload includes V10 static-bench and V11 health-finalization source identity records and their lookup entries; the overlay lacks them.

Classification: old source-authority synchronization defect, not Windows EOL and not caused by e135's two native-radio `-text` paths. Fixed pre-merge `56448bd`, the merge `2016a127`, and e135 retain the same distinct normalized overlay/payload contents. The test body is unchanged. `fz-stackreport-classification.json` preserves hashes, normalized diff and old-commit blob checks.

User reachability: normal Flight generation actually emits the payload copy, so generation is not missing the newer records. A later reference-overlay replay could restore the stale copy; that maintenance/reimport boundary is not safe to claim synchronized. Minimum repair is to restore one canonical script from the already authorized source, synchronize the overlay without expanding accepted identities or weakening rejection, and verify generated equality plus preserved unknown-input rejection. No such repair was performed here.

## Freeze decision

Fresh unified GUI and compiler checks establish their recorded positive scope. They do not eliminate the legacy-model compatibility boundary, old catalog contract failure, stale overlay, original full-run failures or skips. Correct the external invocation; separately authorize correction of the documentation test's destination policy setup. Settle legacy-model support, catalog identity versus platform variants, and canonical stack-report synchronization under a separately authorized batch, then rerun affected complete modules and original emitted gates. If catalog identity must be globally unique, retain one physical-device registration with platform adapters; if explicitly scoped variants are supported, prove per-target source uniqueness and unambiguous selection rather than deleting the assertion or inventing different physical metadata. Until these boundaries are closed or explicitly accepted as documented baseline exclusions, retain a held freeze decision; do not claim all SCG regressions or critical contracts passed.
