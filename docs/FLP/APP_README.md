# SilverStar Flight Log Processor

## Current SilverStar project folder workflow

Use **Open SilverStar Project Folder** for a project created by FCCG. FLP reads the root `<ProjectName>.ssdecoder`, offers logs under `Log/` for one-at-a-time selection, and checks the exact decoder identity before opening. The default export directory is `Log/<LogStem>_Export/`. Direct `.BIN`/`.sslog` and manually selected `.ssdecoder` remain available. Details: [project folder contract](../architecture/PROJECT_FOLDER_CONTRACT.md).

Current formal logging, fixed-lag replay, single Analysis Source, shared range and paged/GIF
exports are defined in [Field Log Replay](Field_Log_Replay.md). Exact validation is in
[VALIDATION.md](VALIDATION.md). Historical test snapshots below do not supersede that contract.


SilverStar_FLP is a Windows desktop application and command-line toolkit for SilverStar
`SSLOG0` flight logs. It parses the current binary profile, reconstructs the complete Pure INS
and KF6 navigation chains from `START`, compares recorded and recomputed results, visualizes the
flight, and exports timestamp-faithful data products.

Version: **v0.1.0**

> Raw `.BIN`/`.sslog` logs and `.ssdecoder` packages are opened read-only. A `.ssflp` v3 project
> stores one log reference, exact decoder/cache identity, replay settings, notes, and UI state; it
> never embeds or rewrites either source.

See [KF6 field analysis and project paths](KF6_FIELD_ANALYSIS.md) for outage recovery,
independent vertical velocity noise, default project roots and per-log result directories.

## Start here

### 1. Install the shared environment

From the SilverStar monorepo root in PowerShell:

```powershell
.\tools\setup_venv.ps1
```

FCCG, GSHC and FLP use this one root `.venv`.

### 2. Open the application

```powershell
python FLP.py
```

The recommended path is **Open SilverStar Project Folder** and select the FCCG
project root. FLP lists log files only below `Log/` and uses the root decoder.
For standalone analysis, choose **New Project** to select a `.ssflp` location first, then select exactly one flight
log plus its `.ssdecoder` (or run the bounded task-folder search). The project file is written
only after exact-pair validation succeeds. Choose **Import Log / Decoder** for a temporary
session that does not require an immediate project save. You can drag one log with an optional
package onto the window; a log by itself invokes the same bounded exact search. Command-line GUI
startup accepts the explicit pair:

```powershell
python FLP.py D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder
```

The dark-blue brand header shows the localized application name, `v0.1.0`, developer credit,
compact current-project name (with the absolute `.ssflp` path in its tooltip), then flexible
space, language, and theme. The File menu provides New Project (`Ctrl+N`), Open Project (`Ctrl+O`), Save Project
(`Ctrl+S`), Save Project As (`Ctrl+Shift+S`), Import Log / Decoder, Export (`Ctrl+E`), and Exit.
The adjacent Plugins menu provides Manage, Install, and Refresh; Help provides About. Plugin Manager reads the runtime registry. Install accepts only explicitly trusted `.ssplugin` container packages, never executes archive Python, and requires restart plus a host-allowlisted factory before activation. There is no online store, dynamic Algorithm installer, or duplicate toolbar.
Import and export use focused option dialogs. The five analysis pages are:

1. Overview — mission/file and exact decoder identity, flight metrics, deploy altitude/reason,
   configured calibration flow plus the selected effective model, initial alignment result, and
   GNSS online/fix/usability state, translated event timeline, and explicit Data Quality status.
2. Replay — every installed offline algorithm, independently labeled for firmware membership,
   recorded output, and offline-plugin availability. Recorded Configuration is enabled only when
   every required firmware actual parameter is present in the exact package; Offline defaults and What-if remain distinct. Every run is
   retained. A dedicated **Analysis Data Source** selector begins with Recorded data and exposes
   only complete, successful runs.
3. Flight — START-cropped ENU velocity/position, corrected IMU, authoritative software attitude,
   and a themed 3D attitude/trajectory replay with its own playback controls. Before Deploy the
   path/current point are red; after Deploy they are blue; Deploy is one extent-scaled orange
   world-space point. Recorded Pure INS and Recorded KF_6 remain separately identified, with only the selected source visible
   curve layers.
4. State Estimation — metadata-selected estimator state groups, covariance as 1-sigma or Pii,
   measurement-group innovations/NIS/noise/age, and generic sequential-update results. The page
   contains no KF6-specific channel IDs, so future estimator groups and sensors can be declared by
   a plugin without page-code changes.
5. Data Explorer — searchable raw/stable/capability/algorithm channel groups, Record View and
   logging metadata, configured streams with zero actual samples, unknown raw payload hex, every
   decoded record with file offsets, parser diagnostics/damaged spans, and uniquely named replays.

The Replay page groups What-if parameters into Process Model, Initial Covariance, Measurement
Noise, and Consistency Gating. For onboard algorithms, What-if copies the complete firmware actual configuration;
for algorithms absent from firmware it uses plugin actual defaults. Incomplete firmware
configurations cannot be completed with offline defaults. The form scrolls when taller than the available window.
Every combo box uses a conventional downward popup with at most ten visible rows; longer lists
scroll inside the popup. Flight and State Estimation each provide a page-level **Reset Charts**
button that restores every 2D chart on the page after manual zooming or panning.

Chinese and English interface text and Light/Dark themes are built in. Export language defaults
to **Follow UI**, with explicit Simplified Chinese and English choices. Standard PNG plots,
the deploy-segmented mission-relative ENU trajectory, and the combined attitude/trajectory GIF use
matching `_ZH` or `_EN` filenames and localized titles, axes, and legends. The GUI and export
share the same rocket attitude model, START-relative origin, and deploy/landing/current markers.
For a SilverStar project root, export defaults to `Log/<LogStem>_Export/`.
With a standalone `.ssflp` project, export defaults to `<project-directory>/Result`;
a temporary log defaults to `<log-directory>/<log-stem>_Data`. The destination remains editable, no fixed drive is
used, and FLP does not offer a source-code-package export.

An FCCG `SilverStar.ssproject` may sit beside a log, decoder, and `.ssflp`, but FLP neither parses
it nor treats it as authoritative. The only decoding authority remains the exact match between
the BIN/SSLOG Descriptor and `.ssdecoder` 1.2.

## What the parser supports

The trusted built-in container ID is `silverstar.flight_log.container.0_0`. It supports
SSLOG0's 64-byte file header, 24-byte common record header, payload, CRC-32/IEEE trailer,
resynchronization, truncation handling, and raw-frame diagnostics without knowing any Record
fields or channels.

The firmware/FCCG schema ID `silverstar.sslog.container/0.0` is accepted only as an audited name
for this same built-in wire contract; it does not register or execute a second plugin.

Production opening is exact and configuration-driven. `LogOpenCoordinator` validates one package
schema 1.2, requires a matching 64-byte log Descriptor, imports the verified package into the
content-addressed cache, creates `DecoderProfileParserPlugin` dynamically, parses the Catalog,
then applies Project Semantics and calibration before publishing a dataset. GUI manual import,
bounded folder search, drag/drop, CLI, and project restore use this same atomic path. There is no
Descriptor-less, package 1.0, unsigned, fixed-parser, or filename-based production fallback. See
[Decoder_Profile_Package.md](Decoder_Profile_Package.md).

- Unknown CRC-valid types/versions retain their raw bytes and mark the dataset partial.
- A bad CRC, invalid length, or lost sync performs a bounded scan; a `FLG1` candidate is accepted
  only after header, length, timestamp, complete-frame, and CRC validation.
- Bad frames are excluded without payload repair. Diagnostics retain recovered offsets and a
  bounded raw-hex preview of each damaged byte span.
- An incomplete final record is reported as a truncated tail and ignored.
- Record counts, CRC errors, recoveries, sequence gaps, unknown types/versions, and offsets are
  retained in parser diagnostics.
- Decoded Records retain file order/offset even when interleaved timestamps regress. Each channel
  independently sorts its real `timestamp_us`; unlike-rate sensors are never forced into one table
  and timestamps are never rebuilt from nominal rates.

A ready calibration mode `NONE` is a legal identity model (zero bias, unit scale, zero
sample/reject/retry counts) even when only `SixFace` is configured; its `start_sequence` is
provenance and may be nonzero. A configured/online GNSS with no fix and zero usable fusion
measurements is also legal. These states are reported explicitly instead of being treated as
missing packages or parser failure.

AIR telemetry frames are intentionally not treated as flight logs. See [SSLOG.md](SSLOG.md).

## Navigation replay semantics

At successful `START`, `INITIAL_STATE.q_nb` freezes the adopted WXYZ Hamilton Body-to-ENU
attitude. After that boundary, the mission attitude is propagated entirely in software. The
hardware quaternion remains a diagnostic reference and is never used as the authoritative
post-START replay attitude.

The Replay GUI always uses **Corrected IMU** and does not present an input-source selector. The
algorithm API and CLI retain two explicit, non-interchangeable sources for validation and
advanced workflows:

- **Corrected IMU**: trapezoidal subintervals, two-sample coning/sculling, quaternion propagation,
  Body-to-ENU specific force, gravity removal, velocity, and trapezoidal position.
- **Recorded Inertial Increment**: uses the recorded coning/sculling output and re-runs the same
  quaternion/velocity/position mechanization.

KF6 uses state order `[pE,pN,pU,vE,vN,vU]`, the order in current `navigation_kf.c`. It restores
P0, process acceleration standard deviations, NIS thresholds, and maximum soft-R scale; then it
uses the independent mechanization prediction plus logged GNSS and barometer measurements. It
exports full P, innovations, effective R, NIS, accepted/soft/rejected results, and reacquisition
diagnostics.

Every result is labeled:

- **Recorded** — values actually logged by the flight controller;
- **Recomputed** — replay using the recorded configuration;
- **Offline** — replay using the offline plugin's declared defaults;
- **What-if** — replay with explicitly modified parameters.

Separately, fidelity is `EXACT`, `APPROXIMATE`, or `UNAVAILABLE`. Missing required input never
causes a hidden source switch. Build mismatch, data gaps, missing measurement-application timing,
or decimation lower fidelity with an explicit warning. Input gaps are segmented without silent
interpolation. `EXACT` additionally requires clean source integrity and a matching immutable
host-C Golden reference. See [Replay.md](Replay.md) and
[Architecture.md](Architecture.md).

## Command line

After installation:

```powershell
sslog inspect D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder
sslog replay D:\logs\flight.BIN --decoder D:\logs\flight.ssdecoder --algorithm silverstar.algorithm.pure_ins --mode offline --source corrected_imu
sslog replay D:\logs\flight.BIN --auto-find --algorithm kf6 --parameter process_accel_std_u=2.5
sslog export D:\logs\flight.BIN D:\exports --decoder D:\logs\flight.ssdecoder --language en_US --theme dark
sslog gui D:\logs\flight.BIN --auto-find
```

`inspect` also prints package/generation identity, semantic context, calibration, firmware
components, and independent algorithm availability. Algorithm IDs are resolved dynamically from
the offline registry. CSV export is one file per channel so every sensor keeps its own timing.

## Tests

```powershell
python -m pytest -q
```

The repository fixtures are generated in memory and are explicitly named **SYNTHETIC**. Tests
cover all current payload layouts, unknown records/versions, CRC recovery, sync recovery,
truncated tails, sequence gaps, stationary Pure INS through both input chains, KF6 covariance and
NIS rejection, calibration/alignment/deploy summaries, replay-result coexistence, active-source
readiness and return-to-Recorded behavior, Flight/State Estimation read-only source displays,
dual Recorded navigation layers, unique plot colors, camera preservation, relative-origin 3D
rendering, rocket PNG/GIF export, the 30 fps combined GIF, partial export failures, project
immutability, and a headless five-page GUI smoke test. Dedicated decoder-profile tests cover ZIP
limits and attacks, checksum/schema validation, the complete scalar whitelist, payload-size
contracts, two IMU instances, canonical channels, same-physical-device capability linkage,
Descriptor hash matching, atomic coordinator opening, mandatory/identity NONE calibration,
including nonzero start sequence and configured-SixFace independence, zero-copy immutable
aliases, online/no-fix GNSS with zero measurements, multiple Alignment/INITIAL_STATE authority,
candidate-validated bounded recovery, per-channel timestamp sorting, CLI integration,
audit-manifest provenance, cache reuse, bounded parent discovery, and trusted `.ssplugin` factory
allowlisting. Package 1.0/1.1 and unsigned layouts are explicit rejection cases.

No real flight log is included. Phase 2 requires frozen real logs and host-C golden vectors from
the matching flight-controller build; this is tracked in [TARGETS.md](TARGETS.md).

## Windows packaging

Install the `packaging` extra and run:

```powershell
.\打包.bat
```

The PyInstaller output appears under `dist\SilverStar_FLP`. Run the test suite before packaging.
PyInstaller preparation is included, but a distributable build is not committed to source
control.

## Design boundaries

Users manage two log-decoding layers:

- trusted Log Container Plugin code for one incompatible container generation;
- one exact data-only `.ssdecoder` 1.2 per generated project.

Internally, Algorithm Plugins remain the separate replay/estimation extension point. A
`.ssdecoder` may describe recorded algorithm streams, but field layout alone cannot implement or
reproduce a new navigation algorithm.

Pure INS and KF6 are the only first-release Algorithm Plugins. Deploy and landing replay are Core
flight-analysis services. ESKF15 and ESKF24 are future targets only; their interface can be added
without changing the standard navigation pages, but neither is implemented now.

## Source of truth and remaining risk

Record/semantic authority comes from the exact matched `.ssdecoder`; algorithm implementation is
still audited host code. The external SS0014 compatibility sample proves current 0.0.10 package
matching, corruption exclusion/recovery, semantic adaptation, GUI degradation, and audit export
when its opt-in gate is run. It is not a numerical host-C Golden. Pure INS and KF_6 therefore
remain `APPROXIMATE` for firmware 0.0.10 and retain build identity `SILV0008`. Never claim
`EXACT` until the matching immutable real-log and host golden gate passes.

## Display quality and workspace maintenance

Arrays now inherit semantic axis labels, and GUI/PNG/GIF share event-point drawing geometry that
keeps true data gaps visible. Overview distinguishes sequence-gap segments, missing IDs, and
recorded queue counters. See [Display_DataQuality.md](Display_DataQuality.md).

Run `python tools/clean_workspace.py --dry-run` to inspect bounded cleanup candidates, then
`--apply` to remove only verified generated files. See [Workspace_Cleanup.md](Workspace_Cleanup.md).

## GNSS 水平与竖直一致性图的读法（当前 revision 3）

水平图呈阶梯、竖直图呈连续折线，首先反映的是**统计口径和输出节奏不同**。
不能仅凭外观判断算法正常，也不能把两图的数值直接当作同一窗口下的误差比较。
以下说明对应当前 revision-3 窗口证据与 FLP 的离线竖直诊断。

### 水平的两个图分别是什么

| 图 | 显示的量 | 单位与含义 |
|---|---|---|
| 水平上图 | `NAV_QUALITY.closure_norm_m` | 米；GNSS 水平位置变化减去同一窗口内水平速度积分后，EN 闭合向量的模长 |
| 水平下图 | `NAV_QUALITY.variance_scale` | 无量纲；窗口对水平位置测量**方差**的倍率，不是第二条误差，也不是另一个方向的闭合量 |

水平闭合量可写为：

```text
closure_EN = p_EN(t_end) - p_EN(t_start) - integral(v_EN, t_start, t_end)
c = norm(closure_EN)
```

它检查接收机的位置变化与速度积分是否自洽，**不是相对真实位置的绝对导航误差**。

当前窗口方案为两个 10 秒窗口序列，起点错开 5 秒。例如，序列 A 为
`[0,10]、[10,20]、…`，序列 B 为 `[5,15]、[15,25]、…`；这里的 0 只是监测起点示意，
不是所有日志的 START 或 GPS 时间零点。两个序列合起来每 5 秒完成一个窗口。
图上两个上下子图并不分别代表 A、B：上图画最近完成窗口的闭合量，下图画其方差倍率。

窗口完成后才发布新的统计结果；两次完成之间保留上一份可用结果。
因此即使 `NAV_QUALITY` 约以 25 Hz（约 40 ms 一条）记录，也不代表每 40 ms 计算出
一个新的 10 秒窗口结果。**25 Hz 是记录节奏，5 秒一次（约 0.2 Hz）是此窗口方案的统计更新节奏。**
Recorded 水平图使用向后保持的阶梯绘法，表现日志中真实保持的值；它没有漏做区间计算。
首次完成窗口前没有有效闭合证据，图中的空白不能解释成误差为零。

下图的当前窗口倍率关系为：

```text
k_R = min(k_max, max(1, (c / H)^2))
```

其中 `H` 为该日志的闭合误差加权门限，`k_max` 为配置的倍率上限。
000062 的 `H = 10 m`、`k_max = 4`。闭合量不超过 10 m 时，该倍率保持 1；
超过门限后才增大，所以倍率图常比闭合图更长时间保持水平。
这是**方差/协方差 R 的倍率**，不是标准差的倍率；对应标准差倍率为 `sqrt(k_R)`。
这项只表示窗口贡献的倍率，不应当作包含接收机质量、卫星数、NIS 等其他调权后的总倍率，
也不应把它当作融合拒绝状态。无效或过期窗口应结合有效性标记解读，不能只看倍率是否为 1。

### 竖直图为何逐样本变化

当前竖直图由 FLP 使用 `GNSS_NATIVE` 和记录的有效 GNSS 原点，在离线环境中独立计算：

```text
vertical_residual(t) = U(t) - U(t_ref) - integral(v_U, t_ref, t)
```

每个可用原生样本都更新积分及残差；000062 的接收间隔约为 40 ms，FLP 用普通折线连接
这些实际样本。因此它看起来是密集曲线。**当前这项竖直诊断没有采用水平相同的
10 秒窗口、5 秒错开方案**，而是从当前参考点累计，直到连续性条件触发参考重置。

无效垂直速度、来源或 replay epoch 改变、序列不连续、时间倒退，以及超过配置最大间隔
（000062 为 120 ms）等情况会重置离线积分链和局部参考。
竖直图的灰色竖线表示这种**离线局部参考重置**，不等同于固件 GNSS 断流或融合拒绝事件。

水平窗口内部以原生 GNSS epoch 积分，横轴使用记录的 MCU `evaluation_us`；
竖直诊断使用可信样本时间，否则使用接收时间。二者除了窗口长度不同，时间选择也不同。
所以不能直接横比两图数值大小、把竖直累计漂移与水平最近 10 秒闭合量当作同一统计量，
或据此推断某一轴精度更高。

### 000062 的原始记录核对实例

已有 000062 日志含 3390 条 revision-3 `NAV_QUALITY`，其中 3140 条标记为有效证据，
但只有 **26 个不同的完成窗口**。26 个窗口的 `window_end_us - window_start_us`
全部为 `10,000,000 us`，相邻完成窗口结束时间全部相差 `5,000,000 us`，窗口索引 0、1 交替。
重复记录保持的是同一窗口结果，不是 3390 份独立完成窗口。

| 从 START 起的记录时间 | 水平闭合量 | 窗口方差倍率 |
|---|---:|---:|
| 75.070 s | 11.70554 m | 1.370197 |
| 80.072 s | 15.71896 m | 2.470857 |
| 85.072 s | 8.223319 m | 1.000000 |

这些窗口字段、闭合量和倍率已与 exact `.ssdecoder` 定义及原始记录载荷核对。
日志 SHA256 为 `7ba89a60127a027adc28623cfb4b5e4898c72b99fd0374d58d59154633c89218`；
decoder SHA256 为 `47394c9d1b27f76e074ce43b324dd218e3448c6a5465628fdce2c744e3afe0e5`。
以上是已有日志的读图实证，不是新硬件试验、位置真值验证或飞行安全结论。

### Recorded 与离线诊断的边界

Recorded 水平图读取飞控记录的 revision-3 `NAV_QUALITY`，不以接收机原生数据重新计算
并替换这些值。选择 Recomputed/What-if 时，水平图只使用该所选运行提供的 completed
`window_evidence` 和明确的 MCU 时间映射，按完成窗口点显示；没有证据时显示不可用，
不借用 Recorded 的结果。竖直图则是独立的接收机原生离线诊断，不是记录的固件加权或拒绝决策，
也不参与固件/KF6/NIS 的计算。

解读时保留水平阶梯和真实数据空白；**不要用插值或平滑把保持值美化成连续曲线**，
否则会掩盖实际更新时刻并制造不存在的中间统计结果。若需要水平和竖直使用同一窗口口径，
应另行定义诊断指标，不能靠更改绘图方式实现。

实现依据：[水平记录显示模型](../../apps/FLP/src/silverstar_flp/analysis/gnss_integrity_display.py)、
[GNSS 页面绘图](../../apps/FLP/src/silverstar_flp/ui/gnss_integrity.py)、
[离线竖直计算](../../apps/FLP/src/silverstar_flp/analysis/gnss_vertical_consistency.py)。
