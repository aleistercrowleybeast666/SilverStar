# Navigation performance batch (local, no hardware)

Owner: `navigation_performance`; baseline: `57b78fbb56d64eb09a76c8b7e961aa4027a6eb70`.
No commit, branch change, publication, hardware access or cleanup performed.
The baseline copies and SHA-256 values are in `inventory.json`.

## Product changes

- INS `InsMechanization_CorrectionsCompute` reuses this call's two vector sums
  and rotation cross product. The standalone sculling API is unchanged. There
  is no cache across input, bias, attitude or lifecycle changes.
- ESKF `Eskf_ResetCongruence` specializes only the reset Jacobian
  `diag(I6, Jtheta, I6)`. P remains a full 15x15 matrix, including every cross
  term. Original ascending inner-product order and initial +0 are retained.
  Nonfinite intermediate results fall back to the original dense operation,
  so omitted structural zeros cannot conceal its established numeric failure.
- KF6 source, ESKF transition/noise kernels, all headers, parameters, failure
  enums, gates and product tests were not modified by this subtask.

## Differential evidence

`apps/SCG/tests/test_navigation_perf_equivalence.py` compiles the pinned baseline
and current owning C with the same compiler/headers/fixed numeric configuration
and links them under separate names. No golden fixture is rewritten. Test-only
private reset entry points do not enter firmware.

1. Before product edits: `baseline_test01.log`, 12 passed (O0 and O2). One
   pytest configuration warning arose from disabling its cache plugin; it is
   preserved. There was no pre-existing functional failure claimed by this
   performance batch.
2. First product change: `post_test01.log`, 12 passed.
3. Expanded signed-zero/subnormal/default-contraction coverage:
   `post_test02.log`, 18 passed.
4. Expanded full-call benchmark fixture: `post_test03.log`, 18 passed, 36.28 s.
5. Final suite: `post_test04.log`, **21 passed**, 60.92 s, no skips/failures.
   The additional case compiles baseline and current INS with
   `SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT=1` and runs another 100,000 INS
   calls per compiler configuration. Regular cases cover two-sample INS.
   Configurations: O0/O2 with contraction disabled; O2 with compiler-default
   contraction; all prohibit fast-math. All executed cases passed, no skips.

Each configuration compares 100,000 consecutive ESKF predicts plus 25,000
updates covering all five measurement groups; 100,000 INS calls; 100,000 KF6
predict/update steps; 4,000 dense SPD reset cases spanning scales; 128 signed
zero/subnormal cases; 54 public API failures and 675 nonfinite/large-matrix
private-kernel cases. Entire state/P and outcome diagnostics are compared byte
for byte for finite public outputs. Private NaNs are compared by classification
(NaN payload is not asserted as an API contract). Public fault state is checked
against its pre-call snapshot and error returns/outcomes must agree. This is
recorded differential evidence, not a proof for every possible float/compiler.

Full commands, stdout/stderr, exits, compiler versions and source/header/fixture
hashes are under each test run directory. Final source/header/test copies
are in `final_source_inputs/` (26 files) and `final_source_inputs_manifest.json`.
Every copy was verified against its current source hash. `final_checks.json`
records final Python F-rule lint and scoped `git diff --check`, both exit 0;
Git's LF-to-CRLF informational warning is retained.

## Host timing (not MCU timing)

Five alternating-order samples with the same inputs are retained in
`post_test03/*/run_benchmark.json` and summarized without dropping outliers in
`host_benchmark_summary.json`.

| Host GCC 16.1.0 mode | Full ESKF update, 10k calls median before/after | Full INS update, 1M calls median before/after |
|---|---:|---:|
| O0, contraction off | 0.283 / 0.198 s | 0.333 / 0.327 s |
| O2, contraction off | 0.048 / 0.037 s | 0.102 / 0.101 s |
| O2, default contraction | 0.064 / 0.044 s | 0.113 / 0.115 s |


The final suite repeated these workloads; all five samples are retained in
`post_test04/*/run_benchmark.json` and `host_benchmark_post04_summary.json`:

| Final-suite Host GCC mode | ESKF 10k median before/after | INS 1M median before/after |
|---|---:|---:|
| O0, contraction off | 0.525 / 0.355 s | 0.538 / 0.465 s |
| O2, contraction off | 0.079 / 0.058 s | 0.211 / 0.184 s |
| O2, default contraction | 0.062 / 0.047 s | 0.124 / 0.127 s |

Concurrent system load was not controlled. The large between-run variation and
all slower samples are retained. These numbers must not be selected selectively
or treated as MCU/WCET evidence. The reset-only number below is from post03.

ESKF reset-only O2 sample: 0.178 / 0.063 s per 100k calls. Full INS changes are
within Host timing noise, including a small regression in one mode; no measured
INS speedup is claimed. These are kernel/update workloads, not total estimator,
MCU runtime, WCET or flight performance.

## Standalone ARM objects and analyzer

`arm01` records actual Cortex-M4 hard-float GCC 14.3.1 compilation and real
`-fanalyzer` object generation for all three owning sources, with the emitted
first-party strict warning set. Every command exited 0. `arm01` total sizes
include differing absolute `__FILE__` strings and must not be used as code deltas.

`arm02` repeats before/after object builds with both source paths mapped to the
same basename, resolving that confound. Section counts are in `summary.json`:

| Code + read-only data bytes | Baseline | Current | Difference |
|---|---:|---:|---:|
| INS | 3752 | 3920 | +168 |
| ESKF15 | 7574 | 7946 | +372 |
| KF6 (unchanged) | 11844 | 11844 | 0 |

Individual compiler frame reports: `InsInertial_Update` 248 to 280 bytes, while
its old call to the 112-byte standalone sculling function is removed; ESKF
Update 240 to 248 bytes, Predict 336 to 336. These local frames do not establish
full task, library, dynamic-frame, MSP or interrupt stack bounds.

## Fresh generated project evidence

Requested by parent after the focused evidence above. `fresh_validation.py`
loads only the prior fixed project configurations and generates new owning
payloads; it does not copy old built objects or an entire SDK. KF6 uses legacy
memory layout; ESKF15 uses auto layout. The fresh generated payload hashes
match the owning files (`generated_payload_identity.json`). Full pre-build
source/configuration snapshots are `*_generated_snapshot.json`.

Both fresh runs completed. Complete streams are in `*_full_run.log`, commands,
UTC and exits in per-action JSON/logs, and summaries in `kf6_summary.json` and
`eskf15_summary.json`. Both wrappers exited 1 because `stack-report` failed.
This is not a full-green gate result.

| Exact emitted action | KF6 legacy | ESKF15 auto |
|---|---:|---:|
| Release ARM compile/link and HEX/BIN | 0 | 0 |
| architecture-check/source graph | 0 | 0 |
| power10-check | 0 | 0 |
| static-analysis: analyzer compilation and link | 0 | 0 |
| host-tests | 0 | 0 |
| artifact-check | 0 | 0 |
| stack-report | **2 (FAIL)** | **2 (FAIL)** |
| memory-report (alias of artifact-check) | 0 | 0 |

Each actual static-analysis build compiled 110 first-party analyzer objects and
48 dependency objects, then linked and produced HEX/BIN. No syntax-only
substitution was used. Toolchains: Host GCC 16.1.0, ARM GNU 14.3 rel1 (GCC 14.3.1),
repository Python 3.14. Logs retain versions and exact flags. Emitted Power10,
architecture, artifact and stack checkers are unchanged relative to the prior
projects (`emitted_gate_identity.json`).

| Host runner result | KF6 | ESKF15 |
|---|---:|---:|
| Executables | 80 | 78 |
| Checks | 4,446,532 | 4,408,184 |
| Failures | 0 | 0 |
| Compile-pass cases | 11 | 11 |
| Expected compile-failure cases | 18 | 18 |
| Runner-level not-applicable cases | 8 | 9 |

`*_not_applicable_details.json` retains distinct raw messages and occurrence
counts, including repeated inline unsupported-stream/storage-profile cases
beyond the runner-level count. Complete reasons and expected negative compile
diagnostics remain in `*_host_tests.log`. These synthetic Host fixtures do not
validate hardware.

Power10 reports 6,447 checks / 113 first-party C files / 2,813 functions /
847 recommendations for KF6 and 6,301 / 113 / 2,740 / 827 for ESKF15. Both
explicitly report **critical-contract review NOT PROVEN**, manual acceptance
pending. Exit 0 does not supersede this status.

Linked Release section/file sizes, bytes:

| Profile | text | data | bss | BIN file |
|---|---:|---:|---:|---:|
| KF6 | 341,804 | 1,140 | 159,928 | 342,956 |
| ESKF15 | 327,756 | 1,140 | 166,632 | 328,908 |

ESKF15 auto layout reports RAM occupied/spare 117,568/13,504 bytes (yellow),
CCM occupied/spare 50,208/15,328 (green). These spare bytes do not prove stack
margin. Both artifact checks find no heap symbols and diagnostics are bound.
Release and StaticAnalysis ELF/MAP/BIN/HEX/SSDIAG/SU hashes are in
`*_final_artifacts.json`; no old build objects/binaries were reused.

Release artifact directories:

- `generated_kf601/build/FCCG/SilverStar_F407/Release/`
- `generated_eskf1501/build/FCCG/SilverStar_F407/Release/auto/`

### Stack failure and diagnostic limits

Both exact emitted `stack-report` commands fail in `BindingHeader_Verify`:

```
ValueError: Changed or missing reviewed callback compilation input:
Generated/Inc/project_algorithm_parameters.h
```

Prior NIS and fresh navperf headers are byte-identical within each profile:

- KF6 SHA-256: `2bbc37593fe83cfca827f212028169c7faee1bebe8cd8aec016ba96ffb0f54bc`
- ESKF15 SHA-256: `2bef83bce27abfbd53ac91e308e378994c2c6141dd09b95a884f6ed1828db68c`

The emitted stack checker is also unchanged. Its unchanged `BindingHeader_Verify`
was invoked read-only and rejects all four prior/fresh inputs identically.
`stack_preexisting_input_failure.json` records hashes, reviewed versions and
errors. This establishes an existing reviewed-input mismatch, not one introduced
by these performance edits. This diagnosis is **not a full prior-project stack
run**. No allowlist, checker or threshold was changed to bypass the failure.

Both fresh full reports stopped at this error; later checks did not complete.
Task/library/callback/dynamic-frame/main/MSP/ISR bounds remain unproven. Review
the exact header and provenance before any separately authorized binding repair
and rerun. This report does not claim it is the only remaining stack issue.

### Retained evidence and archival scope

`archive_inventory.json` enumerates every archived small file with size and
SHA-256, purpose/owner and cleanup authorization false. The evidence ZIP contains
source snapshots, pinned baseline sources, fixed configuration, scripts, scoped
patch, logs, JSON and individual SU files. It excludes entire generated project
trees, SDK/toolchain/runtime copies, objects and executable/firmware binaries.
Actual generated artifacts remain at the local paths above and their hashes
remain archived. `archive_receipt.json` records the ZIP hash and size.

## Limits and remaining work

Critical-contract review remains NOT PROVEN. The text checker is not full
Power-of-Ten compliance, NASA certification, whole-program stack/recursion or
hardware qualification. No sensor, serial, probe, flash, reset, target-memory
write or actuator operation was performed. F²/noise/KF6 Joseph optimizations
remain outside this batch. Parent owns final integration and local commit.
No generated outputs or earlier `.work/` contents have been removed.
