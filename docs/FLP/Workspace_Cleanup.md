# Safe workspace cleanup

From the monorepo root (the default scope remains `apps/FLP`):

```powershell
python apps/FLP/tools/clean_workspace.py --dry-run
python apps/FLP/tools/clean_workspace.py --plan .work/flp-cleanup.json --owner "completed FLP test caches"
# Review every candidate and retain any uncertain or final delivery files.
python apps/FLP/tools/clean_workspace.py --apply .work/flp-cleanup.json
```

Without arguments the tool performs a dry run. It never invokes `git clean`. It validates the
actual Git root independently of the application scope, stays inside that scope, rejects
symlink/junction/reparse ancestors, and rechecks the Git index and path before removal.
The saved plan records owner, type, size, content SHA-256 and filesystem identity. Execution
requires that reviewed plan; it does not silently create a different list. A changed target
refuses the plan before removal; an already absent target makes repeat execution a no-op.
It unlinks approved individual files and
uses only nonrecursive `rmdir` for empty directories. Busy or changed targets are reported refused.
Run it after local test/export/package jobs have finished.

The same command works from a subdirectory with the appropriate script path; it does not change
scope to the caller's current directory. An explicit `--scope apps/FLP/tests` can narrow the
preview. A scope may not escape the repository or traverse a link. Put a `.cleanup-active` marker
in a task directory before a long running job and remove that marker when the job has fully
stopped; any candidate under an active marker is refused, including a previously reviewed plan.
Do not apply a plan while unrelated build or test jobs still own its scope. The preview lists
retained paths and protection reasons; an eligible filename alone is not proof of ownership.

Candidates are Python bytecode, documented cache trees (`__pycache__`, `.pytest_cache`,
`.ruff_cache`, `.mypy_cache`), and known generated suffixes beneath root build/dist, `.acceptance`,
`.codex_pytest_*`, and `.codex_container_stage_*`. Under `tests`, the same suffix allowlist applies
only to named `.tmp_*`, `.pytest*`, and `.integrity-*` workspaces and nested `*_temp` / `*_cache`
directories. Arbitrary root PNG/JSON/CSV files and unknown suffixes are not candidates. The virtual
environment, Git internals, docs, fixtures, golden directories, tracked files, and `.BIN`, `.sslog`,
`.ssdecoder`, `.ssflp`, `.ssproject`, `.tdproj`, `.tdrun`, `.bak`, `.tdmotor.json`, `.sstuning.json`,
signing-key files and `.zip` inputs are preserved. Small evidence summaries,
manifests, final logs, GUI screenshots, and finished acceptance GIFs are retained. A directory
containing any protected file remains in place.

Some historical `.codex_pytest_*` and `.codex_container_stage_*` outputs are already tracked.
New ignore rules prevent adding future leftovers; they do not remove existing tracked files.
This task does not rewrite history or silently untrack/delete those assets. No raw user log,
decoder, project, or source archive is removed.

New acceptance runs use `.acceptance/<run-name>` or pytest `tmp_path`; long-term fixtures belong
in `tests/fixtures` and must be reviewed and explicitly added. Named test basetemp workspaces are
ignored by Git and eligible for bounded cleanup. See
[Display_DataQuality.md](Display_DataQuality.md) for the display/quality contract.

## Explicit historical test retirement

At the user's 2026-09-12 request, 46 obsolete `.codex_pytest_*` / `.codex_container_stage_*`
directories were audited as generated, unreferenced test runs and retired, including 2,397
mistakenly tracked synthetic files (86,042,656 bytes). Git records these deletions for review.
`WorkspaceClean_RetireTests(root, exact_names)` is an explicit retirement API: it checks the real
repository root, permits only those historical run-name prefixes, preflights every descendant,
refuses links/junctions and removes individual files followed by empty directories. It does not
change the ordinary dry-run/apply policy or permit fixture/source directory deletion.
