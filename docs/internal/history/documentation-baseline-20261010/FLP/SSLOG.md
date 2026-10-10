# SSLOG0 support

The protected built-in `silverstar.flight_log.container.0_0` implements profile 0: a 64-byte
header followed by records containing a 24-byte common header, opaque payload, and 4-byte
CRC-32/IEEE. It has no knowledge of IMU/KF fields, units, instances, channels or algorithms.
Each CRC-valid record becomes a `RawRecordFrame` containing type/version, declared payload
length, sequence, timestamp, validity flags, raw bytes, source offset and CRC validity.

Production opening combines this container only with an exact matched `.ssdecoder` 1.1 and
selects each payload layout by `(record_type, record_version)`. The historical fixed parser is
kept for frozen internal fixtures but is not registered and is never a GUI/CLI/project fallback.

CRC failure, an invalid length at an expected record boundary, or an unexpected byte sequence
starts current-SSLOG0 bounded resynchronization. A candidate is accepted only after its
byte-aligned `FLG1` magic, complete common header, payload length, plausible unsigned-microsecond
timestamp, complete frame, and CRC-32 have all been validated. A recovery scans at most 65,536
bytes and evaluates at most 1,024 magic candidates. A false `FLG1` inside damaged bytes is not a
record boundary merely because its magic matches.

Bad frames are excluded. FLP never patches their header, repairs their payload, synthesizes a
replacement sample, or applies a legacy-layout interpretation. Diagnostics retain CRC/length/
resynchronization counts, original and recovered offsets, sequence-gap size, and a bounded
96-byte uppercase hexadecimal preview of each damaged span. Already decoded records remain
available. If no valid candidate is found within the bound, the remaining bytes are reported as a
truncated/unrecoverable tail instead of launching an unbounded search.

CRC-valid unknown current record types and unknown versions are advanced by their declared
payload length and counted in diagnostics. The dynamic parser retains their raw bytes and labels
the result partial, allowing a newer log to remain inspectable without guessing a layout.

Container version, container-plugin API version, decoder-package schema, Record Version and
firmware version are independent. Record IDs are never reused and a layout for an existing
type/version pair cannot be duplicated inside a catalog.

Every production log also contains the fixed 64-byte `DECODER_PROFILE_DESCRIPTOR` bootstrap
Record. The container exposes it as opaque bytes; matching code validates the package/container
version and three 128-bit hash prefixes before dynamic payload parsing. A missing/conflicting/
nonmatching Descriptor rejects the open.

Record file order and timestamp order are deliberately separate. Records retain source offsets
and file order; timestamps may regress between interleaved producers. No global monotonicity rule
is imposed. Each generated channel is sorted only by its own recorded timestamp before becoming a
`TimeSeries`.
