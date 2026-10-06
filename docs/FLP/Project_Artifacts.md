# Project numerical artifacts

The optional v3 `result_artifact` reference preserves every completed run, including
distinct runs of one algorithm. It points to a bounded, data-only JSON manifest in
`PROJECT.ssflp.artifacts/generation-UUID/manifest.json`. Its SHA-256 covers the manifest;
each uncompressed NPY array has its own hash, exact dtype, shape and byte count. Objects,
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
project whose historical results must be retained. Compression is currently disabled;
reported on-disk bytes must include audit JSON and NPY headers, not just array nbytes.
