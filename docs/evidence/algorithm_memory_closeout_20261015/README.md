# Navigation memory batch — 2026-10-15

Owner `/root`, 0.1.3 development. This batch changes placement/link evidence;
filter arithmetic, queue capacity and resource thresholds are unchanged.

The 2560-byte estimator input queue contains private CPU value copies only.
Its address never escapes to DMA or a device. F407 places it in the existing
startup-cleared CCM BSS; other targets retain their existing macro behavior.
KF optional history gets its own startup-covered CCM input section so a live
neighbor cannot retain unused history at O0. Automatic layout accepts a missing
private symbol only when the actual linker map proves the exact input section,
object and size were discarded. Missing, ambiguous and mismatched proof rejects.
All existing physical bounds, source ownership, alignment and clear-range checks
remain. No gate exceptions, queues or thresholds were widened.

## Executed evidence

- `memory_prefault02`: two intended real ARM regressions fail before the fix:
  unused ESKF history is rejected after GC; unused KF history remains linked.
- `memory_post02`: **31 passed**, no skips, including real ARM links and five
  missing/forged/ambiguous discard-evidence rejection cases.
- KF legacy fresh O2 ARM compile/link and artifact check pass: main SRAM
  **101260/102400** reviewed budget (previously 103820), CCM **61736/65536**.
- Current KF and ESKF all-source O0 ARM links pass. Complete nm outputs contain
  no `s_replay`, `s_replay_storage`, `s_history` or `s_body_history`.
- KF legacy actual ARM `-fanalyzer -c`: **110** first-party compilation commands,
  no compiler diagnostics, real final link. It is not syntax-only analysis.
- Emitted Power10 text gates pass for the three configurations. They retain
  critical-contract review **NOT_PROVEN** and the unchanged gate policy.
- `memory_host02`: the named estimator preparation and logger streaming cases
  plus the emitted runner's automatically executed complete storage integrity
  stage pass. This is a scoped Host run, not the full Host suite.

Commands, full logs, versions, source/configuration hashes, maps, ELFs and compiler
stack/dependency files are indexed in manifest.json and evidence.zip. The initial
62-file dirty snapshot is retained to bind the executed development sources.
The source base is the recorded commit plus those bytes and the changed files.
Each project retains its own exact generated inputs and layout-tool snapshot;
the failed map-argument attempt and later corrected snapshot are not conflated.
Generation inventories identify all linked native/vendor inputs; SDKs were reused
externally. Existing upstream licenses and provenance were not changed.

## Failures and limits retained

`memory_prefault01` contains an initial unused-variable fixture compile failure;
the corrected pre-fix reproduction is `memory_prefault02`. `memory_post01` passed
26 tests, then a production ARM O0 attempt exposed a map argument also containing
`,--cref`; the final parser and 31-test run cover that actual argument shape.
`memory_host01` requested a nonexistent case name and failed; no full pass is
inferred from it. All failures remain in the archive.

The additionally attempted **KF legacy O0** link fails physical Flash capacity by
**1088 bytes**. This combination had not previously been established to fit;
the failure is not waived by the successful O2 build or current-mode O0 links.
Whole-firmware stack/MSP/ISR bounds and manual critical-contract acceptance remain
NOT_PROVEN. CCM spare bytes, Host timing and compiler frames do not establish
hardware timing, navigation accuracy or flight qualification. No hardware was used.

The separate logger scheduling trial is outside this batch and is not committed
or accepted through these results. No frozen release, GSHC or USB source is changed.
