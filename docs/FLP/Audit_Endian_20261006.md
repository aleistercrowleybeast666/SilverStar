# Audit array byte-order preservation

The cloud-validated diagnostics WIP was frozen without source changes as
c8fdc2dfeaa470ed30d8485d2e50de247fae2438. Its original package SHA256 is
11b1bd4c1872e0529c7b5fddb07cbbc505f214feb9bfa8a3f8c3e26388d58521.
This subsequent delta changes only the audit-column concatenation to require
the planned dtype and casting="no". NumPy's default concatenation had converted
big-endian columns to native order while the plan retained the original dtype,
causing artifact_audit_matrix_invalid during transaction read-back verification.
No generic budgets, artifact verification, record codec, parse identity, or
algorithm engine identity were relaxed or revised by this fix.

Four dtype cases (>f8, >f4, >i4, >u2) failed before this one-line behavior fix
(4 failed, 13 deselected, 1.71 seconds, exit 1). The same cases now preserve dtype,
shape, raw bytes and read-only arrays over 4113 rows in two actual blocks
(4096+17). Floating cases include signed zero, infinity and changing NaN payload
bits; integer cases include signed/unsigned bounds. The whole audit test file
passed once after this fix: 17 passed in 5.40 seconds, exit 0. Original cumulative
object/memory/block admission failures and hash/path/size/version checks remain
in that file. These are bounded synthetic storage tests, not real replay evidence.

Parent-reported diagnostics-only cloud evidence applies to the frozen c8fd WIP:
48 top-level fields with exact typed fingerprints, order and IEEE bits; 31 blocks,
119 files, 669804 charged objects and 70.2 MB estimated live allocation; save
4.37 seconds/read 1.89 seconds/peak RSS 236 MiB, 2.69 MB compressed, zero parse or
replay. It is not a full real AlgorithmResult backup or a Windows measurement.
The audit row dictionary provides the tested read interface, but low-level dict
base-method/C API consumers have not all been validated. Full large-result GUI
consumer compatibility remains NOT PROVEN.
