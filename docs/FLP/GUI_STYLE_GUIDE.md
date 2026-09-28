# SilverStar_FLP GUI style guide

The normative cross-project GUI specification is
[`CXYL_Python_GUI_STYLE_GUIDE.md`](CXYL_Python_GUI_STYLE_GUIDE.md). Read that document before
changing layout, navigation, controls, plots, Replay, 3D views, themes, or i18n. This file is the
short project entry point and does not duplicate the full CXYL guide.

SilverStar_FLP 0.0.4 fixes these project invariants:

- OS title is always `SilverStar_FLP`; the loaded filename appears only in status/details. On
  supported Windows versions, the native caption uses the current theme's brand blue.
- The header shows a localized descriptive name, `v0.0.4`, localized developer credit, and a
  compact current-project name whose tooltip contains the full absolute `.ssflp` path.
  Language/theme fields and popups are deep blue with white text and accent-blue hover rows.
- The File menu is New Project, Open Project, Save Project, Save Project As, Import Log / Decoder,
  Export, and Exit, with separators between the three groups. There is no duplicate toolbar.
  Import and export remain modal option dialogs.
- Export defaults to `<project-directory>/Result_<log-stem>` for a saved/open project; without one, use
  `<source-log-directory>/Result_<log-stem>`. The destination remains editable. After an
  export completes, the dialog exposes the generated localized export manifest directly. Failed
  items are listed by localized name with toggleable exception details; any failure also triggers
  a best-effort standard-I/O `Export_Failures_ZH|EN.txt`.
- Full P exports as one localized `<Algorithm>_Full_P_Keyframes_ZH|EN.txt`, driven by Algorithm
  Plugin metadata. It contains START, PARACHUTE_DEPLOY, and LANDING (or analysis-end fallback),
  using only the last valid non-future P without interpolation; START falls back to declared
  INITIAL_STATE P0 when it precedes the first full-P sample. Keep upper-triangle CSV; do not
  generate its generic multi-curve PNG.
- Batch Export writes all selected channels to CSV but creates PNGs only for standard engineering
  plots. Estimator state/measurement plots come from `EstimatorVisualizationSpec`; configured
  groups without valid updates receive explanatory plots, while explicitly unconfigured groups
  are recorded as skipped.
- Header, sidebar, menu, and unselected tabs are deep blue. Selected navigation uses the
  same accent blue as Header combo hover with white text. All tabs retain their global style.
- A combo popup opens downward, shows at most ten rows, and scrolls internally beyond ten.
- Every page containing 2D plots provides one Reset Charts action for all plots on that page.
- Replay has no input selector and always requests `corrected_imu`. Replay owns the only editable
  Analysis Data Source selector; Recorded is first, and only complete successful runs are listed.
  Flight and State Estimation display the source read-only.
- Recorded navigation identifies KF_6 or Pure INS; only the selected Analysis Source is drawn.
  Do not add automatic reference layers; explicit Compare remains separate.
- Attitude uses the shared GSHC-proportion and GSHC face-color rocket mesh plus the existing WXYZ
  Body-to-ENU quaternion helper. Trajectory coordinates are relative to mission START. Pre-deploy
  path/current are red, post-deploy path/current are blue, and Deploy is one small opaque orange
  world-space mesh. Landing is the same small opaque mesh geometry in purple. Both sizes follow the
  cached mission-trajectory extent; do not add outlines or floating event text. At Landing, hide
  Current and show Landing.
- Normal Replay, Flight plots, the 3D slider, trajectory PNG, and replay GIF use START-to-Landing as
  their mission horizon. Without a valid Landing event, use the active source's valid end. Raw logs,
  Data Explorer channels, raw CSV, and explicitly selected generic channel plots remain complete
  and immutable; samples before START use negative mission time in generic channel plots.
- Cache mission-relative `TrajectoryBounds` separately for Recorded Pure INS, Recorded KF_6, and
  every Recomputed/What-if result. Initial/Reset View fitting uses cached center and bounding radius
  with the OpenGL view's FOV and aspect ratio plus margin. Playback updates geometry only; it must
  not rescan bounds or reset orbit, pan, or zoom.
- Every user-visible Replay fidelity, warning, parameter, provenance, result, and source label must
  exist in both `zh_CN.json` and `en_US.json`; keep raw diagnostic IDs in tooltips.


- Semantic columns, record quality labels, and shared event drawing geometry follow
  [Display_DataQuality.md](Display_DataQuality.md). The existing diagnostics inner tab contains
  a per-gap table. Flight separately reports position timestamp gaps and the drawing threshold.
  Event-marker interpolation is permitted only across valid normal-cadence samples; the nearest
  scheduling fallback applies only outside channel coverage, never inside a data hole.

## Shell menus and plugin visibility

The header order is product, version, credit, current project, stretch, language, theme. Top-level menus are File, Plugins, Help. Plugins contains Manage, Install, Refresh; Help contains About. Plugin Manager is registry-driven and uses shared theme/i18n.


## Shared compact dialogs

About follows the FCCG information-dialog layout: information icon on the left, localized
product/version/description on the right, and one bottom-right OK button. New Project uses
name and output-directory rows before exact-pair import; cancellation creates no project file.
Plugin Manager uses a heading, descriptive notice, install/refresh action row and ID-first table.
The Install menu opens this manager. FLP retains its trusted-container installation rules;
FCCG declarative firmware component installation/removal is not an FLP runtime capability.
All three dialogs follow the active Light/Dark theme and interface language.


## KF6 comparison sampling

Flight position/velocity draw only the selected source. Shared TimeRange controls Flight and State Estimation plots;
min/max envelope preserves peaks and gaps. Export PNGs default to categorized 30 s pages; GIF
uses the full selected interval at constant speed capped to 30 s motion plus 1 s hold. See
[Field Log Replay](Field_Log_Replay.md).


## Touch scrolling

Ordinary scrolling content opts into the repository-local `TouchScroll_Enable` helper.
It registers Qt `QScroller.TouchGesture` on the viewport of a page, item view, or text
view. It does not convert touch into mouse drags, change wheel handlers, or change existing
ScrollPerPixel settings. Table headers are excluded; combo popups opt in separately.
Buttons, spinboxes, sliders, 2D plots and OpenGL views are not scrolling targets. Keep
plots, 3D views and time sliders outside page-scroll ancestors so their own drag semantics
remain authoritative. New ordinary scroll areas should opt in at construction.

Before field use, check finger swipes and taps on a CF-33: page scroll, nested table/list
scroll and selection, popup selection, button taps, spinboxes, mouse wheel/scrollbars,
stylus, plot pan/zoom, camera lock/rotation and replay time slider. Automated synthetic
Qt touch tests do not certify the physical Windows touch driver.


## NIS reference semantics and sparse preflight

MeasurementGroupSpec owns NIS description and reference-line metadata, shared by the State
Estimation page and exported PNGs. KF6 GNSS position/velocity show four independent groups:
Position EN, Position U, Velocity EN and Velocity U. EN groups use their 2D soft/hard
references; U groups use 1D references. Recorded values come directly from
GNSS_MEASUREMENT.group_nis and group results; recomputed KF6 exposes equivalent group channels.
The aggregate maxima remain available only as compatibility data. Barometer retains 1D gates.
Reference values come from the selected source's actual parameters. Do not infer group NIS
from an aggregate, or add KF6-specific branches to the page/export renderer.

A valid BOOT-to-START interval may contain only descriptors/configuration/events and snapshots.
Absence of preflight continuous sensor records is not corruption or a record-sequence gap.
Replay prerequisites still apply to the START/INITIAL_STATE mission interval; do not relax them
to accept missing mission inputs. Existing timestamp and comparison-sampling contracts apply.

## Default project directory

New/Open/Save As use the existing PathPreferences effective root: a valid configured directory,
then existing Documents, Home, or cwd. Opening a project elsewhere never updates the preference.
Save As keeps the current .ssflp filename (or flight.ssflp before first save) under that root;
ordinary Save keeps the current project path. Dialog display does not create directories.
Log import and Result_<log-stem> export retain their current project-relative rules.

## Shared TimeRange and diagnostics

The shared range bar appears only on Flight and State Estimation. It has start/end handles, a
center handle that shifts the whole interval, one-window left/right buttons, and
presets/Start/End/Duration. Data Explorer always shows the complete log. State Estimation has six
child tabs: State Uncertainty, Innovation, NIS,
Measurements, GNSS Position Self-Check and Landing. NIS has a two-choice display selector:
a full-size NIS plot or a four-row GNSS statistics table for the current TimeRange.
Measurements uses two linked plots. GNSS Position Self-Check has a three-choice display
selector: horizontal consistency error with revision-2 state transitions, signed offline-only
vertical consistency error, and receiver information (hAcc/vAcc/sAcc/satellites). It compares
receiver-native position and velocity within the same solution epoch. Flight visuals end at
the final successful landing candidate start when evidenced. Landing shows complete-mission
recorded LANDING_DIAGNOSTIC transactions, the recorded confirmation summary, or an explicit
absence/disabled message. Persist source/range in .ssflp; display selection does not change
raw/replay/CSV data.
