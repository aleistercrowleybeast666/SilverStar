# Flight persistent storage (SilverStar 0.1.0)

The Flight target's current provider is SD/TF over SDIO with FatFs. Ground
does not require persistent storage. LoggerTask is the sole FatFs owner;
cross-task consumers read bounded health snapshots through the storage and
log sink interfaces. The firmware uses static buffers and no heap.

The SD card layout currently produced by the F407 reference is:

```text
/system/calibration/mag00.0, mag00.1
/system/device/devNN.0, devNN.1
/system/preferences/preNN.0, preNN.1
/missions/000001/flight.sslog
/missions/000001/manifest
/missions/000001/snap00.0, snap00.1
```

The mission directory number is allocated when the log session opens. An
existing directory is skipped, including an incomplete directory left by an
interrupted prior boot. Mission IDs are bounded to six decimal digits; the
current log session limit is lower. Persistent objects use two slots, a
generation counter and CRC32. A new generation is written to the inactive
slot, synced and read back. Readers choose the highest valid generation and
can fall back after a torn write. The object payload limit is fixed at build
time. These files are compact binary data, not JSON.

The immutable 20-byte `manifest` is created in a new mission directory
before `flight.sslog` is opened. It contains `SSMF`, schema 1, the SilverStar
product version, mission ID, profile ID and CRC32. Creation requires sync and
readback. The START readiness getter only reports a mission ID after this
check succeeds. A failed manifest write or a log create failure after the
manifest is durable latches the session fault rather than allocating another
directory on each retry.

FatFs long-file-name support uses static BSS storage and an ASCII-only
conversion adapter. This supports the fixed SilverStar directory names and
rejects foreign names outside printable ASCII. An imported CubeMX FatFs
configuration must use a compatible static LFN setting and must not compile
another `ff_convert` implementation into the same target.

The current START check requires a mounted, healthy, writable log sink, a
verified mission manifest, a committed mission snapshot and the logger's
streaming-ready state. The snapshot freezes selected devices, source priority,
effective navigation parameters, alignment inputs, and calibration identities
through bounded binary dual-slot objects. Its committed identity is also
recorded in SSLOG. Landing/finalization writes a best-effort final-status
object. Post-START storage failure marks the sink unhealthy without stopping
navigation or the flight state machine. See [mission snapshot](MISSION_SNAPSHOT.md)
for the section layout, atomicity and failure behavior.

The real FatFs Host fixture covers long paths, log output, two object
generations, snapshot banks, final status and torn-slot fallback. F407 ARM
Release compile/link and static memory/stack checks cover this software path.
Physical SD card behavior remains hardware unverified.
