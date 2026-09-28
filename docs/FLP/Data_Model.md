# FlightDataset data model

`FlightDataset` is immutable after parsing/adaptation. It contains the parsed header, decoded
records grouped by record name, independent `TimeSeries` channels, source metadata,
`ParserDiagnostics`, an explicit immutable `DataQualitySummary`, and one immutable
`DatasetSemanticContext`.

Every `TimeSeries` contains its own `uint64 timestamp_us`, values, unit, physical quantity, source,
validity vector, column names, and metadata. Times are sorted using the logged timestamp. No
nominal sample rate is used to synthesize time and different rates are not interpolated until a
specific comparison explicitly requests it. Decoded records preserve file order and
`file_offset`; the file as a whole is not required to be timestamp-monotonic.

Algorithm results use the same `TimeSeries` model. Standard IDs (`attitude.q_nb`,
`navigation.velocity_enu`, `navigation.position_enu`) feed common views. Algorithm-specific IDs
remain discoverable in Data Explorer and export.

## Configuration-driven channel construction

A `RawRecordFrame` is the immutable boundary between trusted container parsing and payload
decoding. The generic Record Catalog selects a layout only by
`(record_type, record_version)`; its finite scalar/array/padding decoder produces a
`DecodedRecord`. Unknown layouts are retained with `raw_payload` and `__partial__` metadata
instead of being interpreted.

Project Semantics turns decoded values into `ChannelDefinition` objects. `partition_by` fields
must occur in the channel ID template, so records such as IMU 0 and IMU 1 cannot accidentally
share one series:

```text
imu.0.native.accel_b
imu.1.native.accel_b
```

Channel metadata carries Descriptor ID, physical-device ID, capability class, instance, plugin
and model. Separate capability endpoints may therefore remain separate while still grouping under
one physical module. A canonical channel is emitted only when its explicit `canonical_when`
condition matches; algorithm plugins continue to consume that single canonical channel instead
of automatically running once per raw instance.

FCCG packages may express the same mapping through `record_views`,
`raw_channel_id_templates`, `capability_endpoints`, `physical_devices`, and
`canonical_channels`. The binding layer resolves those declarations against the Record Catalog,
preserves the source/instance partition in each raw channel ID, and retains capability and
physical-device identifiers as channel metadata. It does not merge two equal-capability devices
or silently promote every instance to a canonical input.

A default raw-channel template is used only when every placeholder can be supplied by that
Record. In particular, `descriptor_id`, `source_descriptor_id`, physical-device ID, instance ID,
and capability ID remain distinct namespaces even when two happen to have the same numeric value.
A Descriptor-style Record that has no `source_descriptor_id` falls back to its Record name plus
the actual declared partitions; it is never implicitly attached to a device endpoint.

The semantic adapter retains every raw dynamic channel and adds audited stable role IDs by storing
the same `TimeSeries` object under an alias key. Arrays are copied once at dataset construction and
made read-only; aliasing never duplicates samples or permits mutation. Ambiguous/missing audited
routes fail rather than using field offsets or name similarity.

## DatasetSemanticContext

The context is the query boundary between package metadata and upper consumers. It holds:

- full package/generation/Catalog/Semantics identity and project/firmware commit;
- firmware algorithm component IDs and separate immutable resolved parameter sets;
- logging/telemetry/maintenance protocol metadata (optional slots may be `null`);
- hardware, physical devices, capability endpoints/routes, canonical routes, and Record Views;
- configured modes/strategies, event catalog, streams, components, and component locks;
- the raw-channel templates and raw-to-stable alias map;
- the validated effective `CalibrationSnapshot`.

Overview, Replay, State Estimation, Data Explorer, CLI inspection, projects, and export query this
context instead of reading arbitrary nested JSON. Raw package metadata is retained in immutable
form for diagnostics.

Configured stream membership and actual sample presence remain separate. A configured,
enabled `GNSS_MEASUREMENT` stream may legally contain zero records. GNSS transport online,
navigation fix, usable geodetic position, and usable velocity are also separate facts. A 0/0
geodetic placeholder without `position_usable` is retained as raw data but marked invalid for
plots and exports.

## CalibrationSnapshot

The snapshot records the selected result timestamp/boundary, source/virtual IMU, mode/state/ready,
face mask, counters, four bias/scale vectors, corrected-sample count, and consistency status.
`NONE` is represented explicitly by zero bias, unit scale, zero face mask, and zero
sample/reject/retry counters; it is never encoded as an absent object. `start_sequence` is
provenance and may be nonzero. `NONE` is always a legal identity model and need not appear in the
configured one-face/six-face sampling procedures. All calibration records remain available; the
effective snapshot is the latest valid result at or before START, otherwise the initial-state or
first-corrected-IMU boundary. Dataset construction fails if no valid snapshot can be selected.

`DataQualitySummary` is derived from parser diagnostics, recorded cumulative queue counters, and overflow events. It reports
clean/warnings status, valid-record count, CRC and length failures, successful resynchronizations,
sequence gaps/missing records, unknown/decode counts, damaged spans, logger overflows, truncation,
and per-Record counts. It never changes exact decoder-package identity into an algorithm
equivalence claim.

## Algorithm concepts

Firmware membership, recorded output presence, complete recorded parameter availability, and
offline plugin availability are separate fields. A firmware component string does not instantiate
a plugin. A recorded curve does not prove its full configuration was logged. Offline defaults are
immutable plugin metadata and are not inserted into `recorded_parameters`.

## Display and integrity additions

See [Display_DataQuality.md](Display_DataQuality.md) for semantic column rules and the independent
record-gap/queue/channel-continuity model. Column metadata changes labels only; raw/stable aliases
remain the same immutable objects. Unknown array columns use bracketed indices.

`FirmwareParameters_Get(component_id)` and `FirmwareParameterSets_Get()` expose immutable package
actual values independently of membership. Replay results contain actual parameter snapshots,
schema identity, per-parameter units/representation, config source, plugin version and fidelity.
Project v3 persists these references and values; [Project_Format.md](Project_Format.md) describes
strict restore rules. Export puts firmware sets under `firmware.algorithm_parameters` and each
run's values under `replay_results[].actual_parameters`.
