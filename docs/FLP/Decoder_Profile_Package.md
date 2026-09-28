# Decoder Profile Package 1.2

## Authority and exact layout

Every opened flight log must be paired with one declarative `.ssdecoder` generated for that
firmware project. The package is the sole authority for Record layouts, device/capability
metadata, stable semantic routes, configured modes, protocols, and the firmware component list.
It never supplies executable parser or algorithm code.

FLP accepts only package schema `silverstar.ssdecoder.package-schema/1.2`. The ZIP must contain
exactly these five members:

```text
manifest.json
record_catalog.json
project_semantics.json
checksums.sha256
README.md
```

Schema 1.0, unsigned/provisional packages, alternate member names, extra files, and compatibility
fallbacks are rejected. The canonical JSON bytes, member checksums, full Catalog/Semantics
SHA-256 values, generation-profile SHA-256, and complete package SHA-256 all participate in the
identity contract.

The supplied FCCG package uses the declared container ID `silverstar.sslog.container/0.0`.
That spelling is an audited alias for the protected built-in
`silverstar.flight_log.container.0_0`; the manifest spelling is still used when validating the
generation-profile hash.

## Import security

`DecoderProfilePackage.Load` reads members in memory and never extracts or executes them. It
enforces archive, uncompressed-size, member-size, member-count, path-depth, compression-ratio,
JSON-depth, and JSON-node limits. Absolute paths, `..`, drive prefixes, backslashes, NULs,
case-insensitive duplicates, encryption, links/special files, executable suffixes, duplicate JSON
keys, and non-finite JSON constants are rejected.

The package must declare `contains_executable_code: false`, a compatible trusted container
plugin/API/version range, the supported primitive whitelist, and the selected
`flight_log.0_0` profile. `checksums.sha256` must cover every other member and nothing else.
Source logs and source packages remain read-only.

## Catalog and Project Semantics

`record_catalog.json` selects a layout only by `(record_type, record_version)`. The decoder
supports finite little-endian scalar types, fixed arrays, and fixed padding. Layouts have an exact
payload size; there is no expression evaluation, import, callback, or code hook. A CRC-valid
unknown type/version retains its `raw_payload` and source metadata as a partial record.

`project_semantics.json` must identify `silverstar.project-semantics/1.2` with numeric schema
version `0x00010001`. It may bind Catalog fields through explicit Record semantics or FCCG
`record_views`, `raw_channel_id_templates`, capability endpoints, physical devices, canonical
routes, logging streams, events, modes, strategies, and protocols. Firmware algorithms may be a
list of component-ID strings; these IDs describe firmware membership and are not executable
offline plugins.

Raw dynamic channels remain in `FlightDataset`. The audited semantic adapter adds stable roles as
zero-copy aliases of those immutable `TimeSeries` objects. Upper pages and offline algorithms use
stable roles; Data Explorer and export retain raw IDs and metadata. Ambiguous canonical or stable
routes fail instead of selecting an arbitrary device.

## Exact Descriptor matching

SSLOG Record `0x1D`, version 0, is a mandatory 64-byte bootstrap Descriptor. Its payload contains:

- package schema major/minor;
- container format major/minor;
- the first 16 bytes of Record Catalog SHA-256;
- the first 16 bytes of Project Semantics SHA-256;
- the first 16 bytes of generation-profile SHA-256;
- eight zero reserved bytes.

FLP decodes this fixed bootstrap contract before consulting the candidate Catalog. A package is
accepted only when schema/container identity and all three hash prefixes match exactly. The only
match mode is `exact_generation_profile`. File names, Catalog/Semantics-only ranking, manual
override, Descriptor-less logs, and built-in parser fallback are not evidence of identity.

## Unified single-log opening

`LogOpenCoordinator` is the only production opening path for GUI import, folder discovery,
drag/drop, CLI, and `.ssflp` restore. It performs one atomic sequence:

1. validate exactly one read-only log and one package source (manual, cache, or bounded search);
2. load and fully validate package 1.2 and `flight_log.0_0` protocol metadata;
3. read the Descriptor and require an exact package match;
4. import the already-validated package into the content-addressed cache and reload it;
5. construct `DecoderProfileParserPlugin` dynamically from the trusted container plus package;
6. parse raw Records/channels, apply stable semantics, and validate calibration;
7. publish one complete `LogOpenResult` only after every step succeeds.

Failure leaves the current GUI dataset/project/replay state unchanged. Folder discovery is bounded
by depth, parent count, file count, and total bytes and requires the user to select one independent
pair if more than one exists. Drag/drop accepts one `.ssflp`, or one log with zero/one
`.ssdecoder`; a log without a package triggers the same bounded exact search.

## Calibration authority

Every opened log requires a valid `CALIBRATION_RESULT`. FLP selects the latest **valid** result not
later than mission `START`, or otherwise the initial-state/first-corrected-IMU boundary. Invalid
later attempts remain visible as history but do not replace an earlier valid result. The effective
result must be ready, finite, allowed by the current semantic contract, and consistent with later
`IMU_CORRECTED` records.

Mode `NONE` is a valid ready result only with zero bias, unit scale, zero face mask, and zero
samples/rejects/retries. Its `start_sequence` is provenance and is not required to be zero.
`NONE` is independent of `modes.calibration`: a package may configure only `SixFace` while a
particular log legally records a ready identity result because no calibration run occurred.
One-face and six-face results must be declared and meet their respective face/sample completion
rules. A missing/future-only set or a set with no finite, complete, consistent result rejects the
open.

GNSS stream configuration is also independent of recorded usability. An enabled native GNSS may
be online with `fix_type=0`, unusable position/velocity, and zero `GNSS_MEASUREMENT` records. That
is a legal indoor/no-fix log, not a decoder failure. Offline algorithm availability follows each
plugin's required/optional input contract rather than assuming GNSS measurements are mandatory.

## Algorithms, projects, and audit export

FLP keeps three independent concepts:

- component IDs declared as members of the firmware;
- algorithm outputs actually recorded in this log;
- offline Algorithm Plugins installed in FLP.

Recorded Configuration is offered only when every required firmware actual value is present
in the exact package. Header/SYSTEM_CONFIG values and plugin defaults never fill missing fields.
Offline defaults and What-if values never fabricate a recorded configuration. Pure INS and KF_6
for firmware 0.0.10 remain `APPROXIMATE` until the real-log host golden gate proves equivalence;
the existing `SILV0008` implementation identity is not renamed.

`.ssflp` version 3 stores one `log_reference`, one decoder source/cache reference, full package,
generation, Catalog, and Semantics identities, exact match mode, container ID/version, replay
settings, notes, and UI state. Older project versions are rejected. Saves are atomic and never
embed or rewrite the log/package.

The export manifest records the source-log SHA-256, exact decoder identity, project/firmware/
hardware/protocol metadata, firmware component list, selected calibration and alignment
provenance, GNSS usability, complete Data Quality/Parser diagnostics (including damaged spans),
configured streams with actual sample counts, raw-to-stable aliases, exported-channel provenance,
and each replay plugin/mode/provenance/fidelity/parameter/input-contract set. CLI `inspect`,
`replay`, and `export` require either `--decoder PACKAGE.ssdecoder` or `--auto-find` and use this
same coordinator.

## Validation boundary

Synthetic fixtures validate protocol mechanics and rejection behavior, including an explicit
Descriptor and Calibration Result. They do not satisfy a real-log validation gate. A real package
may be validated independently, but claims about decoded values or replay equivalence require its
matching immutable log and expected/golden artifacts.

## Firmware resolved parameters (1.2 only)

The final FCCG wire property is `firmware_algorithm_parameters` (the FCCG project editor calls
its value map `algorithm_parameters`). Each list entry has `component`, `schema_id`
(`silverstar.algorithm-parameters/1.0`), `manifest_sha256`, and `parameters`. Each parameter has
`id`, resolved binary32 `value`, `unit`, `representation`, `storage_type`, and `description`.
The data-only loader validates this before cache insertion. Known algorithm IDs, units,
representations and ranges are checked against trusted builtins; unknown firmware component IDs
never instantiate code. Duplicate owners/IDs, nonmembers, invalid types/finite values and contract
mismatches fail. Missing required values make Recorded Configuration unavailable.
Record Catalog remains independently versioned at 1.0. Package/Semantics 1.1 are rejected;
no legacy fallback or multiplier migration exists. See [Project_Format.md](Project_Format.md).
