# SilverStar workspace guidance

This repository is the unified SilverStar monorepo. For an application-local task, change the affected application. For an explicitly cross-component contract, version, or integration task, changes across `apps/FCCG`, `apps/GSHC` and `apps/FLP` are permitted. `contracts/` owns shared machine-readable contracts.

Use the repository naming style: noun, underscore, capitalized verb phrase (for example `Lora_TryStartNextTx`). Public operations returning success or failure reasons should use an `UpperCamelCaseResult` enum. New C header guards use `__` plus the uppercase filename with periods replaced by underscores. Keep file-scope state `static` where possible; expose it through an interface. Check whole-file implications of every edit.

FCCG: preserve declarative plugins, source-graph ownership, generated-file boundaries, workspace path safety, storage integrity, interrupt/DMA safety and explicit hardware verification. Imported CubeMX files are not FCCG source. Normal generation must not overwrite user-owned project payloads. Read [FCCG architecture](docs/FCCG/ARCHITECTURE.md) and [runtime safety](docs/FCCG/platform/details/RUNTIME_SAFETY.md) for detailed constraints.

GSHC: AIR M0 and command/controller readiness are authoritative. An ACK does not imply READY. Keep serial/protocol processing off the GUI thread and maintain bounded queues and diagnostics. Read [AIR protocol](docs/GSHC/AIR_PROTOCOL.md) and [GSHC architecture](docs/GSHC/UPPER_COMPUTER_ARCHITECTURE.md).

FLP: source logs and recorded datasets are immutable. Production opening requires the exact `.ssdecoder` and Descriptor through `LogOpenCoordinator`; do not add fallback decoding or treat offline defaults as recorded. Keep trusted container plugins separate from declarative decoder data. Read [FLP architecture](docs/FLP/Architecture.md) and [decoder contract](docs/FLP/Decoder_Profile_Package.md).

`.work/` is disposable test, build, generated-project and analysis space. Cleanup may remove only verified generated files; preserve user inputs, logs, decoder packages, archives, source fixtures and formal evidence. Generated firmware normally belongs to the user-selected external project. Do not treat a synthetic fixture as hardware validation.
