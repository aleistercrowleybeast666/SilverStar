# Project format v3

`.ssflp` is an atomic, single-log reference document. It never embeds or modifies a log or decoder.
Version 3 rejects all older versions, including v2 multiplier configurations; no migration exists.
Decoder, generation, Catalog, Semantics, cache and container identity checks remain mandatory.

Each `replay_configurations` item contains exactly:

- `algorithm_id` and `algorithm_version`;
- `mode`: `recorded_configuration`, `what_if`, or explicit `offline`;
- `input_source`;
- `actual_values`: ID-to-value map;
- `parameter_schema_identity`: SHA-256 of plugin schema metadata;
- `provenance`: `Firmware build configuration from .ssdecoder` or `Algorithm Plugin actual defaults`.

Unknown fields/IDs, missing values, invalid types/ranges, non-finite numbers, old plugin/schema
identities and invalid modes are rejected. Recorded values cannot override the package.
Restore checks every saved configuration against the opened dataset and validates provenance
before publishing it. The `draft` entry preserves unsubmitted What-if edits; historical run
configurations remain available in the document, while result arrays are recomputed when requested.
Saves flush a temporary UTF-8 JSON file and atomically replace the target.

## Desktop workflow and path authority

**New Project** first asks for the destination `.ssflp`, then opens the existing manual-pair or
bounded folder-search import flow. Cancellation or exact-match failure leaves that destination
untouched; an existing destination requires confirmation and is replaced only by the final atomic
save after validation. Open Project selects only `.ssflp` and requires its referenced log and
decoder at their exact saved identities—there is no similar-name recovery scan.

Log and decoder references in the project directory or descendants are stored relative to the
`.ssflp`; paths that cannot be relativized fall back to absolute references. A neighboring FCCG
`SilverStar.ssproject` is an inert sidecar: FLP does not parse it, infer parameters from it, or use
it for matching. The authoritative chain remains log Descriptor ↔ exact `.ssdecoder` 1.2.

The format remains **version 3**. These interactions add no fields and define no second project
model.

## Analysis source and range state

Version 3 ui_state stores analysis_source and time_range (start/end/preset/custom_duration).
The selected normal replay/What-if configuration is re-executed on reopen and retains its run ID.
No result arrays are embedded; source log and decoder identity checks precede restoration.
