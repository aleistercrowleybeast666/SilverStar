# Horizontal trajectory in FLP and GSHC

FLP appends a horizontal trajectory tab after the six existing Flight tabs. GSHC
appends a horizontal trajectory page after its three existing top pages; the
six live curves and 3D view retain their layout. Both use the same standalone
geometry builder and Matplotlib renderer, mirrored byte-for-byte in each app.
`test_both_apps_ship_identical_standalone_geometry_and_renderer` protects that
contract without a runtime dependency between the installed applications.

East E is the horizontal axis, north N is the vertical axis, both in metres.
The axes have equal metric scale and equal numeric spans. The trajectory uses
viridis colours for relative height U; each actual sample has its own height
colour and each uninterrupted segment uses its endpoints' mean U. The colourbar
states relative height U and metres. Negative heights are retained. A constant
height has one colourbar tick at its actual value. Colours are local to the
displayed range and do not imply a common scale between separately exported pages.

Only start (green circle), parachute deployment (orange diamond) and end (red
square) receive named markers. The legend sits below the axes. A clipped start
or end is labelled View start/View end (范围起点/范围终点), rather than being presented
as the mission boundary. Missing initial or final position samples mean the
markers refer to the first/last valid recorded position in that mission view;
they do not manufacture an exact position at the event timestamp. Deployment
is omitted if absent, outside the selected range, or located in a gap. A single
sample is visible, with coincident start/end semantics in the legend. An empty
range shows the localized no-data message and no colourbar or event markers.

No trajectory samples or clipping endpoints are interpolated. Nonfinite time
or ENU, invalid samples, repeated or reversed timestamps, recorded reanchors and
long gaps split the lines. The default maximum connected interval is the smaller
of one second and 2.5 times the median positive recorded cadence. A deployment
marker may interpolate only within one connected adjacent pair, never across
a split, and never extrapolates to a nearest point outside its valid interval.
Exact duplicate deployment epochs choose the last valid matching position;
duplicate epochs themselves never create a connecting edge.

FLP uses the existing active analysis source, flight display bounds, shared time
range and display-only mission origin. Cropping preserves that origin. GSHC uses
its existing mission-relative ENU data and bounded live buffer; a live buffer
start after zero is a view start, and its end remains a view end until LANDED.
GSHC retains its existing live ten-second range. Export uses the existing range,
page, language and theme options and writes `Trajectory2D` PNGs under plots/charts.
The same builder and renderer produce the GUI and export geometry. Existing plot
items remain present; GSHC chart output increases from seven to eight per page.

Regressions use synthetic inputs for empty, short, constant/negative U, duplicates,
NaN, long gaps, reanchors, deployment absence/gaps, origin/range semantics, byte
parity, metric scale and actual exports. The native Qt probe is
`apps/FLP/tests/validation/field_gui_probe.py`; it creates only its own windows
and synthetic inputs, including strict production open through matched test
decoder/Descriptor packages for FLP. Run it separately for `flp` and `gshc` with
an evidence output directory and `QT_QPA_PLATFORM=windows`. The probe exercises
EN/light and ZH/dark at 1280x720 and 1280x900, empty/incremental content, preserved
views, exports and reopen. Its Qt-rendered screenshots do not prove physical
screen compositing or hardware performance.
