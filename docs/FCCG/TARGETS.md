# Development targets

## Algorithm actual parameters / 算法实际参数

新增独立算法参数页面（硬件连接之前），插件声明实际值、单位和 representation。
Project format 12；`.ssdecoder` / project-semantics 1.2，拒绝 decoder 1.1；
产品当前为 0.1.0，沿用合仓前平台规范；Record Catalog 与协议布局不变。
参数清单、生成绑定与 Recorded Configuration / Offline What-if 边界见[参数契约](ALGORITHM_PARAMETERS.md)。
精确验证结果仅见仓库根 VALIDATION.md。

以下带日期的检查点保留当时版本号和页面结构；当前版本与五页面流程以上述算法参数契约为准。


## Logger startup burst closeout

- [x] bounded bootstrap admission, retained critical snapshots and immediate drain after open
- [x] distinct suppression/rejection/overflow, writer fault, session and latency diagnostics
- [x] default multi-stream startup/START model and finite overload recovery with strict C-writer audit
- [ ] repeated SS0.5 real-card startup with zero overflow/gaps, task HWM and storage latency margins

This follows the storage byte repair; SSLOG 0.0 and decoder/project semantics 1.1 remain unchanged.
Executed gates and queue/memory snapshots are recorded only in [VALIDATION.md](VALIDATION.md).

## Storage byte integrity

- [x] arbitrary-buffer SDIO bounce ownership and bounded fail-closed completion handling
- [x] Logger partial-write replay removal, bounded critical-burst sync coalescing and diagnostics
- [x] full startup queue drains and backfills its Required decoder descriptor without reopen loops
- [x] real FatFs/Logger/codec Host regression, explicit queue-drop gaps and strict offline audit
- [x] optional Target bench harness outside normal firmware sources
- [ ] SS0.5 real-card repeated preflight/NONE/alignment/START/stop/readback acceptance and SS0014 audit

Actual gate results and memory changes belong in [VALIDATION.md](VALIDATION.md).

## Documentation authority

Start with [FCCG documentation](README.md) and the [current SilverStar platform specification](platform/README.md).
The [shared Calibration contract](AIR_CALIBRATION_CONTRACT.md) owns cross-component behavior;
[runtime safety](platform/details/RUNTIME_SAFETY.md) owns platform runtime rules.
Imported builtin documents are package-local implementation notes. Reference re-import must never
overwrite `docs/platform/`; historical documents keep their original semantics. Exact test, hash,
FLASH/RAM and acceptance snapshots belong only in [VALIDATION.md](VALIDATION.md).

## 2026-09-05 runtime indicator, stack and calibration repair

- [x] production indicator initialization and Host startup/GPIO integration coverage
- [x] build-derived `0x01/03/05/07` calibration capability and shared C procedure gate
- [x] NONE identity READY on empty-build init/reset with effective result logging retained
- [x] deferred full ALIGN_START processing in FlightTask and bounded command-side origin reset
- [x] reproducible Release/Debug stack report for every static task, including Idle
- [x] bounded static overflow record with stable task identity and valid cached HWM
- [ ] continuous SS0.5 startup, repeated AIR/Serial commands, task HWM, MSP nesting and log verification

## 2026-09-02 verified Board fixed-resource mapping repair

- [x] verified Board `connections.json` is the sole logical-ID mapping authority; CubeMX inventory
  order is validation data and cannot override generated Platform table designators
- [x] SS0.5 GPIO 0–8 golden mapping covers SX1281, launch/parachute outputs, system indicator, and
  GNSS reset/timepulse with exact generated validity entries
- [x] Platform Resource Closure Check rejects missing/drifted aliases and corrupted generated table
  entries without scan-order or first-resource fallback
- [x] deterministic resource-binding fingerprint covers Board ID/version/manifest, fixed aliases,
  resolved handle/port/pin/channel facts, physical pin, and renderer contract; readiness detects
  drift in hardware-preparation and ownership metadata
- [x] custom CubeMX manual assignment and imported `logical_index` behavior remain unchanged
- [ ] physical SS0.5 actuator/indicator/radio pin verification remains hardware qualification work;
  this repair validates generation semantics and firmware builds, not electrical behavior

## 2026-08-31 bounded same-model multi-instance and minimal failover

- [x] JY901B, NEO-M9N, and E28-2G4M12SX/SX1281 allow up to four context-safe repeated instances,
  with deterministic IDs, independent typed resource rows, static resource tables, and one copy of
  each source in the graph
- [x] all selected IMU/GNSS instances initialize, process, and retain independently identifiable
  native-log sources; one configured primary plus stable remaining instance order forms the backup
  chain
- [x] IMU chooses the first initialized fresh finite source before calibration/alignment and then
  locks for the run; no in-flight IMU switch, voting, cross-check, multi-calibration, or Multi-EKF
- [x] GNSS performs latched one-way basic-liveness failover while treating fresh no-fix messages as
  live; no backup leaves the current source active and polled
- [x] AIR M0 binds an ordered telemetry candidate set but transmits/receives through exactly one
  active transport; ten consecutive true local TX timeouts trigger one-way failover, success resets
  the counter, busy does not increment it, and an exhausted last source continues bounded periodic
  retries
- [x] source changes reuse the existing SSLOG EVENT payload and `.ssdecoder`/project-semantics stay
  1.1; AIR M0, maintenance 0.0, SSLOG 0.0, and all record layouts remain unchanged
- [ ] real dual-JY901B, dual-NEO-M9N, and dual-SX1281 electrical, RF, HIL, and flight validation
- [ ] future full health management: numeric IMU cross-check, bias/stuck detection, 2oo3 voting,
  GNSS residual/quality ranking, Multi-EKF, RF end-to-end health, and explicit failback policies

## 2026-08-31 SilverStar 0.0.10 final freeze

- [x] one authoritative 0.0.10 application/platform/generated-firmware release identity while
  preserving independent Profile, schema, upstream, Board, MCU, CubeMX, and firmware-package versions
- [x] cwd-independent pure portable-relative-path validation with filesystem-root write protection
  unchanged
- [x] MCU/Platform-owned build Target Profile and strict persisted lock; synthetic alternate-target
  coverage remains test-only and makes no H7 support claim
- [x] calibration UI/project semantics limited to empty, OneFace, SixFace, or both; empty maps to
  NONE/READY identity correction and Required `CALIBRATION_RESULT`
- [x] project format 11, AIR M0, maintenance/SSLOG 0.0, Record layout, and `.ssdecoder` 1.1 frozen
- [x] fresh Python, 8-protocol-combination Release/Debug, 4-calibration-combination, Host,
  architecture, Power of Ten, static-analysis, and artifact acceptance recorded in `VALIDATION.md`
- [ ] SilverStar_FLP follow-up: import one log at a time, require an exact `.ssdecoder`, reject
  unpublished old logs, and allow offline algorithm comparison independently of the onboard list
- [ ] physical I²C pull-up and PWM waveform/safe-level electrical validation
- [ ] dual-hardware-platform internal testing and real H7/G4 production plugins
- [ ] normal Classic CAN consumer and its filter/router/bus-off contract

## 2026-08-30 optional Protocol and firmware gating

- [x] strict project format 11 with exactly three nullable Protocol slots, deterministic format-10
  migration, stable canonical `null` state, and no fake None plugin
- [x] Device/Protocol independence: transport removal atomically clears the dependent slot, while
  Device restoration never auto-enables a Profile
- [x] three always-visible localized Protocol combos with disabled unavailable Profiles and transport
  explanations; logging controls/export are inactive under Logging None
- [x] declarative maintenance endpoint lifecycle through `auto_managed_protocol_category`, including
  Console/UART assignment and SerialTask removal/recreation
- [x] one Source Graph for all eight T/M/L combinations, with stable compile-time feature macros,
  static task-index semantics, no disabled stack/TCB allocation, and no heap
- [x] Logging None omits LoggerTask/SSLOG/Log Sink, `.ssdecoder`, descriptor and golden artifacts;
  project semantics remains auditable and stale managed decoder files are removed transactionally
- [x] package/project-semantics schema 1.1 with nullable telemetry/maintenance locks and a mandatory
  logging lock inside every emitted `.ssdecoder`
- [x] all eight official SS0.5/F407 combinations built in Release and Debug; the default composition
  retained `AIR-NCRC`, while T=0/L=1 uses the documented eight-zero compatibility tag

## 2026-08-30 internal software release-candidate closeout

- [x] project format 10 with actual imported-MCU-first matching, strict Platform compatibility, declarative CubeMX module/provider activation, FatFs/timebase inventory, and deterministic format 0–9 migration
- [x] Device-owned single-instance `silverstar.device.storage.sd_sdio_fatfs`; Board supplies only verified physical mappings, MCU supplies controlled FatFs core/HAL providers, and CubeMX supplies SDIO plus App/Target glue
- [x] generated storage source moved to `Devices/Storage/SdSdioFatFs`, so format-9 projects retain legacy Board files without collision while the Source Graph compiles the new owner exactly once
- [x] dynamic CubeMX HAL timebase validation and rendering with no hidden TIM1 assumption; invalid SysTick, missing/mismatched init, frequency, IRQ, and PWM/timebase collisions are rejected
- [x] I²C/PWM provider boundaries, reserved Classic CAN consumer rejection, strict HAL/CMSIS single-source policy, and no default compile-all behavior
- [x] 36 strict builtin packages and 48 builtin/schema JSON documents
- [x] fresh default and custom-F407 generation/build/Host validation plus architecture, Power of Ten, static-analysis, artifact, GUI, migration, and schema regression coverage
- [x] status remains **Software Release Candidate / Pre-Hardware-Validation**; no tag, push, public release, flash, electrical, or flight claim

## 2026-08-28 internal firmware/plugin refactor

- [x] reproducible read-only reference snapshot plus FCCG-owned overlay provenance; external firmware remains unchanged
- [x] at the 2026-08-28 checkpoint, three then-mandatory single-category Protocol plugins with locked component/version/Profile/manifest hash and deterministic format-7 migration; format 11 now permits each slot to be `null`
- [x] at the 2026-08-28 checkpoint, project format 8 added explicit `protocols` slots and the detected MCU/Platform lock; format 0–7 files remained readable and saved as format 8 at that checkpoint
- [x] Board/imported CubeMX facts automatically match an installed MCU/Platform plugin; the Devices page no longer exposes an MCU selector
- [x] manifest-driven Platform resource renderer with no STM32F4 header/getter or MCU-model whitelist in Python
- [x] conditionally selected F407 I²C, Classic CAN, and PWM backends with static APIs, resolver constraints, Host mocks, and no default-SS0.5 inclusion
- [x] strict `sensor.*`, `link.*`, `storage.*`, `actuator.*`, and `indicator.*` categories plus dynamic Devices-page grouping
- [x] logging-plugin-owned Record Catalog and data-only `.ssdecoder` semantics covering three protocols, hardware, resources, devices, algorithms, and logging
- [x] 36 strict builtin packages: the former three-category bundle is replaced by three independent Protocol packages and hardware-facing services have explicit owners

## 2026-08-28 multi-instance/decoder-profile round

- [x] dynamic display of all valid installed Device manifests; Board/IOC incompatibility is deferred to Hardware Connection
- [x] one-MCU project model with multi-instance Device/capability identity and latest physical/source descriptor metadata
- [x] `build/FCCG/<target>/<config>`, StaticAnalysis, Host, EIDE, `clean-all`, and opt-in Listing layout
- [x] normalized shared EIDE ownership that ignores ordering/UI state but reports changed FCCG-owned fields
- [x] absolute Host GCC propagation, target validation, UTF-8 diagnostics, persistent nonmodal quality results, and real BEGIN/DONE progress
- [x] semantic logging Cadence with unit-aware periodic editing, source/event/measurement/one-shot text, and DECIMATION-only extraction editing
- [x] optional producer declarations that distinguish a known Record format from a producer in the selected component composition
- [x] verified **Export Log Decoder Profile** action plus deterministic canonical `.ssdecoder`; no executable decoder or multi-version parser is claimed
- [x] hidden Devices-page maintenance endpoint with the UART Transport retained in protocol binding, source graph, and Hardware Connection
- [x] reusable PLAN/BEGIN/DONE progress for generation, save, Save As, CubeMX, plugins, tools, Host tests, architecture, Power of Ten, and artifacts; failure/cancel never force 100%
- [x] strict Service → Profile → Transport Binding → Physical Device/Storage protocol resolution for the three real profiles
- [x] deterministic source-package export that preserves source tests and excludes generated/binary artifacts
- [x] retrying repository cleanup with read-only handling, per-target failure aggregation, and an explicit report for abnormal Windows ACL remnants

## Current FCCG upgrade

- [x] Draft/Dirty/Materializing/Ready/Building/Error lifecycle with staged complete Save and descriptor-last publication
- [x] one `Project_EnsureBuildable` path for Build/Clean and all five checks, including dirty auto-save, current renderer refresh, and explicit project `cwd`
- [x] idempotent verified-Board hardware preparation with automatic Save integration and no CubeMX call for SS0.5
- [x] Release-default `-O2 -g` / selectable Debug `-Og -g3 -gdwarf-2` policy with assertions retained and dual-configuration Make/VS Code/EIDE output
- [x] manifest-driven multi-select Mode/log defaults while preserving existing projects and locking Required logs
- [x] shared worker/progress/localized-error path, aligned bilingual wizard, and no unvalidated GUI/Make/VS Code/EIDE flash entry
- [x] non-blocking Board preparation planning plus completion-safe QRunnable ownership after 100% progress
- [x] Custom STM32 Hardware as the new-draft default, with no visible unselected entry or Board-only preparation action
- [x] fixed the three checkable-GroupBox interaction failures with visibility-only collapsible sections and visible cross-theme checkboxes
- [x] Protocol-owned SSLOG metadata, Required/Recommended/Optional policy, capability-aware availability, and deterministic data-only `.ssdecoder`
- [x] Project format 11 with `DeviceInstance`, manifest-driven Mode parameters, three explicit nullable protocol locks, Platform lock, decoder-profile hashes, assignment confirmation fingerprint, FatFs/timebase facts, and v0-v10 migration
- [x] Physical Device `provides` + consuming component `requires {capability,purpose}` + automatic/ambiguous provider resolution
- [x] backward-compatible Device instance policy with independent `plugin_max` and `class_max`; repeating one model requires a context-safe driver, while different singleton models may share a class
- [x] `.ioc` physical truth for builtin/custom Boards plus semantic `connections.json`
- [x] UART/SPI/I2C/ADC/Timer/PWM/CAN/GPIO/EXTI/DMA/NVIC/clock inventory without parser count caps
- [x] separate FCCG-internal and explicitly authorized user-project roots
- [x] localized structured error dialogs, buttons, filters, build labels, and startup failure logging
- [x] latest-reference discovery/explicit selection and read-only provenance import
- [x] 36 real builtin components, including three independent Protocol plugins, a physical storage Device, internal mission-action/indicator services, and declarative voltage/mission-action/System/GNSS Indicator Devices
- [x] strict Project format migration plus generic Strategy/Mode dictionaries
- [x] four-page GUI; File owns New/Open/Save/Save As and Plugins owns manager/install/refresh dialogs
- [x] one-step New Project dialog with project name/output only and complete-source Save As
- [x] Board provides/defaults/candidates/fixed/reserved/conflicts and compatibility/auto-assignment
- [x] trusted STM32CubeMX `.ioc`/directory import with MCU/layout/peripheral/RTOS validation
- [x] isolated HardwareGenerated ownership, warning, Power-of-Ten boundary, and dangerous replacement
- [x] custom Board `.ssplugin` export, secure install, and second-project reuse
- [x] one resolved source graph for Make, native EIDE, and VS Code
- [x] Estimator=None excludes KF6 before build rendering
- [x] current Power of Ten, forced memory include, CCMRAM/DMA contract, Debug/Release/static/artifact tasks
- [x] F407 reference, same-MCU Board A/B, and custom hardware acceptance fixtures/tests
- [x] Locked required SSLOG checkboxes plus model enforcement and Protocol-owned metadata
- [x] Simplified Chinese/English four-page coverage and updated architecture/user/plugin/build documentation
- [x] Devices → Flight Configuration → Hardware Connection → Code Generation & Build flow with read-only derived capability usage on Flight Configuration
- [x] candidate/reconcile changes, edit-vs-strict validation, non-fatal unselected hardware, and assignment retention/cleanup/auto-map
- [x] formal Raw/Data versus Qualified capability model with JY901B evidence and localized unavailable-use reasons
- [x] generation-first workflow with Generate Code, Open VS Code Workspace, Open Project Folder, and no separate Build Release action
- [x] Release-default Make/VS Code/EIDE output with Debug retained, advanced Release Validation Build, dry-run planning, structured progress, and live logs
- [x] unchanged-file Apply semantics that preserve managed mtimes, project-owned payloads, build directories, and Make dependency files
- [x] normal build summary without duplicate tool status; advanced firmware/host environments separate Arm GNU, GNU Make, and Host GCC with derived objcopy/size and installation guidance
- [x] JY901B preflight 6-axis/9-axis quaternion qualifications separated from absent authoritative runtime qualifications
- [x] independently optional launch/parachute mission-action Power Outputs, external-ignition START behavior, and deployment-mode clearing/restoration without actuator auto-readd loops
- [x] Provided/Consumed/Recordable separation with POWER and HW_QUAT_NATIVE available and device-config-disabled MAG_NATIVE
- [x] deferred snapshot-based Mode/Logging transactions with rollback, traceback logging, incremental log widgets, and 50-change signal stress coverage
- [x] generated deployment trigger mask/threshold/delay header with seconds-to-milliseconds conversion and review/decoder propagation
- [x] typed UART/SPI/I2C/PWM and GPIO electrical/resource validation, physical-resource exclusivity, and invalidated manual-assignment fingerprints
- [x] selectable AIR M0, serial maintenance 0.0, flight-log format 0.0, and explicit None profile states with pre-release ID migration and unchanged wire formats
- [x] System Status Indicator on active-low SS0.5 PA1 plus optional GNSS Indicator using `position_usable` and an independent GPIO contract
- [x] unified generation fingerprint shared by digest/readiness/ownership, excluding host tool paths and provenance
- [x] validated reference EIDE/workspace templates and `code.cmd`/`code.exe`/`code --new-window` launch with one localized manual-open failure dialog

## Current validated scope

- STM32F407VET6 + SS0.5 is the only complete firmware-build-validated target.
- STM32 + STM32CubeMX is the only formally supported manual hardware-configuration path in v0.x.
- VS Code + EIDE + Arm GNU Toolchain is the only DevelopmentEnvironment renderer.
- Current selectable Strategies: Alignment (four choices), INS Coning2Sculling2, Estimator KF6/None, Landing Stillness/ImpactThenStillness/BarometerImuWindow. Landing selectors share the centralized reference implementation; they are not three independent duplicated C payloads.
- Current real Modes: Calibration and Deployment triggers.
- JY901B raw magnetic/external-attitude data does not grant absolute-vector or authoritative runtime quaternion qualification. Its explicit static preflight qualifications make HardwareQuat6AxisKnownYaw and HardwareQuat9Axis alignment available. GravityMagTriad and ImpactThenStillness remain unavailable; GravityKnownYaw, Stillness, and BarometerImuWindow are available.

## Deliberate limits / future work

- No Guidance, Control, Control Allocation, or continuous-control actuator implementation is supplied. The current launch-ignition and parachute-pyro Power Output plugins are declarative one-shot Devices backed by an explicit internal mission-action service, not by Board ownership.
- No alternate MCU, non-STM manual provider, Keil, IAR, or fictional environment project is generated.
- FCCG inventories clocks, pin alternate functions, interrupts, and DMA, but does not solve or edit clocks, PLL, pinmux, alternate functions, or DMA streams.
- Custom hardware is generated with an explicit unverified warning; generation does not claim official Board validation.
- The current production Platform package is verified only for STM32F407VET6/SS0.5. A virtual H7 contract fixture proves renderer portability but is deliberately not an installed/supported target.
- F407 I²C is blocking 7-bit master plus memory-register access and does not claim generic repeated-start; Classic CAN is bxCAN only and single-owner per peripheral; PWM is ordinary fixed-frequency, non-complementary output with CubeMX-owned timing.
- FLP does not yet import `.ssdecoder`; this round defines and emits the safe profile contract without modifying FLP.
- **Export Log Decoder Profile** writes a verified data-only package; this round still does not implement a log parser, executable decoder plugin, or version-plugin system.
- [x] Final multi-instance facade, Record Catalog, decoder descriptor and STATS/TELEMETRY_DIAG producers are imported from verified read-only provenance; exact source evidence belongs in `VALIDATION.md`.
- The GUI exposes add/remove controls when class capacity and another legal model/instance remain; same-model repetition still requires a context-safe manifest. Firmware-backed builtin limits are synchronized only after the specified reference commit passes the dependency gate.
- Full health-managed voting, in-flight IMU failover, Multi-EKF, GNSS quality comparison, RF
  end-to-end health, and automatic failback are not implemented. The only runtime switching is the
  narrow latched GNSS-liveness and local telemetry-TX-timeout policy described above.
- EIDE native metadata is generated and structurally/architecturally checked; an EIDE CLI builder is required before claiming an actual EIDE-native compile.
- No current Board/Environment pair declares validated flash capability, so FCCG emits no GUI, Make, VS Code, or EIDE upload action; no hardware flash or electrical test is claimed.

## Shared algorithm-parameter closeout

- [x] generic owner ordering by `selection.ui_order` and deterministic component ID
- [x] declarative, strictly compatible `shared_key` groups with one GUI editor and synchronized format-12 values
- [x] separate INS/KF6 generated macros and decoder resolved values; `.ssdecoder`/semantics stay 1.2
- [x] required FLP minimum corrected to 0.0.2 without changing FLP
