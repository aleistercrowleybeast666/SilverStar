# Fail-closed artifact reclamation

An origin project can restore a deleted run and save a new generation while a
configuration-only Save As still needs the older generation for recovery. Local
inventory then labels the old generation unreferenced. The old removal command
validated contents and local references, but deleted that shared recovery candidate.
Content integrity and local non-reference do not prove exclusive ownership.

Physical removal now fails with project_cache_generation_ownership_unproven for
every locally unreferenced generation. Referenced/nonexistent generation requests
still fail protected. There is no ownership registry capable of proving exclusivity;
no directory scan, new allowlist, automatic eviction or deletion was added. Inventory
explicitly reports current_project_only scope and ownership_not_proven. The CLI help
and artifact documentation describe this refusal. Explicit clear-parse remains a
transactional reference-only operation and reports no reclaimed bytes.

A tiny synthetic Pure INS fixture reproduced the exact Save As -> origin restore
-> new save sequence before the fix. The required refusal was absent (1 failed,
16.60 seconds, exit 1). The same unchanged sequence now passes, verifies all old
generation file hashes unchanged and reloads the dependent backup with every result
field exact. Together with active-result/unknown-evidence preservation it passed
2 selected tests, 18 deselected, 24.30 seconds, exit 0. The existing unknown-file
test now expects the stronger ownership refusal before inspecting artifact contents;
its preservation and result-reload assertions were retained.

Only disposable synthetic Temp fixtures were used. No user project, shared cache,
log, decoder, evidence or other directory was cleaned. Safe physical reclamation
remains unavailable until an explicit ownership contract is implemented and reviewed.
