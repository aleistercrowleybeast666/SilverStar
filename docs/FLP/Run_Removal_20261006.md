# Logical run removal candidate, 2026-10-06

This delta is based on `1b0b1650d5270a5c904ca31b09ab5b54e0d2b73e`. It changes FLP project history
and the existing Replay page only. It does not change the numerical engines,
parser identity, artifact codec, or record blocks. It is an isolated candidate for
parent review; no main-branch integration or user-project deletion was performed.

## Identity and selection

Removal addresses one `result_id`, not an algorithm name. Each algorithm/mode
namespace retains a monotonic highest assigned run index. The optional v3
`run_identity_state` stores these limits and deleted IDs. Old v3 projects are
readable; IDs from their saved run configurations reserve indices even when arrays
were not saved. Recomputed runs never reuse a removed number. Explicit recovery
restores the original ID. It cannot substitute another run of the same algorithm.

Removing the selected primary leaves that source explicitly unavailable until the
user selects another source or restores the exact run. Removing the secondary
clears the secondary selection. These behaviors survive save/reopen. Stale Replay
detail/comparison references are cleared. Removal/restore marks the project dirty.
The existing primary-only export behavior is preserved.

## Transaction and recovery

Removal is initially logical: it removes the run from active tables, source maps
and future saved active results. It retains an undo entry in window memory, so it
does **not** free all run memory. Closing the window loses undo for unsaved runs.
The confirmation states this and states that raw logs and saved files are retained.
It does **not** claim reclaimed disk space.

`removed_results` maps deleted IDs to small configuration metadata and an optional
saved recovery candidate. A candidate may not contain a newly completed unsaved
run; explicit recovery verifies the full artifact, current numerical/input identity,
effective configuration (if saved), and exact run membership. Missing, damaged,
incompatible, or non-member candidates fail explicitly. No numerical replay,
Recorded fallback, or alternate-run substitution is attempted. Disk recovery uses
the existing background worker, not the GUI thread. Window undo is immediate.

Saving writes/validates retained numerical artifacts before atomically updating
`.ssflp`. Failure/cancellation leaves the committed project and old references
intact; in-memory removal remains dirty and undoable. Configuration-only save keeps
tombstones/identity limits and removes deleted configuration entries, so it cannot
resurrect removal. Existing notes and other run configurations are preserved.

Old generations stay in their original directory. Their bundles can contain several
runs and their numerical array files can be hard-linked across generations. Global
exclusivity is not proven. This delta neither moves nor deletes those files and
does not scan unrelated projects. A local referenced recovery generation is
labelled `deleted_run_backup` and protected by the existing manual cache command.
Unknown/shared generations are left alone by run removal.

Data-enabled Save As copies each unique verified recovery candidate once to the
new sidecar and makes the reference local; moving the whole new project/sidecar
retains recovery. Configuration-only Save As copies no numerical backup and records
an explicit origin-project dependency. Its recovery requires that old location and
sidecar to remain accessible. It is not a standalone numerical backup; the Replay
page states this limitation. Raw logs and decoder packages are never copied/deleted
by this delta. External source references use the established project path rules.

## Evidence boundaries

`tests/test_run_deletion.py` uses one tiny exact synthetic decoder/log and two short
Pure INS What-if runs with different effective gravity parameters. Tests cover exact
ID removal/undo, monotonically reserved indices, data/config-only save/reopen,
old-v3 migration, missing candidate, failed save/cancellation, Save As/move,
protected recovery generation, GUI confirmation cancellation, deleted primary,
cleared secondary, dirty state, worker guards and off-GUI-thread recovery, and
hostile history references. Numerical round-trip checks include every channel array
and diagnostics. The retained pre-fix log substitutes only the released 1b
`Result_Add` method into an isolated child test process; it is not a whole old-branch
execution. The failure is `run_index == 2`, where `3` is required.

Final commands, exact source/file hashes, dependency versions, exit codes and full
logs are in the delivery evidence package. Historical/intermediate passes do not
constitute an unexecuted full-suite pass. No hardware qualification is claimed.

Cloud acceptance of exact 1b raw 0028 dataset persistence covers 265573 records,
532 channels, 105 aliases, one parse, zero numerical replays, one save/cache-open,
and full typed fingerprints (including order and IEEE bits). That is a parent
report, not a Windows measurement or a backup of the user's unsaved runs. Large
numerical results are still **NOT PROVEN**: ordinary diagnostic dictionaries/lists
remain under the generic object/node bounds; record blocks cover only
`DecodedRecord` tuples. The parent's existing real 0028 KF6 diagnostics audit
exceeds 2 million value/container nodes even before keys. It is being tested
separately without replay. The parent subsequently confirmed exact 1b's
`Artifact_Write -> Artifact_Verify` fails with `artifact_object_limit` at object/node
count 2000001 after encoding 3803558 nodes (24.52 seconds, peak RSS 864 MiB in its
independent process; neither watchdog nor OOM). This is diagnostics-only evidence,
not a full AlgorithmResult test. This delta deliberately does not change the codec or
raise limits. No complete reloadable large AlgorithmResult was identified in the
three bounded user-project locations checked, and no long ESKF was rerun.

The expanded Windows regression command selected 21 tests, reported 19 as passed,
then terminated with `access violation` (`-1073741819`) near the existing GUI reopen
test. The complete log is retained. This is a failed combined run, not a 19-test
suite pass. Its cause is unresolved and blocks claiming complete automated
acceptance; a separate-process deletion result does not erase this failure.
The separate final deletion-file run passed all 14 cases in 161.62 seconds (exit 0).
Ruff is unavailable in the shared venv; no lint pass is claimed and the venv was
not changed to install it.
