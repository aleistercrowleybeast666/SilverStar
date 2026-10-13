# Log file service and session export versions

The 0.1.3 development work adds two independent contracts:

- [`log_file_service_v1.json`](../../../contracts/log_file_service_v1.json): Console ASCII `LOGFILE` service version 1. It does not change Maintenance 0.0, AIR M0 or GSP.
- [`session_export_v1.schema.json`](../../../contracts/session_export_v1.schema.json): a directory package or ZIP containing `manifest.json` and unchanged file bytes, with per-file SHA-256, role, format and format version. The sibling golden manifest uses `123456789` as synthetic content, not a valid SSLOG recording.

SSLOG already has container version **0.0**, `SSLOG0` magic, per-record versions, firmware version in the file header and an embedded Decoder Profile Descriptor. The declarative `.ssdecoder` package remains **1.2**. These are distinct from product version **0.1.3**, file service version **1**, and export schema version **1**. Downloading never converts records or replaces the embedded Descriptor. FLP still requires the exact decoder package through its existing coordinator.

New GSHC JSONL sessions declare `log_format=silverstar.gshc-jsonl` and `log_format_version=1` in SESSION_START. Existing JSONL files are preserved byte for byte and described as `legacy-unversioned` in exports.

## Maintenance protocol

Use the exact request/response examples in the machine-readable contract. `CAPS` negotiates support. `LIST` exposes one numbered mission log per cursor page; `META` computes its full CRC32 and size; `READ` returns up to 64 original bytes at an explicit offset, with a chunk CRC32. `LIST`, `META`, `READ` and `DELETE` submit work and return a request ID. `POLL` retrieves completion; `CANCEL` stops further work. Clients allow one outstanding request and verify operation, request ID, file ID, token and offset before accepting data.

Only LoggerTask accesses FatFs. Metadata hashing advances in bounded chunks and checks lifecycle/cancellation between chunks. Reads of old missions are allowed in PREFLIGHT, READY and POSTFLIGHT while preflight recording continues. The current mission is never exposed, even if its writer is temporarily closed for retry. FLIGHT/RECOVERY and other states reject work. A storage transaction already executing completes under the existing diskio timeout before a cancellation can be observed; this is not proof of STM32 timing or WCET.

The v1 implementation exposes only `0:/missions/NNNNNN/flight.sslog`; client paths are never accepted. Older flat-directory logs remain readable through existing offline tooling, but are not enumerated by this service. `closed=1` means there is no active writer for that mission; it does not certify that recording finalized successfully after a power interruption.

The token `1-CRC32-SIZE` is a versioned change detector. It is not cryptographic identity or authorization. Both device ID and boot ID are explicitly `unknown` until a reliable backend is implemented. After disconnect, timeout, cancellation or reboot, clients repeat CAPS and META. They must restart from offset zero when device/boot identity is unknown; even a matching prefix cannot authorize continuation. A matching length/CRC alone does not justify appending bytes from an unknown device. A client validates final size/CRC, calculates SHA-256 locally and atomically publishes a completed download. Failures preserve the source and keep partial local data distinguishable from completed artifacts.

Deletion is disabled: CAPS advertises `delete_supported=0`, and DELETE returns `UNSUPPORTED`. The current unknown device/boot identity cannot justify destructive selection across reconnection. A future identity-capable implementation must require fresh metadata and a separate explicit confirmation. Download success never implies permission to delete. There is no AIR/radio bulk binding and no automatic low-bandwidth telemetry download.

## Acceptance boundary

The shared contract and synthetic golden vectors define interoperable host behavior. Firmware service integration and host fault tests are development work; no statement here certifies completed hardware acceptance. Fresh generated Power of Ten, host regressions, real analyzer compilation, ARM link, source graph and stack/artifact reports must be recorded for the implementation snapshot. Critical contract review and hardware behavior remain NOT PROVEN until their separate evidence exists. No TF card, serial device, programmer or flight actuator was operated to establish these contracts.
