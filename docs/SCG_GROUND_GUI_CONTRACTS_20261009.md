# Ground GUI availability and diagnostics — 2026-10-09

Base: `8b418943c987e8b12f37e08d90a58032a1e1b89e`. This independent GUI change
does not merge USB repair `b05b370` or modify backend/runtime/generator files.

## Historical contract, not a waived failure

- Approved `31541b3cf382c65b80038baf7929cc13a9e6d31e` (2026-10-03) hid the Ground
  enable control, made both targets available in the GUI and changed the existing
  test to require a disable request to retain the enabled Ground target. The
  [GUI release notes](GUI_RELEASE_NOTES_20261003.md) say Ground is internally
  enabled, while generation remains an explicit choice.
- `b26f6be340c9fb72f4efa116fc8574bf9e00d9d3` (2026-10-05) deliberately removed
  enabling from display construction to preserve stored/legacy models. The GUI
  had relied on that display side effect to undo disable requests, so its old
  enabled-state assertion subsequently failed. Restoring display mutation would
  violate the newer preservation requirement.
- `506aafba54267d6b973615e0c1eca480b2248a9c` (2026-10-05) explicitly replaced raw
  diagnostic prose with localized summaries and guidance. Its
  `test_ground_errors_are_localized_and_block_only_ground_generation` requires
  no `GROUND_` codes in that body/generation-dialog presentation. The older
  `4449ab8` test still required the polarity code in the status body, so those
  two assertions described different presentation contracts.

The implementation now handles the GUI disable request at its event boundary:
it refreshes the control without mutating the model or lifecycle. A stored/API
disabled model remains disabled; parsing, reference defaults and read-only
refresh do not enable it. Compatible GUI opening already makes an explicit
in-memory enabled copy, preserving source descriptor bytes until authorized
save/generation; release-legacy opening still retains its migration boundary.
No model/schema/default or backend disable contract is changed.

The status body keeps its localized summary. Its tooltip now includes each
stable issue code and concrete reason, alongside existing localized guidance
and unused-resource information. The older diagnostic test now checks the
authoritative polarity issue, stable tooltip code, exact localized summary and
absence of raw codes from that body. It also forbids ProjectRoot_Save during
invalid Ground generation and proves the descriptor is unchanged and no Ground
Makefile is published. This is a stronger diagnostic/blocking check, not removal
of a failed assertion without replacement.

The earlier field-blocker test's disable path predates the approved GUI change.
It now checks that the GUI request preserves availability, then explicitly
installs a stored disabled model and retains its original disabled generation
and tooltip assertions. New tests separately verify full-model/lifecycle
invariance, disabled refresh across languages, and localized polarity diagnostics.

## Test isolation and executed evidence

The shared test window fixture uses a unique short settings directory under its
real service workspace. It no longer places path_preferences outside that policy
when pytest data uses Windows Temp. Production WorkspacePolicy/PathPreferences
are unchanged. User-descriptor tests read a same-byte private copy; the source
descriptor is verified unchanged at teardown. FINAL and all existing generated
projects remain untouched.

The previous read-only matrix is retained: main `8b41894` and isolated `b05b370`
both ran the original nine tests with **7 passed / 2 failed**, exits 1, 50.06 and
56.67 seconds. The original expanded backend result remains 148 passed / 2 failed
/ 7 setup errors / 1 deselected, not a successful suite.

New/strengthened contract checks before the product fix: **4 failed / 1 passed**,
exit 1, 40.29 seconds. After the six-line product fix, the complete declared
eight-file scope runs **81 passed**, exit 0, 198.63 seconds:

```text
../FLP/.venv/Scripts/python.exe -u -B ../../.work/gui012_20261008/run_pytest.py tests/test_ground_gui_contracts.py tests/test_ground_board_recovery.py tests/test_ground_activity_configuration.py tests/test_ground_radio_editor.py tests/test_gui_20261005.py tests/test_field_blockers.py tests/test_ground_gui_acceptance_20261009.py tests/test_ground_gui_cubemx_import.py -q --basetemp=.work/gc9c --tb=short
```

Working directory: `apps/SCG`; `QT_QPA_PLATFORM=offscreen` and
`PYTHONDONTWRITEBYTECODE=1`. Python 3.14, PySide6 6.10.1, pytest 9.1.1. The existing
normal-directory/private-settings runner plugins are retained. The known disabled
cache-provider `cache_dir` configuration warning is preserved.

The exact seven previously failing setup cases separately run **7 passed**,
exit 0, 38.69 seconds with data under
`C:/Users/chdxm/AppData/Local/Temp/scg_contract_settings_20261009_a`, proving that
only test settings were relocated. A tiny standalone API probe also passes:
reference and parsed Ground remain false; TargetScope.GROUND rejects that input
with `Ground target is disabled` before creating an output directory. It writes
no firmware payload and does not count as an additional pytest suite result.

An initial pre-test shell redirection used the wrong relative evidence directory
and did not execute a successful test run. Its error is recorded separately.
All executed logs, source hashes, runner/probe scripts and the original matrix
are retained under `docs/evidence/scg_ground_gui_contracts_20261009`.
For reproduction, restore archived scripts to their recorded `.work` locations:
`run_pytest.py` under `.work/gui012_20261008`, `disabled_api_probe.py` under
`.work/GroundGuiContracts_20261009`, and the original matrix runner under
`.work/GroundGuiReviewDiagnosis_20261009`. Their repository-relative lookup is
intentional. Reproduce historical failures on their pinned source revisions,
not the newly repaired GUI; the original matrix manifest retains its file hashes.

## Limits

These are GUI/project-contract tests, not ARM compilation or hardware evidence.
No firmware payload, validator, source graph, return contract, assertion policy,
allowlist or path safety check was weakened. No user window, FINAL/bench project,
serial port or probe was controlled; no cleanup, flashing or push occurred.
The known SD physical identity collision is outside this declared scope and
remains unresolved. Do not add independent run counts into an unexecuted full
suite pass. USB acceptance remains blocked: the parent reports five findings
closed in isolated `b05b370`, with dependency-closure P2 still requiring repair
and independent review. That repair is not part of this GUI commit.
