# Ground GUI integration candidate — 2026-10-09

Compilation progress was committed separately as `88fa7a7`. Backend commit
`d1eb4bf95a52a192dc750c7a18dd23d8145386cf` was then cherry-picked without conflicts
as `7eba519f64d0a6c9eaa7c64a2f202ea8c9e10bb8`. This follow-up changes only the
Ground GUI import route, its post-build linker selection and isolated tests.
Backend source files remain owned by the independent USB repair thread.

Ground now explicitly passes `target="ground"` to the existing import service.
Flight keeps its original default. Real importer tests verify a complete tiny
project is accepted and IOC-only directory/file inputs are rejected without
changing the GUI model. These tiny fixtures are parser tests, not MCU evidence.

The first actual ARM flow exposed a GUI adaptation error: after successful
compile/link, the audit looked for the preset MCU linker in the target root.
Imported Ground instead owns its linker under `HardwareGenerated/STM32CubeMX`.
The GUI now reads the selected linker from `Generated/ground_source_graph.json`
for imported Ground, validates a portable relative path and resolves it within
the Ground target. Missing/malformed/escaping paths fail; no fallback is added
for imported Ground. Preset Ground and Flight retain their existing path.

## Actual GUI/ARM flow

The private script runs real Qt worker/callbacks offscreen, replacing only the
file chooser and message presentation. It uses the existing official F103 USB
CubeMX input, cache and disposable generated target under
`C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation`. The user's live
window, FINAL project and bench project were not touched. No new vendor snapshot
was created in the final flow; before/after cache inventories match. No cleanup,
new worktree, serial/probe access, flashing or push occurred.

Complete-directory import → expected IOC-only rejection → Ground generation →
actual incremental ARM compilation/link → actual ELF/MAP/linker audit succeeds.
Regeneration preserves identical content; the script touches only the generated
`Generated/Src/pc_byte_stream.c` timestamp and verifies its content hash remains
unchanged to request a fresh incremental compilation. Native MinGW make 4.4.1
and Arm GNU GCC 14.3.1 execute 1 compile, 1 link, 1 BIN and 1 SIZE unit. GUI
events show progress while the worker is active, then 100% after audit success.
The unchanged ELF/BIN hashes match the backend's recorded candidate:

- ELF: `e7dd36cb4f1685955c01c4464280df7ad79392ee206dac6c8fc5e38ea3d50cbd`
- BIN: `346506ee1843161665ab60815f67b3fde5c916ca93e69372439f288c402abdb0`

This records a new executed incremental compile and audit, **not a fresh full
firmware build or a substituted full-suite pass**. The backend's original
68 passed / 1 deselected scope and three complete target builds remain recorded
in `apps/SCG/docs/GROUND_CUBEMX_USB_20261009.md` with their original evidence.

The first private-script attempt failed before import because its settings path
was outside the service policy; it was moved into a private subdirectory of
that validation workspace. The next attempt compiled/linked but exposed the
linker audit error above. After the GUI fix a no-work build/audit succeeded but
the script's explicit compile-count expectation failed; the timestamp trigger
then exercised actual compilation. A final repeat corrected only the evidence
cache inventory path. All logs are retained separately.

## Remaining blockers

The post-merge selected regression run executed **63 passed / 1 failed**, exit 1,
187.02 seconds. The failure reproduces the backend's known pre-existing physical
identity collision between `sd_sdio_fatfs` and `sd_sdio_fatfs_f1`. It is not fixed
here and is not silently waived. A separately recorded final scoped run excludes
exactly that case and adds the four selected-linker/path-guard cases; its result
is **67 passed / 1 deselected**, exit 0, 192.74 seconds, recorded as
`regressions2.log`. No combined full-suite green claim is made.

Final command (from `apps/SCG`, with `QT_QPA_PLATFORM=offscreen` and
`PYTHONDONTWRITEBYTECODE=1`):

```text
../FLP/.venv/Scripts/python.exe -u -B ../../.work/gui012_20261008/run_pytest.py tests/test_ground_gui_cubemx_import.py tests/test_ground_gui_acceptance_20261009.py tests/test_target_compile_progress.py tests/test_task_progress_busy.py tests/test_build_progress.py tests/test_ground_cubemx_base.py tests/test_ground_usb_cdc_ring.py tests/test_round2_targets.py tests/test_custom_hardware_architecture.py -q --basetemp=.work/ug9b --tb=short -k "not test_one_bmi088_plugin_resolves_mixed_interfaces_without_duplicate_sources"
```

Actual GUI/ARM command (repository root, same environment):

```text
apps/FLP/.venv/Scripts/python.exe -u -B .work/GroundGuiIntegration_20261009/gui_arm_flow.py
```

The parent supplied an independent Astra review of `d1eb4bf`: **2 P1 + 4 P2**.
P1 findings concern unreachable Init/DeInit reset hooks and reset/main-loop races
that can forward old commands. P2 findings concern compiled IRQ ownership,
external dependency closure, extra snapshot headers and actual HSE/MCU macros.
These require backend repair, regenerated normal/fault evidence and re-review.
USB remains a candidate; do not recommend flashing or claim final USB acceptance.
Critical-contract, full stack/timing and hardware qualification remain NOT PROVEN.

Small evidence, the reproducible private script, exact source hashes and complete
logs are retained in `docs/evidence/scg_ground_gui_integration_20261009`.
