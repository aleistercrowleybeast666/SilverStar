# Navigation default-off review entry — 2026-10-16

本次可检查：主动恢复保持禁用时，GNSS 原子快照、内部损坏撤销就绪状态、
模式 0/1/2 的生成、ARM 编译、分析和受限栈门禁，以及下列 CPU 回放证据。
尚未完成：主动恢复的后端启用、动作日志和 1/5/30/120 秒完整矩阵。
未上板，不代表整仓或飞行验收通过；v0.1.2 冻结发布未改变。

This is a local 0.1.3 development checkpoint. Stable v0.1.2, its tag and release
payloads are unchanged. No hardware, serial, DAP, flashing, actuator, push or
release operation was performed.

**Active GNSS reacquisition is unfinished and blocked in generation.** Its kernel,
qualifier, configuration codec and replay/horizon companions are preparatory
implementation. Backend activation, receipt/action log records and the complete
1/5/30/120-second outage matrix are not delivered. No approved flight policy or
recovery effectiveness is claimed.

## Reviewable behavior

GNSS source, sample and native metadata now form one coherent receipt. Selector
handoff publishes identity and freshness barrier together. Invalid owned selector
state returns `BAD_STATE` without publishing a successful snapshot. The ESKF
backend latches this fault and withdraws readiness in modes 0, 1 and 2, including
missions without a GNSS origin. Normal missing source/origin and bad external
packets retain their ordinary paths; a later fix cannot establish a moving
mission origin.

ESKF component 0.4.0 declares 29 explicit recovery parameters and an exact
104-byte actual binary32 configuration identity. Defaults keep recovery off.
Project validation and rendering reject activation even if logging is disabled.
FLP admits the complete disabled identity and rejects active or inconsistent
metadata. Historical packages retain their original missing fields; no recovery
policy is backfilled into old Recorded data or offline defaults.

## Actual validation scope

Final task-owned firmware instances are `eskf15_{0,1,2}_default03` and
`kf6_{0,1,2}_default01` under `.work/dev013_navclosure02`. Each was generated as a
new current-source instance from read-only earlier configuration. Existing user
project payloads were not regenerated or overwritten.

| Final configuration | ARM compile/link | Real GCC analyzer compile/link | Power10 text gate | Architecture | Linked artifact | Emitted v20 task stack |
| --- | --- | --- | --- | --- | --- | --- |
| ESKF 0 | PASS | PASS | PASS | PASS | PASS | PASS |
| ESKF 1 | PASS | PASS, fresh retry below | PASS | PASS | PASS | PASS |
| ESKF 2 | PASS | PASS | PASS | PASS | PASS | PASS |
| KF 0 | PASS | PASS | PASS | PASS | PASS | PASS |
| KF 1 | PASS | PASS | PASS | PASS | PASS | PASS |
| KF 2 | PASS | PASS | PASS | PASS | PASS | PASS |

These are separate executed actions on the recorded source configurations. The
manifest preserves each command, complete output, exit code and hash; it does not
invent an unexecuted single full-suite command. Power10 is SilverStar's
F Prime-inspired adaptation. Its text PASS explicitly leaves critical-contract
review **NOT PROVEN**. No assertion threshold, stack budget, callback rule or
source-coverage exception was weakened.

The initial mode-1 analyzer link correctly rejected a Host test fixture staged
after generation. After that complete Host run, the exact recorded fixture was
restored, its revised copy was retained, and the emitted `static-analysis` target
was fully recompiled and linked in a new `StaticAnalysisFresh02` directory.
Production C was unchanged. Both the original failure and full fresh retry are
retained. This is not a syntax-only analyzer check.

Additional independent results:

- 458 kernel, replay, horizon, qualifier and receipt tests passed, with O0/O2
  compilation and strict warnings in their recorded scopes.
- The owned-selector fault failed before the fix in O0/O2 and passed afterward.
  The no-origin fault failed in modes 0/1 before the correction (four failures,
  mode 2's two existing checks passed); all six passed after correction with
  unchanged expectations.
- Final native mode-2 backend regression: 56 passed. Final mode-0 exact-pair and
  numerical regression: 22 passed. Final mode-2 production
  `LogOpenCoordinator` exact Descriptor/package opening and full covariance
  comparison: two passed. These use new CPU-produced logs, not onboard logs.
- One complete Host invocation passed: 80 executables, 4,402,848 checks, zero
  failures, 11 positive compile cases, 18 expected compile rejections and 10
  not-applicable cases. Its explicit owning Host-fixture revision corrects the
  synthetic barometer noise policy and checks the existing 42-record catalog,
  including both horizon identities/sizes. Earlier full-run failures are kept.
- The v20 registration's 49 tests passed, including source/header/graph tampering,
  mixtures of individually known inputs, an active-header rejection and unchanged
  historical v19 checks. All other checker AST policy nodes remain identical.
- Trusted packaged contract and disabled-identity tests passed. A broader FLP
  run retained an existing `export_source_unavailable:recorded` failure, reproduced
  with HEAD production modules. This checkpoint is **not** a full FLP-suite PASS.

CPU fixtures include explicit 5 ms stress intervals. They do not establish the
real device sampling schedule, interrupt latency or MCU timing. Mode-1 historical
replay compatibility is separate from the not-delivered active recovery matrix.

## Stack scope

The actual v20 report registers 21 reviewed input paths, eight dependency graphs
and 960 complete source/compiler-input tuples. Changed ARM objects introduce no
indirect call sites. Some shared recovery helpers remain linked in modes 1/2;
their conservative linked paths remain in the analysis. The default backend has
no active recovery receiver/companion lifecycle.

| Configuration | Estimator worst known / configured bytes | Estimator margin | INS margin |
| --- | --- | --- | --- |
| ESKF 0 | 2128 / 4096 | 1968 | 808 |
| ESKF 1 | 2768 / 4096 | 1328 | 808 |
| ESKF 2 | 2552 / 4096 | 1544 | 808 |
| KF 0 | 3236 / 4096 | 860 | 832 |
| KF 1 | 3356 / 4096 | 740 | 832 |
| KF 2 | 2772 / 4096 | 1324 | 832 |

These recorded task-path estimates are not a complete stack proof. Main/MSP,
relevant ISR nesting, physical high-water marks, WCET, navigation accuracy,
manual critical contracts and hardware/flight qualification remain **NOT PROVEN**.
The [exact input review](NAVIGATION_RECEIPT_DEFAULT_OFF_STACK_REVIEW_20261016.md)
explains the limited gate revision.

## Evidence and reproduction

The machine-readable entry is
[`docs/evidence/navigation_receipt_default_off_20261016/validation.json`](../../evidence/navigation_receipt_default_off_20261016/validation.json).
It indexes the auditable source snapshot, final outputs and retained failures.
Its archives and manifest contain SHA256 hashes. The private task directory also
retains all execution receipts and superseded/partial projects; none is silently
promoted into a final result.

From the repository root, use the saved final models and the exact commands in
that manifest. For an individual task-owned firmware instance, the standard
targets are `power10-check`, `architecture-check`, `all`, `static-analysis`,
`artifact-check` and `stack-report`, with the recorded target/profile/layout.
The v20 gate-only payload emission and its unchanged Power10 bytes are recorded
in `gate_emission_v20.json`. Changing a model, header or compiler configuration
requires new evidence; these hashes do not approve another project.

The separate USB and GSHC tasks are excluded from this navigation checkpoint.
USB Power10 failures remain failures; neither their tests nor this matrix imply
combined repository, all-chip or onboard acceptance.
