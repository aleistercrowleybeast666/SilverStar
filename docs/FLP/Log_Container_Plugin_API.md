# Log Container Plugin API

## Purpose

A Log Container Plugin is trusted code for one incompatible flight-log wire container. It stops
at `RawRecordFrame`; it never assigns payload fields, units, device instances, Channel IDs or
algorithm meaning.

The protected built-in implementation is:

```text
plugin_id:            silverstar.flight_log.container.0_0
container_format_id:  SSLOG0
container version:    0.0
plugin API version:   1
```

Firmware metadata may spell the same immutable SSLOG0 0.0 contract as
`silverstar.sslog.container/0.0`. Decoder-package loading recognizes only that explicit audited
alias and still selects the protected built-in above; generation hashes continue to use the
manifest's original spelling.

Container version describes the wire format and is independent of the FLP implementation version,
decoder-package schema, Record Version and firmware version.

## Stable objects

`ProbeResult` reports confidence, the container format ID and optional inert metadata.
`ParseOptions` carries diagnostics, cancellation/progress context, source size, maximum accepted
payload length, maximum resynchronization scan bytes/candidate count, and damaged-span preview
length. `RawRecordFrame` contains:

- `record_type` and `record_version`;
- declared `payload_length`;
- `sequence`, `timestamp_us` and common `valid_flags`;
- immutable `payload_bytes`;
- absolute `source_offset`;
- `crc_valid`.

`LogContainerPlugin` provides:

```python
probe(source) -> ProbeResult
header_read(source, options) -> Mapping[str, Any]
iter_frames(source, options) -> Iterator[RawRecordFrame]
```

The caller owns the binary stream. Implementations may seek but must not close or modify it.
Cancellation is cooperative through `ParseOptions.context`. Stable diagnostic codes are written
to `ParseOptions.diagnostics`.

## SSLOG0 responsibility

The built-in container validates the 64-byte File Header and checks the 24-byte common Record
Header plus 4-byte CRC-32 trailer. After corruption or lost sync, it accepts a byte-aligned
`FLG1` candidate only when magic, complete header, bounded length, timestamp, complete frame, and
CRC all pass within the configured scan/candidate limits. Bad frames are excluded without repair;
damaged-span offsets and bounded raw hex are diagnostic output. It reports sequence gaps and
preserves already yielded records when the tail is truncated. Unknown Record IDs need no special
container behavior: declared length and CRC delimit the opaque payload.

The container never requires timestamps to increase globally. Record order follows source
offsets; per-channel ordering belongs to dataset construction.

Field names such as `accel_b_mps2`, KF state order, event catalogs, devices and channels are
strictly outside this layer.

## Production registry and parser construction

`PluginRegistry` registers trusted container implementations and offline Algorithm Plugins. It
does not register a fixed Record parser. `builtin_registry()` contains the protected SSLOG0 0.0
container plus the audited Pure INS and KF_6 offline algorithms.

After `LogOpenCoordinator` validates an exact package/Descriptor pair, it constructs one
`DecoderProfileParserPlugin` dynamically from that container and the validated package. GUI, CLI,
project restore, folder discovery, and drag/drop all use this same path. The historical fixed
`Sslog0ParserPlugin` module remains only for frozen internal test fixtures; it is not reachable
through the production registry and is never an opening fallback.

## Trusted `.ssplugin` boundary

`TrustedContainerPluginManager` treats `.ssplugin` as an explicitly trusted code-installation
unit, not as decoder data:

- installation requires an explicit-trust flag;
- installed manifests are discovered only below the configured FLP plugin directory;
- path escape, duplicate members, symlinks, encryption and size-limit violations are rejected;
- the built-in SSLOG0 plugin ID cannot be replaced;
- discovery never executes package code;
- instantiation requires a matching host-provided factory allowlist entry;
- instantiated metadata must exactly match the installed manifest and API version.

A `.ssdecoder` can only name a required plugin ID/API/version range. It cannot include a
container plugin, request automatic installation, or cause unknown code to run. When the required
plugin is missing or incompatible, package loading stops with a stable local error.

## Adding a future container

1. Implement the stable API without importing any project Record Catalog.
2. Assign a new immutable plugin and container-format identity.
3. Add framing, CRC, recovery, truncation and cancellation tests using opaque payloads.
4. Provide an explicitly installed trusted package and host factory.
5. Keep all payload/semantic changes in `.ssdecoder`; do not revise container code for a new
   Record alone.

## GUI installation and refresh

The GUI Install command filters for `.ssplugin`, asks for explicit trust, and delegates to the same path/hash/API/type checks. Algorithm packages are unsupported. Refresh repeats inert discovery without unloading or modifying the live registry or dataset. Installed packages require restart and an exact host-allowlisted factory; archive entry points are never imported by the GUI.
