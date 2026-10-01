# Software recovery stage 2 — 2026-10-01

Software source frozen at `50cc2d3fb4ac7b7e3a84267a82183b4131b23369` on
`fix/software-reconnect-ground-20261001`. Main and the experimental history are
preserved. No push, merge, tag, release, serial, SWD, reset, programming, desktop
update or process shutdown was performed. TEST_4 configuration, source, ELF and
logs were not modified. The real session log was read only for event evidence.

Status: **software gates passed; bench review pending**. Critical-contract manual
acceptance, whole-program stack/call graph, MCU timing, RF reliability and hardware
qualification remain **NOT PROVEN**, not new absolute software gates. A successful
tool exit does not establish original Power of Ten compliance or useful assertion
density. Historical density reports and failure evidence remain unchanged.

## Reviewable changes

| Commit | Change and review points |
|---|---|
| `10e0857` | Ground fixtures now select the real F103 Ground PCB, preserving role validation; current version assertions; immutable snapshot links resolved using their inventory's original source context; short English SCG title fits the single-line header. Chinese title/layout unchanged. |
| `0ed73f3` | GSHC tests: two advancing stale boot-relative samples conservatively cancel pending START without replay; BOOT translation and self-test result/alias checks. |
| `7676ff2` | Owner `telemetry_service.c`: `CommandEqual`, `CachedAckQueue`, `AckRawQueue`, `AckQueue`, `CapabilityCommand`, `CommandIsPendingStart`. Full command-field retry key, four-second reuse bound, newly validated Capability invalidates old cache; Capability bypasses cache and checks current advertisement. Async START retains its full request; malformed input keeps ordinary responses. Owner SX1281 `Lora_StartRx`, `Lora_Process`, `Lora_ForceRxContinuousDirect`: per-instance 120 ms RX dwell after TX completion/timeout, wrap-safe owner clock, unchanged FIFO/full-queue paths. |
| `ae93a38` | `_Makefile_Render`, `GroundFiles_Render`, Ground declarative payload: actual `architecture-check`, `host-tests`, `artifact-check`, `static-analysis`; excluded Flight adapter include directories now removed with excluded adapter sources. Real ARM analyzer objects/link use separate `build/analysis`. |
| `50cc2d3` | Windows artifact gate reads UTF-8 generated/source inputs explicitly; fixes the actual GBK decoding failure from v5. |

See [gate scope and RX/cache policy](../GROUND_SOFTWARE_GATES.md).

## Executed evidence

`manifest.json` records commands, working directories, exact exits, complete log
hashes, generated input hashes, source commit and GSHC runtime source hashes.
The final `run_v6_gates.py` run executed all 21 recorded steps with exit zero:
three tool-version calls, six Flight stages, and six stages for each of two
Ground projects. No subset was substituted for that full run.

- Two fresh v6 projects: configuration/save/reopen; first Flight-only or
  Ground-only generation, then both; repeated generation preserves owned source.
  Both use the real F407 Flight / F103 Ground board declarations. Synthetic
  custom IOC import/export/reuse and resource-map regressions passed in the
  targeted hardware tests; fixtures are not hardware validation.
- Flight: complete generated Host suite, **72 executables, 4,394,611 checks,
  zero failures**, seven positive compilation cases and 17 expected negative
  compilation cases; emitted architecture and PoT; ARM compilation/link and
  artifact inspection; real ARM `-fanalyzer` compilation/link; emitted stack report.
- Each Ground: ARM compile/link, emitted architecture, PoT, two generated-source
  Host executables (bridge bounds/errors/backpressure, selected UART DMA/ring),
  ARM ELF/BIN/memory/link-map checks, real ARM first-party analyzer compile/link.
- Five generated architecture fault cases reject missing sources, escaped paths,
  graph/Make mismatch, wrong target role and absent bridge startup. Actual linked
  artifact negatives reject damaged BIN, missing link object, wrong ELF machine
  and stale source. `artifact_negative_results.json` records all four rejections.
- Same fault assertions on pre-fix versus post-fix owner sources: telemetry
  **1,015 checks: 5 failures → 0**; SX1281 **638 checks: 201 failures → 0**.
  Old sources are archived and hashed; pre-fix baseline is `10e0857`.
- Additional real driver/protocol Host scheduling harness: continuous populated
  TX FIFO, injected normal completions/clock/RX command; an actual AIR ACK admitted
  behind seven telemetry packets starts TX after **1,380 mock ms**, **76 checks,
  zero failures**, including millisecond-counter wrap. This establishes only
  that simulated schedule, not RF delivery, an STM32 deadline or all fault-time
  latency. Existing host retry/timeout durations were not extended.
- GSHC targeted protocol/handshake/events: **56 tests + 3 subtests passed**.
  FCCG old remaining subset: **18 passed**. Expanded gate/radio/target subset
  initially **41 passed, 1 failed** due to the old immediate-TX expectation;
  updated dwell/initialization contract then **26 radio tests passed**. Final
  hardware/gate/GUI/docs subset **21 passed, 2 setup failures** because its temp
  directory was outside the application workspace; the four GUI tests rerun in
  the authorized application workspace all passed. These are separate executed
  scopes, not a full application suite claim.
  After the evidence README was written, all **six documentation tests passed**.

Flight PoT reports 108 first-party C files / 2,610 functions / 739 nonblocking
recommendations; Ground 15 / 148 / 34. Both explicitly report critical-contract
review NOT PROVEN. Stack report's configured/estimated figures are limited tool
estimates; they do not prove library/indirect/dynamic frames, MSP or ISR nesting.
Linked third-party HAL, CMSIS, SX1280 SDK and newlib remain outside the first-party
PoT gate and unresolved whole-firmware timing/stack analysis. Ground linker logs
retain existing newlib `_read`/`_write` implementation warnings and their GC notes.

## Failures, retries and limits

Complete saved intermediate logs remain: initial old GUI/docs failures; Ground
probe's nonexistent excluded adapter include; GSHC translation test constructor
mistake; shared pytest-directory permission failure; outside-workspace GUI setup
failures; old immediate-TX fixture failure; two v5 Ground artifact gate failures
from GBK decoding. The UTF-8 probe used corrected Tools on a disposable v5 copy;
it is not final acceptance. Final acceptance reran the emitted gates on fresh v6.
Early focused compiler setup attempts missed the forced configuration/current
radio header, and an early Capability test sampled before its queued send; those
were harness setup errors. Their overwritten intermediate compiler output is
not presented as complete saved evidence or as the pre-fix defect demonstration.
The final saved focused commands/logs demonstrate the unchanged intended checks.

Actual read-only session log line 34: STATUS `SELFTEST_COMPLETE`, `arg0=0`,
`arg1=0`, at boot-relative 4,208 ms. No BOOT or SYSTEM_READY record was found in
that session. Current BOOT i18n is “启动” / “Boot”; it is not “系统就绪”. The event
now displays the actual pass/fail result. Completion does not override snapshot
readiness or make START permissible.
Original log path and SHA-256 are retained in the manifest and the
[stage 1 read-only log inventory](../software_recovery_stage1_20261001/real_log_readonly.json).

AIR M0 has no session nonce, so wire-identical requests inside the retry lifetime
remain indistinguishable from retries. Two stale advancing samples can conservatively
clear the session; business requests are cancelled, never replayed. The RX dwell
changes effective throughput; queue pressure, packet loss, physical receive-window
adequacy and command latency must be measured on the selected PHY. IMU startup
failure / alignment prerequisites and the original board PING timeout are not
claimed fixed by this software evidence. No SF6, memory-layout, barometer,
estimator or multi-telemetry expansion was undertaken in this slice.

## Frozen artifacts

Independent directory:
`D:\python_software\SilverStar\.work\SoftwareFreeze_20261001_v1\FrozenArtifacts_50cc2d3`.
All four files are copied from the fresh normal v6 ARM build; analyzer images and
earlier candidates are excluded. Original candidate projects stay separate.

| Artifact | SHA-256 |
|---|---|
| Flight ELF | `bd19f5cff57cf28b33623b50dc13e89a50ef458258c30c4363c3d0248e51f601` |
| Flight BIN | `d470768aace147c700b4d3f685c022d54950289d71859d789e8d7fa9671a83f5` |
| Ground ELF | `d32e243c41846569306dee805a0b31b4b3c4c71dab6a31c376f35f08feda04a9` |
| Ground BIN | `d5e16e44d8f2f00a289415d449eb2e223b0ff30431b57af986d03661e8cf876d` |

GSHC is the **0.1.1 source application at source commit 50cc2d3**; every tracked
runtime Python file and VERSION is hashed in the manifest. No new packaged EXE
was built or substituted, and an older EXE is not this reviewed source version.
Ground metadata supplies configuration version provenance; embedded Ground
product-version identity remains NOT PROVEN. Bench use requires the parent's
review/hardware phase authorization; this slice performs no hardware actions.
