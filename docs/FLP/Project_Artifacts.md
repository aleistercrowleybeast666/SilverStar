# Project numerical artifacts

The optional v3 `result_artifact` reference preserves every completed run, including
distinct runs of one algorithm. It points to a bounded, data-only JSON manifest in
`PROJECT.ssflp.artifacts/generation-UUID/manifest.json`. Its SHA-256 covers the manifest;
each NPY array has its own hash, exact dtype, shape and byte count. Objects,
pickle and executable imports are forbidden. JSON retains tuples, lists, nonfinite
diagnostic values, bytes and NumPy scalar types through explicit data tags. Supported
dataclass and enum types are an internal fixed allowlist. Timestamps, values, validity,
units, quantity, source, columns, metadata, effective parameters, schema/audit metadata,
provenance, warnings, fidelity, missing inputs and diagnostics all round-trip.

The numerical identity binds the immutable log SHA-256, complete exact decoder identity
and executable engine/input-contract source digest, independent of the whole Git commit
and of UI language, theme or selected display range. Algorithm version and mathematical
revision evidence remain part of each result. A historical APPROXIMATE result never
becomes EXACT. Saved run/source IDs and run indices are verified on restoration.

Writes create an unreferenced generation, flush/fsync all files and validate a complete
read-back before atomically replacing `.ssflp`. Cancellation, disk failure and incomplete
generations cannot publish a successful project reference. Raw logs/decoder packages are
never copied or changed. Save As writes verified artifacts beside the destination and
re-encodes log/decoder references. Moving the project together with its sidecar and any
relative source files preserves references; external files retain absolute references.

Old v3 files without artifact references remain readable with their notes and parameters.
They cannot contain historical arrays which were never saved. Missing, damaged or
incompatible result artifacts produce an explicit replay-required message and never
start an expensive replay automatically. Save is blocked while saved history is
unavailable, preventing accidental replacement with a partial store. The primary and
optional secondary source IDs are saved independently; export still freezes primary.

Limits: 256 MiB manifest, 512 MiB numerical data per array, 4 GiB total arrays, 4096 arrays,
20 million entries per dimension, four array dimensions, 64 structure levels and eight
million decoded structure nodes. NPY headers are checked before allocation. Hashes
detect corruption; they are not signatures against a person who can rewrite the project
and all its artifacts.

Numerical results are project data and are never automatically evicted. Incomplete and
superseded generations remain unreferenced. Manual cleanup must identify the active
manifest references and remove only explicitly selected generated generations. Preserve
logs, decoder packages, source fixtures and evidence. Do not delete the sidecar of a
project whose historical results must be retained. New generations use lossless gzip for JSON and NPY, with bounded expanded sizes and
headers checked before allocation. The reader also accepts first-stage uncompressed
JSON/NPY. References report compressed and uncompressed bytes, including audit JSON
and NPY headers. Equal array contents are deduplicated even for distinct objects;
verified identical files may be hardlinked between generations on one filesystem.


## Complete parsed dataset cache

The optional `parse_artifact` stores the entire FlightDataset, including raw/partial
records and byte payloads, header, all channels, alias object identity, semantic context,
ParserDiagnostics, DataQualitySummary and damaged spans. Frozen nested mappings remain
frozen. Its identity includes original log content SHA-256 and bytes, exact decoder and
container identity, cache schema and parser/semantic source digest. LogOpenCoordinator
still validates the package and Descriptor before admitting a cache. Missing, corrupt
or mismatched parsed cache falls back to that same strict parser. No alternative decoder
is used. Production parsing binds content identity before/after parsing; replay captures
that identity and engine identity at execution. Saving cannot relabel a result made from
an earlier log or a different engine. Restore validates effective configuration, schema,
provenance, process/quality revisions and input identity before admission.

## Save choice and responsiveness

`save_data_and_results` defaults to true for v3 and is remembered per project. The save
dialog's checked option saves the full parsed dataset plus every completed result.
Unchecked saves only references, notes, UI and run configurations; both artifact
references are null. Previously saved sidecar files are retained. Re-enabling can save
completed runs still in memory; an old closed configuration-only project has no saved
arrays to recover and needs an explicit replay. A requested unavailable replay remains
unavailable with blank navigation/filter views until the user selects another source.
Normal Save/Save As compress and validate in a cancellable background task.

## Manual space management

`sslog project-cache PROJECT.ssflp` reports each generation, its logical bytes, physical
bytes accounting for hardlinks, and whether it contains live saved results, live parsed
data or unreferenced files. `--clear-parse` drops only the parse reference atomically;
next open parses strictly. `--remove-generation generation-EXACT_ID` removes only one
verified unreferenced generation. Active saved results and all unknown/evidence files
are protected. Partial generations without a verifiable manifest require separate
manual inspection; they are not silently deleted. No logs or decoder packages are
removed. Before array writes a conservative free-space reserve is required.

Reader admission rejects symlinks/reparse points and nonregular files before hashing,
checks cancellation before any read, limits columns even for zero rows, enforces scalar
tag types and accounts for loaded arrays plus every TimeSeries copy against a live
allocation budget. Expanded gzip size, JSON structure nodes and generated column
objects have independent bounds. Tool tests use small lowered budgets, not large
allocations or an OOM experiment. These are defensive bounds, not a worst-case RSS proof.
