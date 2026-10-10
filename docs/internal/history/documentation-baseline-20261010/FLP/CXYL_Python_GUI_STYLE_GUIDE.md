# CXYL Python GUI Style Guide

> Recommended use: copy this document into a project as `docs/GUI_STYLE_GUIDE.md`, or incorporate the normative sections into the repository-level `AGENTS.md`.
>
> Scope: PySide6/Python desktop engineering and analysis tools. This guide is intended for CXYL projects, but it is deliberately domain-agnostic and may be reused by unrelated Python GUI projects.
>
> The purpose of this guide is not to force every application to have identical pages. It defines a reusable visual language, interaction model, theme model, i18n model, plotting model, 3D model, and code architecture. Domain-specific examples such as flight logs, estimators, rockets, and telemetry are examples only, not requirements.

---

## 0. Applicability and naming

This document is a **general GUI standard**, not a SilverStar-only or avionics-only standard.

It may be used for:

- CXYL engineering tools;
- data-analysis applications;
- hardware/embedded development utilities;
- log viewers and processors;
- robotics or aerospace tools;
- laboratory/test software;
- generic desktop utilities;
- other PySide6/Python applications.

Domain-specific examples in this guide—such as `SilverStar_FLP`, INS/KF data, ENU coordinates, rockets, deploy events, or flight replay—are **examples of applying the standard**, not mandatory concepts.

When this guide is copied into a non-CXYL project:

- keep the structural, theming, i18n, plotting, interaction, testing, and architecture rules;
- replace product names and domain terminology with the target project's terminology;
- do not introduce CXYL branding unless the product is actually part of CXYL.

The recommended repository-level rule is simply:

```markdown
All PySide6 UI work must follow `docs/GUI_STYLE_GUIDE.md`.
```

## 1. Design goals

All CXYL and general-purpose Python GUIs should prioritize:

1. **Engineering clarity over decoration**
   - Dense enough to be useful.
   - No unnecessary cards, oversized whitespace, or dashboard gimmicks.
   - Important state should be visible without opening many dialogs.

2. **One visual family**
   - Deep-blue brand bars.
   - Blue left navigation.
   - White/light-gray content surfaces in Light mode.
   - Dark navy/slate content surfaces in Dark mode.
   - Consistent typography, spacing, tab appearance, buttons, tables, and plots.

3. **Stable information hierarchy**
   - Brand and version at top.
   - Primary workspace navigation at left.
   - Main work area in the center.
   - Task state/progress at bottom.
   - File/session details belong in the content or status area, not in the application title.

4. **Full bilingual operation**
   - Simplified Chinese and English.
   - Internal IDs stay stable and language-neutral.
   - User-visible text is translated.
   - Technical abbreviations such as IMU, INS, KF, GNSS, ENU, NIS, CRC, WXYZ may remain as abbreviations.

5. **Theme completeness**
   - Switching Light/Dark must affect Qt widgets, menus, tabs, tables, 2D plots, OpenGL views, Matplotlib exports, and GIF exports.
   - A “dark shell with white 3D canvas” is considered a bug.

6. **Data and algorithms remain independent of the GUI**
   - UI code must not contain estimator mathematics, binary-protocol decoding, or navigation algorithms.
   - GUI consumes datasets, analysis results, and stable metadata.

---

## 2. Application identity and version

### 2.1 Window title

The OS window title must be a stable product name, regardless of the application's domain.

Example:

```text
SilverStar_FLP
```

Do **not** change the window title when a file is loaded.

On Windows versions that support DWM caption colors, the native caption should use the same
brand-blue family as the menu/header shell, with high-contrast light title text. Failure of the
platform API must degrade safely to the native system caption; do not replace the native frame
with a fragile custom title bar solely for color.

Avoid:

```text
SilverStar_FLP — SS0007.BIN
SilverStar_FLP — C:\Logs\SS0007.BIN
```

The loaded file belongs in an Overview / Project / Status area.

### 2.2 Header identity

The top brand bar must contain:

```text
<Localized Product Display Name>    <vVersion>    <Developer Credit>
```

Example:

```text
简体中文：SilverStar 飞行日志解析器    v0.0.4    辰星引力开发
English:  SilverStar Flight Log Parser    v0.0.4    By CXYL
```

Recommended implementation:

- `headerTitle`
- `headerVersion`
- `headerCredit`

Keep the brand word itself stable (for example, `SilverStar`), but localize the descriptive
product role when that improves clarity. The stable technical product ID may remain in the OS
window title, package metadata, and machine-facing identifiers.

### 2.3 Single version source

Keep one authoritative version source, e.g.:

```python
PRODUCT_NAME = "SilverStar_FLP"
__version__ = "0.0.4"
```

Packaging metadata, About text, installer metadata, and header display should derive from the same value when practical.

Do not allow:

```text
GUI: 0.0.4
pyproject: 0.1.0.dev0
exe metadata: 0.0.1
```

---

## 3. Main window composition

Recommended structure:

```text
┌──────────────────────────────────────────────────────────────┐
│ Menu Bar                                                     │
├──────────────────────────────────────────────────────────────┤
│ BLUE BRAND HEADER                                            │
│ Display Name  vVersion  Credit        Language ▼  Theme ▼     │
├───────────────┬──────────────────────────────────────────────┤
│ BLUE LEFT     │                                              │
│ NAVIGATION    │              MAIN WORKSPACE                  │
│               │                                              │
│ Overview      │                                              │
│ Replay        │                                              │
│ Flight        │                                              │
│ ...           │                                              │
├───────────────┴──────────────────────────────────────────────┤
│ Status / task message                         Progress       │
└──────────────────────────────────────────────────────────────┘
```

Optional:
- Do not overload the brand header with many task buttons.

For applications with an engineering document/project format, the recommended visible order is:

```text
File menu: New Project, Open Project, Save Project, Save Project As,
           Import Log / Decoder, Export, Exit
```

Use separators after Save Project As and Export. Avoid a duplicate toolbar when all required
project actions are available from this menu with conventional shortcuts.

In Simplified Chinese CXYL engineering applications, translate the document concept `Project`
as `工程`, for example
`保存工程` and `打开工程`; use `项目` only when it actually means a managed initiative rather
than an application document.

---

## 4. Brand header

### 4.1 Light mode

Recommended tokens:

```text
Header background:      #123A78
Header hover/control:   #1C4F94
Selection/accent:       #2F6FED
Header border:          #315A94
Title text:             #FFFFFF
Secondary header text:  #DCEAFF
```

### 4.2 Dark mode

Recommended tokens:

```text
Header background:      #0B2447
Header hover/control:   #163B6C
Selection/accent:       #3B82F6
Header border:          #234A76
Title text:             #F8FAFC
Secondary header text:  #C8D8EC / #E5E7EB
```

### 4.3 Header controls

Place language and theme controls on the right.

Recommended:

```text
界面语言 / Language:  [简体中文 ▼]
主题 / Theme:         [浅色 ▼]
```

Use the same `StandardComboBox` family for both.

Header combos and their popup lists must use a deep-blue background with white/light text.
Hover and selected rows use the theme accent blue with white text. Do not allow the popup to
fall back to a white background with inherited white text.

Prefer a theme dropdown over a single toggle button when the application family is expected to grow to:

```text
Light
Dark
System
```

Even if only Light/Dark exist today, the combo pattern is consistent and explicit.

---

## 5. Left navigation

Navigation should be a fixed-width deep-blue vertical list.

Typical width:

```text
150–190 px
```

Rules:

- Background uses the same blue family as the header.
- White/light text.
- Hover uses a slightly lighter blue.
- Selected item uses the same application accent blue as the header combo hover/selection.
- Selected navigation text remains white; do not use a nearly white pale-blue selection fill.
- No native gray selection.
- Vertical scrollbar appears only when needed.
- Horizontal scrollbar disabled.

Suggested Light colors:

```text
normal:   #123A78
hover:    #1C4F94
selected: #2F6FED
```

Suggested Dark colors:

```text
normal:   #0B2447
hover:    #163B6C
selected: #3B82F6
```

Navigation should contain **workspaces**, not every minor subview. Subviews belong in tabs within the page.

---

## 6. Tabs: mandatory custom style

Never leave `QTabWidget/QTabBar` on platform-native gray styling.

This is especially important on Windows, where native tabs can become:

```text
gray background + dark text
```

and look disconnected from the CXYL visual family.

All major tabs should use:

- Deep-blue inactive tab background.
- White text.
- Brighter-blue selected tab.
- Medium-blue hover.
- Clear border relationship to the content pane.

Recommended behavior:

```text
Inactive: deep navy/blue
Hover:    medium blue
Selected: bright accent blue
Text:     white
Disabled: muted slate-blue
```

Apply this globally to:

- Flight tabs
- State Estimation tabs
- Data Explorer tabs
- Any future workspace-local tab bar

Do not style each page separately if a global theme rule can do it.

---

## 7. Content backgrounds and cards

### 7.1 Light mode

Recommended:

```text
Application background: #F4F6FA
Card/GroupBox:           #FFFFFF
Primary text:            #172033 / #111827
Muted text:              #64748B
Border:                  #D7DFEB / #AEB8C8
```

### 7.2 Dark mode

Recommended:

```text
Application background: #0F172A
Card/GroupBox:           #111827
Input/table surface:     #182235
Primary text:            #E5E7EB
Muted text:              #94A3B8
Border:                  #334155 / #475569
```

### 7.3 GroupBox

GroupBoxes should:

- Have restrained rounded corners.
- Use the brand blue for titles in Light mode.
- Use light blue for titles in Dark mode.
- Support status properties such as:
  - `success`
  - `warning`
  - `error`

Do not use saturated filled cards for normal content.

---

## 8. Status colors

Use color as a secondary signal, not the only signal.

Recommended meanings:

```text
Success: green
Warning: amber
Error:   red
Info:    blue
```

Status widgets must remain readable in both themes.

Example custom property:

```python
widget.setProperty("statusLevel", "warning")
```

Re-polish after changing dynamic properties.

Always include textual status:

```text
完成 / Ready
警告 / Warning
失败 / Failed
```

---

## 9. Buttons

### 9.1 Normal buttons

Normal controls:
- Neutral surface.
- Visible border.
- Strong text contrast.

### 9.2 Primary button

Use a single strong accent style:

```text
Light: #2F6FED
Dark:  #3B82F6
Text:  white
```

Examples:
- Run Replay
- Apply
- Export
- Start

Avoid having five different “primary” colors on one page.

### 9.3 Dangerous/destructive actions

Only destructive operations should use destructive styling.

Do not use red for normal “Stop” or navigation unless it is truly destructive or safety-critical.

---

## 10. Tables

Tables should:

- Match the theme.
- Use custom headers.
- Never use native gray/black combinations.
- Keep technical data compact.
- Use row selection where useful.
- Avoid editing unless explicitly intended.

Light:

```text
Body:   white
Header: #E7ECF4
Text:   dark
Select: accent blue + white text
```

Dark:

```text
Body:   #182235
Header: #1E293B
Text:   #E5E7EB
Select: #3B82F6 + white text
```

For large logs:
- Downsample only for display.
- Clearly state that export preserves full samples.
- Do not mutate the underlying dataset.

---

## 11. Combo boxes and dropdowns

Use a shared `StandardComboBox`.

Requirements:

- Popup palette must be explicitly themed.
- Popup selected text must remain readable.
- Same min-height and padding across the app.
- Language/theme/source selectors should use the same visual family.
- Header combo fields and popups use deep blue + white text; hover/selection uses accent blue.
- Give header popup views a stable object name such as `headerComboPopup` when QSS inheritance
  cannot reliably distinguish them from content-area combo boxes.

Do not rely on OS-native popup colors.

---

## 12. Scroll areas

Use `QScrollArea` when a page can legitimately grow beyond a typical 1366×768 or 1280×800 display.

Rules:
- Horizontal scrolling should normally be disabled for normal analysis pages.
- Vertical scrolling as needed.
- Do not shrink fonts or hide engineering detail simply to avoid vertical scrolling.
- Overview pages may scroll; plots should normally occupy expandable regions.

---

## 13. Plot design

### 13.1 General

2D engineering plots should use:
- Real timestamps.
- Clear unit labels.
- Grid with low alpha.
- Theme-aware background/foreground.
- Legend.
- No decorative gradients.

### 13.2 Color reuse is not allowed within one plot

A visible plot must not contain multiple different traces with the same color unless they are intentionally the same logical signal.

Bad:

```text
Recorded E = blue
Recorded N = green
Recorded U = orange
Recomputed E = blue again
Recomputed N = green again
...
```

This becomes ambiguous.

Instead:
- Allocate colors per visible trace.
- Use a sufficiently large palette.
- Also use line style (solid/dashed) to encode source/provenance.
- Do not depend on line style alone.

Recommended model:

```text
TraceColorAllocator
```

The allocator is reset once per plot refresh, not once per series.

Each plotted curve requests the next distinct color.

For semantically repeated groups, stable mappings may be used, but all simultaneously visible curves must remain distinguishable.

### 13.3 Suggested source styling

Example:

```text
Active/primary source: thicker solid lines
Recorded reference:    thinner dashed lines
```

Colors should still differ.

### 13.4 Legends

Legends must be localized.

Good:

```text
飞控记录 · E
离线复算 · N
```

or:

```text
Recorded · E
Recomputed · N
```

Do not mix:

```text
Recorded 东向
```

unless deliberately defined.

---

### 13.5 Chart reset

Every page that contains interactive 2D charts must expose one localized page-level reset action.
The action resets every chart on that page to its data-driven automatic X/Y range after wheel
zooming or panning. If the page contains draggable chart markers, cursors, or annotations, their
documented default positions must be restored by the same action. A 3D `Reset View` remains a
separate camera operation and does not replace the 2D chart reset.

## 14. Technical abbreviations in plots

The following can remain untranslated:

```text
E N U
X Y Z
Xb Yb Zb
W X Y Z
IMU
INS
KF
KF_6
GNSS
NIS
CRC
SSLOG0
```

Human-readable nouns should be localized:

```text
Velocity / 速度
Position / 位置
Acceleration / 加速度
Angular Rate / 角速度
Trajectory / 轨迹
Attitude / 姿态
```

---

## 15. 3D attitude view

### 15.1 Do not use only axis lines as the vehicle

A flight vehicle should be represented by a simple recognizable 3D model.

For a vehicle-oriented application, use a recognizable lightweight mesh. For example, a rocket can use:

```text
square base + nose vertex
triangular side faces + base faces
```

Example proportions:

```text
base half-width: ~0.35
body/nose length: ~2.2
```

A `GLMeshItem` with per-face colors is suitable.

The purpose is orientation recognition, not CAD accuracy. For non-vehicle applications, replace the vehicle mesh with the domain's natural 3D object or omit it entirely.

### 15.2 Body frame

Body axes may remain as a secondary reference:

```text
Xb
Yb
Zb
```

but the mesh should carry the primary visual orientation.

### 15.3 World frame

Show ENU clearly:

```text
E
N
U
```

Use:
- subtle world axes,
- labels,
- or a compact legend.

Avoid cluttering the center with overlapping text.

### 15.4 Camera behavior

Playback must not constantly overwrite the user's camera.

Critical rule:

> Camera fitting is allowed when a dataset/source is loaded or when Reset View is pressed. It must not be executed on every playback frame.

Otherwise wheel zoom appears broken.

Recommended controls:

```text
Reset View
Lock/Unlock Camera
```

If camera is locked:
- mouse drag rotation/pan may be blocked,
- wheel zoom should still work.

---

## 16. 3D trajectory view

### 16.1 Mission origin

For trajectory-style applications, the displayed path should normally be expressed relative to a meaningful session/start origin:

```text
display_position = navigation_position - position_at_START
```

Thus:

```text
START / session origin = (0, 0, 0)
```

Do not place a large `START` text label over the origin if the origin itself already communicates the start.

This coordinate shift is **presentation-only**. Do not modify the recorded dataset.

### 16.2 Event markers

Important event markers should prefer compact point markers over large floating 3D text. For example, parachute deploy can be shown as a point marker.

Recommended:
- orange point,
- legend or side explanation.

In an OpenGL trajectory view, event/current markers should use world-space sizing. Derive the
marker diameter from the cached characteristic visible E/N/U trajectory extent, with a minimum
extent guard, so the marker scales with the trajectory instead of remaining a fixed-size
screen-space circle.

Deploy and Landing should use one generic tiny opaque `GLMeshItem` geometry, such as an octahedron,
when point sprites produce a soft halo or disappear on a Light canvas. Use orange for Deploy and
purple for Landing, alpha 1.0, and the same trajectory-extent-derived world-diameter policy.

Avoid floating `DEPLOY` text directly in dense 3D geometry when it causes occlusion.

### 16.3 Phase segmentation

When a trajectory has meaningful phases, the phases should use visibly different colors. For example, pre-deploy and post-deploy flight phases should be distinguishable.

Example semantic roles:

```text
Pre-deploy
Post-deploy
Deploy point
Current position
Landing point
```

For flight replay, use red for the pre-deploy path and current point, blue for the post-deploy
path and current point, orange for the single Deploy point, and a distinct semantic color for
Landing. The current-point color changes at the Deploy timestamp boundary.

Before Landing, show Current and hide Landing. At and after Landing, hide Current and show the
opaque Landing mesh. Resolve an event position by interpolation when the series covers its
timestamp; otherwise allow the nearest valid sample within five typical sample intervals or at
least 100 ms. This scheduling tolerance is presentation logic, not an invented algorithm sample.

### 16.4 Camera

As with attitude:
- fit initially,
- preserve user zoom during playback,
- provide Reset View.

Precompute and cache mission-relative trajectory bounds separately for every selectable source,
including distinct Recorded Pure INS and Recorded estimator layers. Bounds contain minimum,
maximum, center, span, maximum span, and a bounding radius. Fit only on dataset/source/result
changes and explicit Reset View. Use the cached center and bounding radius with the actual camera
FOV and viewport aspect ratio, plus approximately 10–20% margin. Never rescan the full trajectory
or refit the camera during slider/timer refresh.

---

## 17. 3D theme

OpenGL widgets must be themed independently of Qt QSS.

Update:
- GL background
- grid
- world labels
- mesh face colors
- mesh edges
- markers
- text

Light must not remain black by accident.
Dark must not remain white by accident.

Use theme tokens, not duplicated hard-coded values spread across page classes.

---

## 18. GIF and static 3D export

Interactive 3D and exported 3D should use the same semantic design.

Recommended flight replay GIF:

```text
left:  rocket attitude
right: 3D trajectory
```

For high-rate logs:
- sample frames by mission time,
- do not interpolate unnecessary visual frames,
- 30–60 frames is usually sufficient.

The exported trajectory should:
- start at visual origin,
- end at Landing when Landing is present,
- segment pre/post deploy,
- mark Deploy and Landing with the same semantic opaque meshes as the GUI,
- hide Current on the final Landing frame,
- label ENU axes,
- honor Light/Dark,
- honor export language.

Static trajectory PNG remains useful even when a GIF exists.

---

## 19. Language architecture

### 19.1 Internal vs display values

Internal identifiers stay stable:

```text
firmware_build_differs_from_reimplementation
navigation.position_enu
silverstar.algorithm.kf6
EXACT
```

The UI must not directly render those values.

Instead:

```text
stable code -> translation key -> display text
```

### 19.2 Replay fidelity

Raw enum values:

```text
EXACT
APPROXIMATE
UNAVAILABLE
```

must have localized display labels.

Example:

```text
EXACT        -> 完整复现 / Exact
APPROXIMATE  -> 近似复现 / Approximate
UNAVAILABLE  -> 不可复算 / Unavailable
```

Keep the enum itself stable for JSON, tests, and logic.

### 19.3 Warning codes

Algorithm plugins should return stable warning codes, not user-facing English sentences.

Example:

```text
firmware_build_differs_from_reimplementation
source_log_has_integrity_or_sequence_gaps
measurement_application_time_inferred
```

The GUI translates:

```text
replay.warning.<code>
```

Unknown warning codes should use a localized fallback and optionally expose the raw code in a tooltip.

### 19.4 Parameter labels

`ParameterSpec` should expose a translation key.

The GUI should use that key rather than directly displaying `parameter_id`.

Units remain technical.

Tooltips may show the stable parameter ID for advanced users.

---

## 20. Theme and language settings

Persist:
- interface language
- theme
- window geometry if desired
- last directories
- user display preferences

Use `QSettings` or a project-specific settings service.

Changing language/theme should update the UI immediately when practical.

---

## 21. Analysis-source selection pattern

Applications that support multiple recorded/recomputed/derived result sets should use a dedicated, explicit **Analysis Data Source** panel.

Recommended:

```text
后续分析数据源 / Analysis Data Source
[ 飞控记录 / Recorded Data ▼ ]
```

Do not rely on one-way buttons such as:

```text
Use for Analysis
```

without a clear way to return to recorded data.

### 21.1 Recorded source

Recorded data is always selectable.

A recorded navigation dataset may contain multiple solution layers:

```text
Pure INS
Final estimator (KF_6 / ESKF / ...)
```

Do not hide Pure INS merely because a final estimator exists.

### 21.2 Recomputed source

A recomputed source is selectable only after its required replay chain has completed successfully.

For the current Pure INS + KF_6 stack, a complete recomputed dataset may require:

```text
Pure INS replay complete
KF_6 replay complete
```

Only then enable:

```text
Recomputed Data
```

A failed or still-running replay must never appear as a valid analysis source.

### 21.3 What-if sources

What-if results may be exposed as separate complete analysis bundles if the required chain is complete.

Do not let partial algorithm outputs silently masquerade as a complete navigation dataset.

---

## 22. Recorded solution layers

A “Recorded Data” analysis source does not mean only the final estimator.

Where the log contains both:

```text
Pure INS
KF_6 / ESKF final estimate
```

Flight/navigation views should allow both to be visible and comparable.

Typical display:

```text
Pure INS
Final Estimate (KF_6)
GNSS / Barometer reference as applicable
```

Do not implement generic recorded `navigation.position_enu` by always resolving to KF first and hiding Pure INS from the user.

---

## 23. Replay input convention

Normal full navigation replay should use:

```text
INITIAL_STATE
+
IMU_CORRECTED
+
sensor measurements/config
```

Do not expose a normal-user input selector between:

```text
Corrected IMU
Recorded Inertial Increment
```

unless a specialist diagnostic workflow explicitly requires it.

For current CXYL-style tools:
- use corrected IMU as the normal replay input,
- rebuild inertial increments internally,
- keep recorded increments for validation/data exploration if useful.

Normal mission Replay uses one centralized boundary object. Its start is mission START; its end is
the first valid Landing event at or after START, or the active input/source end when Landing is
absent. Do not feed post-Landing IMU or measurements into normal INS/KF/ESKF replay, and do not
invent a synthetic sample exactly at Landing. The last discrete solution may legitimately be a few
milliseconds early. Keep post-Landing raw records available in the immutable dataset, Data
Explorer, and raw exports. Flight plots, the 3D slider, static trajectory export, and replay GIF use
the same boundary.

This also keeps the interface compatible with future algorithms such as ESKF_15 / ESKF_24 that should not depend on a pre-recorded increment stream.

---

## 24. Page hierarchy

Use a small number of primary pages.

Example for a flight-log processor (domain-specific example only):

```text
Overview
Replay
Flight
State Estimation
Data Explorer
```

Use tabs inside pages for:
- Velocity
- Position
- Acceleration
- Angular Rate
- Attitude
- 3D Replay
- Covariance
- Innovation
- NIS
- Updates

Do not create a primary navigation item for every plot.

---

## 25. Overview page

Overview should prioritize direct engineering inspection.

Typical order:

1. file/mission summary
2. key metrics
3. calibration
4. initial alignment
5. event timeline

If the information fits, display calibration/alignment details directly rather than hiding them behind “Details” buttons.

If vertical space becomes insufficient, make the page scrollable.

---

## 26. Status bar and background tasks

Long operations must not block the GUI:

- log parsing
- replay
- large export
- GIF generation

Use:
- QThreadPool / QRunnable,
- or a consistent task manager.

Status bar:
- normal task message on left,
- progress bar on right,
- cancel action only while a task is active.

Do not show a permanent meaningless progress control.

---

## 27. Export design

Export UI should:
- use checkboxes,
- default valid items to selected,
- allow independent export language,
- isolate failures per item,
- keep the output directory field editable,
- list each failed item's localized name in the completion state and provide an in-dialog
  error-details control with item ID, exception type, and exception message,
- show an Open Export Manifest action after the manifest is written, including when individual
  products failed.

When any product fails, also attempt a dependency-free localized `Export_Failures_ZH.txt` or
`Export_Failures_EN.txt`. This fallback uses only standard text file I/O so a Manifest failure
cannot erase the diagnostic reason.

For SilverStar_FLP, the default output directory is `<project-directory>/Result_<log-stem>`. If no
saved/open project exists, use `<source-log-directory>/Result_<log-stem>`. Changing the field
affects only the current export request; never impose a fixed drive root.

Recommended export language:

```text
Follow UI
简体中文
English
```

Filename suffix:

```text
_ZH
_EN
```

Language controls:
- plot titles
- axes
- legends
- annotations
- human-readable reports
- GIF text

Stable JSON/CSV schema IDs may remain English where they are machine-facing.

Full covariance P is a metadata-driven text report, not a default multi-curve upper-triangle PNG.
Generate one localized keyframe TXT per selected estimator source and keep the raw upper-triangle
time-series CSV. Algorithm metadata supplies the covariance channel/storage, ordered state
symbols, physical units, file stem, and therefore NxN; do not hard-code KF_6's dimension. Report
START, PARACHUTE_DEPLOY, and LANDING, or analysis end when LANDING is absent. For every event choose
the last valid sample satisfying `P timestamp <= Event timestamp`; do not interpolate or use a
post-event sample. Include the event/P timestamps, non-negative difference, algorithm/provenance,
and full-precision reconstructed matrix. If START precedes the first full-P sample, use the
plugin-declared initial diagonal (KF_6: `INITIAL_STATE.p0_diagonal`) to construct diagonal P0;
otherwise, if no non-future P exists, state that explicitly rather than silently taking the first
future sample. No LaTeX or PDF dependency is needed.

Standard flight plots, trajectory PNG, and replay GIF follow the mission horizon. A generic plot
explicitly exported from Data Explorer retains that channel's complete time coverage; pre-START
samples appear at negative mission time instead of being rejected as an empty post-START series.
Batch Export writes every selected channel to CSV but does not mechanically mirror channels into
`Channel_*.png`. Its PNG set contains only defined engineering plots, including metadata-driven
per-state `sqrt(Pii)` and per-measurement Innovation, NIS, and `sqrt(R)` plots.

The Manifest records `generated`, `skipped`, and `failed`. A configured measurement source
with no valid update still produces explanatory standard plots. A source that configuration
metadata explicitly marks as not participating is omitted and recorded with
`measurement_not_configured`.

---

## 28. Plot/export consistency

Interactive plots and exported plots should share:
- semantic channel names
- units
- source labels
- phase colors
- theme meanings
- i18n labels

Avoid one independent plotting vocabulary for the GUI and another for export.

Use shared metadata such as:

```text
PlotDescriptor
ChannelDisplayMetadata
TraceStyle
ThemeTokens
```

---

## 29. Object-name conventions

Use stable object names for global QSS styling.

Recommended:

```text
centralRoot
headerBar
headerTitle
headerVersion
headerCredit
headerControlLabel
headerCombo
headerComboPopup
sidebar
navigation
mainMenuBar
mainToolBar
primaryButton
muted
warningLabel
```

Add shared names for tabs if required, but prefer styling `QTabBar` globally.

---

## 30. Recommended theme architecture

Do not scatter theme colors across page classes.

Preferred:

```text
ThemeTokens
  surface
  surface_alt
  text
  muted
  border
  brand
  brand_hover
  accent
  grid
  plot_background
  plot_foreground
  mesh_edge
  success
  warning
  error
```

Then:
- QSS is generated from tokens or kept in one theme module.
- PyQtGraph reads tokens.
- OpenGL reads tokens.
- Matplotlib export reads the corresponding export theme tokens.

---

## 31. Recommended UI code architecture

Example:

```text
src/<app>/
  app/
  core/
  i18n/
  ui/
    main_window.py
    theme.py
    widgets.py
    pages/
    components/
  plotting/
  export/
```

Rules:
- `main_window.py` coordinates pages and global state.
- `theme.py` owns appearance.
- `i18n` owns translations.
- pages own page interaction only.
- algorithms/data processing live outside `ui`.
- 3D reusable components may live in `ui/components/`.

---

## 32. Common anti-patterns

Do not:

1. Put loaded filename in the OS window title.
2. Maintain different version strings in multiple files.
3. Leave QTabWidget in native gray style.
4. Show English enum/warning codes directly in Chinese UI.
5. Reset OpenGL camera distance every animation frame.
6. Use only axes to represent a rocket when a simple mesh is possible.
7. Hide Pure INS because KF exists.
8. Give different traces the same color on the same plot.
9. Make “Use for Analysis” a one-way state with no explicit source selector.
10. Expose low-level replay input choices that should be implementation details.
11. Apply QSS but forget PyQtGraph/OpenGL/Matplotlib.
12. Translate machine schema IDs.
13. Put navigation algorithms in page classes.
14. Create many primary pages for individual charts.
15. Make dialogs the only way to see critical mission setup data.

---

## 33. Required visual smoke tests

For every release or major UI refactor verify:

### Light mode
- header blue
- native caption blue when supported
- header combo fields and popups readable without selecting text
- navigation blue
- selected navigation uses accent blue with white text
- tabs blue + white text
- content readable
- tables readable
- 2D plots readable
- 3D background light and readable

### Dark mode
- header/nav darker blue
- tabs blue + white text
- tables readable
- 2D plots dark
- 3D plots dark
- no white flash/canvas
- muted text still readable

### Chinese
- no avoidable English user-facing strings
- warning/fidelity/parameter labels translated

### English
- no avoidable Chinese user-facing strings

### 3D
- rocket mesh orientation obvious
- ENU clear
- wheel zoom works during playback
- camera does not reset every frame
- deploy marker remains visible on the Light canvas and does not occlude trajectory
- Landing is a visible opaque purple mesh on Light and Dark canvases
- Current disappears when Landing appears
- the complete mission trajectory fits initially without wheel adjustment
- start is visual origin

### Plots
- all simultaneously visible traces have distinguishable colors
- legends match sources/components
- units visible
- page-level chart reset restores automatic X/Y ranges after manual zoom/pan

---

## 34. Recommended automated tests

Add tests where practical for:

- stable window title
- version label
- localized header display name and developer credit
- file-menu and toolbar action order
- language switch
- theme switch
- tab stylesheet presence
- warning/fidelity translations
- analysis-source readiness
- recorded Pure INS visibility
- replay source unavailable before completion
- unique plot trace colors
- page-level chart reset after manual range changes
- OpenGL camera state not reset during playback refresh
- Light-mode deploy marker visibility
- Light-mode Landing mesh visibility and Current/Landing lifecycle
- source-specific trajectory-bounds caching without playback rescans
- FOV/aspect camera fitting for vertical, horizontal, long-thin, and short trajectories
- START-to-Landing Replay, plots, static PNG, and GIF with no-Landing fallback
- post-Landing raw-data preservation
- GUI/export rocket face-color consistency
- export language
- Light/Dark export
- ZH/EN filenames

GUI screenshots can supplement but should not replace structural tests.

---

## 35. AGENTS.md integration

A project may include this short requirement in `AGENTS.md`:

```markdown
## GUI standard

All PySide6 UI work must follow `docs/GUI_STYLE_GUIDE.md`.

Key invariants:
- stable product window title;
- version displayed in the blue brand header;
- deep-blue header and left navigation;
- language and theme dropdowns in the header;
- custom blue/white tab styling;
- full Light/Dark support including PyQtGraph/OpenGL/Matplotlib;
- stable-code-based i18n;
- no raw warning/fidelity enum strings in the UI;
- no duplicated curve colors within one plot;
- recognizable 3D vehicle model rather than axes-only attitude display;
- camera zoom must remain user-controlled during playback;
- data/algorithm logic must stay outside UI classes.
```

---

## 36. Final principle

The style should make CXYL applications feel related, while remaining reusable in unrelated Python projects without forcing CXYL branding or domain assumptions.

Reuse:
- visual tokens,
- header/navigation structure,
- controls,
- tabs,
- theme behavior,
- translation patterns,
- plotting conventions,
- 3D interaction conventions.

Do **not** force unrelated applications to copy the same page structure or domain workflow.

The standard is a common engineering UI language, not a rigid template.

## 37. Cadence-aware phase rendering

Event color transitions should share an exact or display-interpolated point between neighboring
continuous samples. Derive the continuity threshold from that channel; do not connect through
invalid samples or timestamp gaps. GUI, static export, and animation use one segment builder.
Nearest-event scheduling tolerance applies only outside sample coverage, never inside a data
hole. Keep segment geometry separate from immutable recorded/recomputed samples and expose
record-sequence gaps separately from each plotted channel's cadence.
