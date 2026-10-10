# AIR position display policy

GSHC export keeps raw GSP/AIR logs, processed position samples, event times and
summary data unchanged. Only position visualization uses a separate display copy.
No new warning UI or export warning is added.

A position is excluded from visualization if its time or any ENU component is
nonfinite, or an absolute component exceeds 1,000,000,000 metres (one million
kilometres). This is a deliberately broad Earth-local display envelope for gross
numeric corruption, not an estimator validity rule or an accuracy guarantee.
There is no speed/acceleration gate, median-coordinate filter or smoothing, so
reasonable high dynamics are retained. Finite spikes inside this broad envelope
remain outside the scope of this defense.

Rejected rows are retained as NaN separators in display copies. They do not
affect 2D height normalization, 3D limits, position curves or animated position
interpolation. Neither line segments nor the current animated point interpolate
across a rejected row. Animation and static 3D rendering share the same history
paths. An empty/all-invalid position set has safe default axes and no position
or deployment marker.

AIR time stamps are integer milliseconds. The default connected interval is
`min(1000, ceil(2.5 * median_positive_interval_ms))` milliseconds. It is computed
from the original cadence, including rejected position rows, so exclusion does
not make the cadence sparse. A few floating-point ULPs accommodate subtraction
of mission seconds; they do not add a physical millisecond. An explicitly supplied
gap threshold is retained. The shared FLP/GSHC standalone geometry module is
unchanged; GSHC passes its AIR-specific threshold and validity mask to it.

Deployment uses its recorded time and an exact valid sample or one connected
adjacent pair. It is not snapped to the nearest sample, extrapolated, or placed
inside a rejected/long-gap interval. The same deployment point is used by 2D and
3D. When multiple rows have the exact same AIR millisecond, their retained input
order is preserved and the last row determines the event position and validity.
An invalid final row suppresses the marker, even if an earlier duplicate was
valid; there is no fallback to a stale position. All duplicates and invalid rows
still split trajectory geometry. GSHC adapts the 2D marker to this same rule,
while retaining the standalone geometry's page-range visibility requirements.

A 598 ms interval with a 239 ms median cadence is connected (the unquantized
limit is 597.5 ms); 599 ms still splits geometry and omits an interior deployment
point. The one-second default cap remains.

The identified field session contained one finite U of approximately -2.22e15 m
in a CRC-valid recorded GSP payload. Display exclusion repairs the scale collapse
but does not identify or resolve that value's upstream origin.
