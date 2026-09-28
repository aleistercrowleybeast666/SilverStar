# SilverStar monorepo architecture

```text
SilverStar
├─ FCCG — declarative Flight and Ground target configuration and code generation
├─ GSHC — AIR M0 ground telemetry, commands, readiness and operator UI
└─ FLP  — immutable SSLOG log opening, exact decoder validation, replay and export
```

`apps/FCCG`, `apps/GSHC` and `apps/FLP` retain their existing internal module names. The root launchers locate their applications; they contain no product logic. All use one Python environment and the root `VERSION` for product release identity.

`contracts/navigation_v1.json` is the one machine-readable navigation contract. FCCG generation, GSHC navigation documentation and FLP replay share that authority. AIR M0, SSLOG 0.0, `.ssdecoder`, project semantics and navigation revision are separate compatibility identities and remain unchanged by the product release version.

FCCG's builtin plugin manifests and generated firmware release metadata use the unified product identity. Generated firmware is an output in a user-selected project or ignored work area, never a long-term source directory here. User logs and decoder packages are immutable inputs. Application-local implementation details remain owned by each application; explicit cross-component work can update all three.

FCCG now places Flight Controller and optional Ground Station firmware in one project. Both share [AIR Link](AIR_LINK.md); Ground remains an opaque AIR packet bridge to GSHC's GSP serial stream. [Target model](TARGET_MODEL.md), [Ground Station](GROUND_STATION.md), and [Device variants](DEVICE_VARIANTS.md) define the second-round boundary. Simulator and device automatic initialization remain future work.
