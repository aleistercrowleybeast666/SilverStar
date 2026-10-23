# Last received position and recovery.txt

The desktop post-processing page displays the last valid finite position from
received AIR telemetry. It retains that observation across disconnection and
session restart, with its original receive time, telemetry time and session.
The UI explicitly distinguishes current connection data from retained data.
BOOT boundaries are captured before the bounded UI queue coalesces events.

The Cartesian values are E/N/U in metres. Horizontal distance is measured from
the telemetry origin. Bearing remains unavailable until the operator explicitly
confirms the launch origin and true E/N orientation. Confirmation clears on a
new sample session. This is the last observation, not a verified landing point,
operator-relative bearing, path planner or prediction.

**Export recovery TXT** writes the displayed observation and provenance to a
new `recovery.txt` (or another selected filename). Existing files are never
overwritten. No log access, connection, command or actuator action is performed
by this panel. Verification uses synthetic recorded data and offline Qt widgets;
there is no hardware or field-validation claim.
