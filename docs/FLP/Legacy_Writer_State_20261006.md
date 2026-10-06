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
and runtime saved_result_ids. Failed member or merged-metadata checks publish none
of those fields. Existing declared limits/deletion checks remain authoritative;
indices are adopted only from the strictly validated store.

The new four-case file executes the full original project.py module from Git
commit 1b0b1650d5270a5c904ca31b09ab5b54e0d2b73e, using its original ProjectDocument
and Project_Save. No project metadata is removed by the test to fabricate an old
writer. Runtime artifact/parser/engine dependencies are the current, unchanged
implementation; this is exact old-writer evidence, not a whole old-branch run.
One 21-sample synthetic Pure INS result is reused. The tests verify old payload
absence of the optional fields, exact typed numerical fingerprints and run ID,
configuration-only/data Save As, preserved notes and old project bytes, a late
invalid member, and failed merged-source admission without partial publication.

Before: 3 failed, 1 passed, 36.99 seconds, exit 1. Both saves reported
project_run_identity_invalid and the simulated merged admission was not invoked.
After the eight-line publication change: the identical four tests passed together,
44.44 seconds, exit 0. Complete logs, exact original-writer bytes/hash, new source
hashes, commands and tool versions accompany the independent small delta.
No large replay, GUI launch, original four lifecycle rerun, full-suite claim,
validator relaxation, stable merge or user-project modification was performed.
