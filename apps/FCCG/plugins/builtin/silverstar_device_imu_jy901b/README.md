# JY901B

Declarative SilverStar_FCCG builtin `device` plugin.

Reference baseline: `main` at `cc0b377ded690556d037a412a55f87fe334c42d0`. Reference-derived files retain the recorded snapshot provenance; FCCG-owned files are replayed from their declared workspace source-of-truth and identified separately in `metadata.source_origins`. Plugin payload is data and is never executed.

Installation direction is selected per JY901B instance in Devices. New reference
projects explicitly use vertical (ORIENT=1); horizontal selects ORIENT=0. Older
projects without a recorded direction preserve the device's existing ORIENT value
without rewriting it. Their actual horizontal/vertical mode is unknown to the
project until the operator explicitly selects one. The register is read back at
startup and changed only when a selected direction differs;
the normal boot path does not issue SAVE. This is the module's internal setting, so
neither the raw acceleration/angular-rate samples nor the external quaternion is
rotated again by FCCG. Recalibrate after a direction change. The effect on each
physical JY901B output frame still needs hardware validation; the official protocol
example establishes the register command/readback but does not prove the full
acceleration, angular-rate and quaternion coordinate relationship.
