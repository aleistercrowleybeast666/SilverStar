# Recovery source through configuration-only saves

Restoring a deleted run removed its tombstone and the only reference to its
historical saved bundle. A subsequent configuration-only save cleared the active
result_artifact as intended. Removing that in-memory run again then recorded
backup=None even though its original verified saved bundle still existed.
This candidate preserves that source without making a configuration-only project
carry or automatically load numerical payloads.

The optional v3 recovery_sources dictionary maps an active result_id to an
algorithm name, effective configuration and historical artifact recovery candidate.
It has the same bounded, strict reference structure as removal history. IDs are
reserved by the existing monotonic state; source/deletion maps must not overlap,
and algorithm/mode namespace, configuration schema, path and hash fields are
validated. Explicit restore transfers the candidate into this map; re-removal
transfers it back into removed_results, preserving the exact run and parameters.
Fresh data saves and strict completed-result reads associate their known members
with the actual verified bundle. Restore rejects a different configuration under
the same run ID before altering the store. Explicit backup reads continue through
the existing full artifact/input/engine/effective-configuration validation and
never replay or substitute another result.

Configuration-only save persists these small reference/configuration records,
keeps result_artifact/parse_artifact null, writes no numerical sidecar, and leaves
ProjectResults_Load empty on ordinary reopen. No candidate arrays are read while
saving metadata. Save As rebases local sources into explicit origin dependencies;
data Save As uses existing verified copying and deduplicates shared candidates.
Candidates superseded by a fresh saved run are not unnecessarily copied. Source
metadata is published only with the existing atomic project replacement; failed
or cancelled writes leave committed paths/references unchanged.

saved_result_ids is an unpersisted runtime membership record, populated only by
successful numerical save or strict result load. Project JSON cannot set it.
The Replay details and existing run-ID tooltip distinguish current saved numerical
data, current memory with a historical recovery candidate, and memory with no
known candidate. Candidates still require explicit verification; they do not prove
present file integrity. Saving updates only this small label/tooltip and does not
reiterate large diagnostics. Dataset switches clear the status. No new page,
export source, numerical fallback or automatic candidate restore was added.
Config-only ordinary reopen retains metadata without creating active numerical
rows or adding a new active-run recovery action; the existing explicit deleted-run
recovery action remains the scope of this fix.

Inventory also labels local historical recovery generations, without changing the
fail-closed physical removal policy. No ownership registry, disk reclamation,
artifact eviction, unrelated project scan or user-file operation was added.

The provenance fixtures use one exact synthetic decoder/log and one 21-sample
Pure INS What-if calculation, reused across their state cases. The separately
selected existing old-v3 fixture adds two tiny Pure INS parameter runs.
The original same-path and
Save As cases failed before the fix with backup=None (2 failed, 30.29 seconds,
exit 1); the same assertions passed after it (2 passed, 29.32 seconds, exit 0).
The first expanded small set reported 19 passes and one wrong test error-code
expectation: corrupt manifest hashes correctly raised the existing
artifact_manifest_corrupt, rather than a code containing "hash". Only that test
expectation was corrected; the verifier was not changed. Its full failure log is
retained. The b0dbe3d checkpoint small set passed together: 20 passed,
53.47 seconds, exit 0.
It covers exact typed result fingerprints/run IDs/parameters/input/engine,
metadata-only reopen/no artifact read, local/external Save As, unchanged old file
hashes, wrong hash/input/engine/parameters, metadata identity/path/state admission,
same-ID parameter conflict, cancellation/disk failure, untrusted serialized
membership, Chinese/English with both themes, context switch, commit status
publication, existing i18n consistency and old-v3 index reservation. The old-v3
fixture explicitly omits the new optional field, which did not exist historically;
its original reservation expectations are unchanged.

Final review found that separately valid old sources and newly saved members could
exceed the source-table bound after merging. The pending merged/rebased document
now passes the same RunHistory_Validate before any project publication; the
production 4096-source limit and all item rules are unchanged. A three-source
fixture with a reduced test admission cap reproduced publication without refusal
before this guard (1 failed, 17 deselected, 31.36 seconds, exit 1). After it, that
same refusal/unchanged committed-reference test and the two original lifecycle
cases passed together (3 passed, 15 deselected, 52.45 seconds, exit 0). These final
three checks do not turn the earlier 20-case checkpoint into an unexecuted final
21-case/full-suite pass.

These host test durations are not performance, hardware or full-suite acceptance.
The worker, artifact/record/audit codecs, parse identity and algorithm source are
unchanged. The original four save-lifecycle cases and large experiments were not
rerun. Parent-reported independent worker/endian/purge acceptance stays attached
to their original exact revisions. Historical GC common cause, complete real
large-result GUI restore, and safe physical artifact reclamation remain outside
the proof of this delta. No stable merge/push or live-window shutdown was performed.
