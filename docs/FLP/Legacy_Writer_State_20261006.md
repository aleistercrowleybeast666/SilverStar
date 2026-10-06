# Strict old-writer result load publication

An actual v3 project produced by the exact 1b0b165 Project_Save writer, with
replay_configurations={} and no later optional identity/history/source fields,
passed strict numerical result loading. Its store reserved pure_ins:what_if #1,
but the document still had empty limits while receiving a source for #1.
Subsequent configuration-only and data saves correctly rejected that inconsistent
document. The validator was not the defect and has not been weakened.

After all numerical members and declared identity state pass, ProjectResults_Load
now obtains the store's merged reservations, merges verified recovery sources into
temporary metadata, and admits that complete pending document using the unchanged
RunHistory_Validate. Only then does it publish run_identity_state, recovery_sources
and runtime saved_result_ids. Saved membership is also constructed before publication.
Failed member, merged-metadata, or membership-allocation checks publish none
of those fields. Existing declared limits/deletion checks remain authoritative;
indices are adopted only from the strictly validated store.

The regression file executes the full original project.py module from Git
commit 1b0b1650d5270a5c904ca31b09ab5b54e0d2b73e, using its original ProjectDocument
and Project_Save. No project metadata is removed by the test to fabricate an old
writer. Runtime artifact/parser/engine dependencies are the current, unchanged
implementation; this is exact old-writer evidence, not a whole old-branch run.
One 21-sample synthetic Pure INS result is reused. The tests verify old payload
absence of the optional fields, exact typed numerical fingerprints and run ID,
configuration-only/data Save As, preserved notes and old project bytes, a late
invalid member, failed merged-source admission, and a host-injected membership
allocation exception without partial publication. The latter is not a measured
out-of-memory or disk-full result.

Before: 3 failed, 1 passed, 36.99 seconds, exit 1. Both saves reported
project_run_identity_invalid and the simulated merged admission was not invoked.
After the initial publication change (0acbb571): the identical four tests passed
together, 44.44 seconds, exit 0. After preparing saved membership before publication,
the five-case final file passed together, 50.92 seconds, exit 0. Complete logs,
exact original-writer bytes/hash, new source
hashes, commands and tool versions accompany the independent small delta.
No large replay, GUI launch, original four lifecycle rerun, full-suite claim,
validator relaxation, stable merge or user-project modification was performed.
