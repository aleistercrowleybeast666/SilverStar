# SilverStar project targets

A format 13 SilverStar project contains one Flight Controller configuration, an optional Ground Station target, and one project-owned AIR Link. The in-memory Flight fields retain the first-round FCCG API to keep existing Flight generation stable; Ground has independent MCU, board or imported CubeMX hardware, radio resources, PC interface, and build options. Ground and link are serialized under ground_target and air_link alongside the existing Flight fields.

    SilverStar project
    ├─ Flight Controller
    │  ├─ MCU / board or CubeMX hardware
    │  ├─ devices, algorithms, flight logic, protocols and storage
    │  └─ resource graph and build
    ├─ Ground Station (optional)
    │  ├─ independent MCU / board or CubeMX hardware
    │  ├─ radio and PC byte-stream bindings
    │  └─ Ground bridge and build
    └─ AIR Link
       └─ logical AIR profile and shared radio PHY

The Flight Hardware and Ground Station Hardware pages each offer one generate/update action. Saving the project creates only the root `SilverStar.ssproject` and `Log/`; neither target must be generated. Target outputs are `Flight_Controller/` and `Ground_Station/` under the selected external project root. Each has its own Makefile, build tree and matching `.code-workspace`. The Build & Validation page builds, inspects and validates generated targets; it does not generate them. Ground generation is blocked until its radio, hardware resources, PC interface and shared link are ready. Flight-only generation can proceed while the optional Ground target is incomplete. The [project folder contract](PROJECT_FOLDER_CONTRACT.md) defines root decoder and log discovery. Generated firmware is never source in this repository.

Flight SS0.5 is an internal Ground generation test fixture only. The GS_SS1 Ground Station 0.5 reference is STM32F103; the current platform generator is STM32F407, so no Ground verified board is offered in the production selector. A production Ground target must provide a Ground-safe generated CubeMX project; importer hardware inventory, platform matching and source-graph machinery are shared with Flight. A standalone `.ioc` is pending hardware configuration; readiness reports `GROUND_CUBEMX_GENERATION_REQUIRED` until CubeMX generates the project sources.
