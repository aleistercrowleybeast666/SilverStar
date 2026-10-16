# FLP four-regression closeout — 2026-10-16

Owner: `/root`, SilverStar 0.1.3 development. This is a local test-fixture and
historical-control correction. It does not activate mode2 or change target
numerical code, source recordings, frozen releases or published artifacts.

The original fingerprint encoder and both expected SHA-256 values remain
unchanged. The pinned 45778d3 filter/replay were executed independently: every
original35 state field, full covariance, counters and entire snapshot sequence
are bitwise equal to the current normal control in revisions1 and2. The only
added state fields are the two enabled NIS gate booleans. A source-pinned shape
fixture now retains the exact historical field order for that historical hash;
all original fields remain covered. Unknown extra fields fail the test, and
disabled new gate controls have separate rejection tests. The full comparison,
old source hashes, before sources and unchanged expected hashes are archived.

The ESKF synthetic C producer used current v2 serialization but left appended
timing evidence at zero. It now records its actual successful kernel call's
source/application/evaluation epoch, declared mode0/1 and producer sequence.
Its direct-kernel observations have equal epochs; there is no fabricated delayed
execution. Tests assert all timing fields before replay. Sequential and
interleaved full-P replay retain their existing expectations and tolerances.
Original generated recordings and packages remain untouched; fresh test outputs
and their exact generated decoder packages are retained.

Executed results (one invocation per row):

| Receipt | Result | Scope |
|---|---|---|
| kf_historical_compare01 | exit0 | Both pinned old controls reproduce original hashes; all shared state/snapshots bitwise equal |
| flp_four_post01 | 40pass, no skips | Four original cases plus existing failure-publication cases and new gate-coverage checks |
| flp_regression08 | 365pass, no skips | Exact broader regression05 scope, fresh current backend traces/decoders, horizon core/wire and related timing/UI/contract tests |

The earlier six-failure regression05 and four-failure profile06 are retained with
their precise source snapshots. Their metadata/unit-context issues were separately
resolved before this run; they are not rewritten as passes. This is the recorded
targeted scope, not an unexecuted full FLP-suite pass.

Both previously started full generated Host suites were interrupted by execution
service loss. Read-only recovery confirmed no remaining runner/compiler or
generated Host test processes, but neither suite has a final receipt. Their
partial artifacts are inventoried and retained; completion/exit status remain
unknown and are not counted as passes. No duplicate suite was started.

Mode2 SCG/FLP numerical admission, active ESKF recovery, final all-mode gates and
manual critical-contract/stack/MSP/ISR/WCET/hardware acceptance remain pending.
Wireless integration is deferred. No hardware, push, tag, release or cleanup.
