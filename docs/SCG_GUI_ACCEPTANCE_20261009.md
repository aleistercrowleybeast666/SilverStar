# SCG GUI acceptance — 2026-10-09

Base: `6fe76d87d05de6b7528e74d9c423df6d9217e47f`. The working tree was clean apart from the three pre-existing `work_*_20261006` user files. No user window, unsaved model, serial port, probe, or target hardware was controlled. Only SCG GUI files and isolated tests were changed. Flight algorithms, protocols, generator payloads, checker thresholds and allowlists were not changed.

## Findings and GUI changes

| Finding | Evidence / resulting behavior |
|---|---|
| Ground missing radio resource stays black | `GroundTargetPage.Configuration_Set` previously constructed views without `validation_error`. The shared table colors only rows carrying that field. Ground now marks missing/wrong-kind assignments, fixed-role mismatches and affected authoritative constraint/conflict diagnostics red. A valid refresh removes the error. |
| Ground advanced rows all pass while generation refuses one item | The table contains radio requirements only; PC and activity LED checks occur separately in `GroundTargetIssues_Get`. Enabling activity LEDs before selecting SSGS0.5 leaves the LED unbound although all six radio rows pass. The table now declares its scope and shows remaining Ground issues; the LED group shows its own error. |
| Existing board does not repair the previously enabled LED | `_GroundBoard_Change` filled hardware/radio/PC state but did not revisit the LED. Explicit board selection now adopts only a unique, declared, conflict-free activity LED candidate when the LED is enabled and neither LED binding exists. SSGS0.5 declares `PLATFORM_GPIO_6`, active-low. Existing explicit bindings are preserved, including invalid ones which continue to block generation. Refresh/import does not silently adopt a new binding. |
| Compile appears indefinitely busy | Native worker success, error and cancellation all terminated correctly in the initial probe; the specific user's completed compile loop was not reproduced. The target build entry now reports actual compile and artifact-audit phases and retains 100% exclusively for successful worker completion. Mocked make failure and audit failure remain errors. |
| PoT pass remains blue | This was an explicit `statusLevel=info` policy, not a lost result signal. The automatic result now has its own green/red row. A separate warning retains `NOT_PROVEN` and pending manual acceptance. A known critical-contract `FAIL` is red, including a contradictory stored `passed` record. The summary preserves explicit critical failure. |
| Modal PoT message delays progress termination | `_Build_Complete` opened the modal inside `_Task_Finish`'s result callback, before the progress range/value/state were finalized. It now schedules the message on the next Qt event turn; the terminal progress is committed first. |
| Two CubeMX buttons | The existing directory button is now the sole visible “Import CubeMX project” entry for both targets. Legacy `.ioc` signal/API and project schema readers remain available. No extra button was added. |

Generation is still blocked by authoritative Ground issues in `generator/multi_target.py::GroundFiles_Render`. Colors do not waive requirements. Automatic PoT success remains a limited text-check result, never completed critical-contract review, FIELD READY or NASA certification.

## Validation and limits

Initial private diagnostic probe: **9 passed**. Six new acceptance cases failed on the base and passed after the first fix. A later contradictory stored PoT pass/critical-FAIL case was demonstrated failing before its guard was added.

The first adjacent regression run recorded **75 passed, 1 failed**: the failed fixed-binding readiness fixture exceeded the Windows path limit. With a shorter isolated path, that exact case passed (**1 passed**). These runs are preserved separately; they are not presented as an executed 76-case pass.

An expanded subsequent run was interrupted after the user requested avoiding vendor copies and excess disk use; it produced no complete result and receives no pass credit. The next GUI-only run recorded **46 passed**. Final validation after the critical-FAIL guard recorded **47 passed**, exit 0, 126.78 seconds. The known `cache_dir` warning from disabling pytest's cache provider is retained.

Final test command uses the existing isolated settings/path runner and offscreen Qt, with a short `.work/g9v` temporary root:

```text
../FLP/.venv/Scripts/python.exe -u -B ../../.work/gui012_20261008/run_pytest.py
  tests/test_ground_gui_acceptance_20261009.py tests/test_system_log_gui.py
  tests/test_task_progress_busy.py tests/test_cloud_progress_20261005.py
  tests/test_ground_activity_configuration.py -q --basetemp=.work/g9v --tb=short
```

Command cwd: `apps/SCG`; script/interpreter arguments use the corresponding relative paths. Environment: `PYTHONDONTWRITEBYTECODE=1`, `QT_QPA_PLATFORM=offscreen`. No ARM compilation, hardware test, long build, push or cleanup was performed by this GUI task. Vendor data, logs and caches are excluded from the compact evidence package.

Private offscreen screenshots were actually inspected: missing Ground radio row red; passing radio rows alongside a visible LED error and scope warning; green automatic PoT result alongside orange `NOT_PROVEN`. They use synthetic configuration and are GUI evidence only. Deferred Qt widget deletions are flushed before capturing, matching ordinary event-loop retirement.

Both user Library screenshot downloads were attempted through the current Library materialization helper and failed with HTTP **403**. No local image bytes existed. Library reads supplied image metadata and text extraction, not usable pixels; the original screenshots were **not visually verified**. IDs: `libfile_cfa0ee2a992881919af89db70b2cbf73`, `libfile_2b7435ebb524819182ce7605376dace9`. Transfer URLs and credentials are not archived.

## Confirmed user field project (read-only)

The user subsequently confirmed `D:\stm32_project\SS_0_5_TEST_FINAL`. Root project/decoder time: **2026-10-09 09:30:09 UTC+8**. Project format 17; SS0.5 / STM32F407VET6; firmware 0.1.2. Its saved Ground configuration has no hardware resources and its Ground directory is empty. This saved snapshot does not describe the user's later unsaved Ground GUI selections.

| Artifact | SHA-256 |
|---|---|
| Root `SilverStar.ssproject` | `fb72e162df37d13321ca87ab8f6c1d22f28e8e6c12e47029fd1cc156c23dd50a` |
| Flight `SilverStar.ssproject` | `cf36b85c6ef44c3ae2bb6285f25da0b01623eedf61961d28c76cec2155158146` |
| `SS_0_5_TEST_FINAL.ssdecoder` | `47394c9d1b27f76e074ce43b324dd218e3448c6a5465628fdce2c744e3afe0e5` |
| Release ELF | `86f951ac3dab0611232d1177ea649c2c219f9afdd47bd923d6ab716de93ffd4a` |
| Release BIN, 330,812 bytes | `af75cd3d33677afdc239807cb0619e01b7724595ad89a4f2ca459583440ffd05` |

Release BIN time: **09:34:20 UTC+8**. The separately appearing StaticAnalysis BIN is byte-identical. Decoder internal file checksums match; the three declared hash128 prefixes are present in the ELF/BIN, as used by `project_log_decoder_profile.c`. This is identity evidence, not full FLP opening/Descriptor validation. `firmware_commit` records reference provenance (`cc0b377...`), not a verified local HEAD; generator code obtains it from `model.reference_provenance`. It must not be used to attribute this binary to the GUI fix.

The user's quality-result file records Host/architecture/PoT/static-analysis/artifact passes. This task did not execute those tools or independently validate their full command/source scope. Original source, logs, decoder, binaries and project files were not written. Exact configuration acceptance, complete stack evidence and actual hardware results remain with the independent acceptance/bench task.

## USB integration handoff

The isolated `codex/f103-ground-usb-20261009` branch owns importer, service, source graph, assembler, Ground generator and CDC code. Its inspected interface is:

```python
FccgService.CubeMxProject_Import(input_path, model,
    risk_acknowledged=True, progress_callback=None, target="flight")
```

The existing GUI directory workflow is wired to the current service and callbacks. On backend integration, Ground must explicitly pass `target="ground"`; Flight retains the default. The Ground callback expects the existing `CubeMxImportResult.hardware` and `.inventory` contract. The new backend is responsible for rejecting absent generated code, multiple `.ioc` files and missing HAL/CMSIS/USB dependencies with actionable errors. The full Ground import/USB acceptance and post-merge regression remain pending; this GUI stage does not claim USB readiness.
