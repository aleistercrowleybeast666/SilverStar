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

Flight SS0.5 is an internal Ground generation test fixture only. The Ground Station 0.5 PCB plugin selects the STM32F103C8T6 exact MCU and STM32F1 family backend using GS_SS1's hardware-tested IOC topology. The new SilverStar Ground UART software has an ARM compile/link result, not a new board smoke result. Custom Ground hardware can still use an imported CubeMX generated project; a standalone `.ioc` is pending hardware configuration and reports `GROUND_CUBEMX_GENERATION_REQUIRED` until CubeMX generates the project sources.

Both hardware pages can save an imported generated CubeMX snapshot as a local,
unverified PCB instance. The [PCB instance workflow](PCB_INSTANCE_WORKFLOW.md)
defines its evidence and selector behavior.
