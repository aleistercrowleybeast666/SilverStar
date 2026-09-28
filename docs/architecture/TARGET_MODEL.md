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

The Build page offers **Generate Flight Controller**, **Generate Ground Station**, and **Generate All**. Target outputs are FlightController/ and GroundStation/ under the selected external project root. SilverStar.ssproject stores the common configuration. GroundStation/ contains its own Makefile and GroundStation.code-workspace build task. Ground generation is blocked until its radio, hardware resources, PC interface, and shared link are ready. Flight-only generation can proceed while the optional Ground target is incomplete. Generate All uses one in-memory AIR Link snapshot and refuses source conflicts. Generated firmware is never source in this repository.

The Ground board path currently recognizes the verified SS0.5 board application entry and replaces its Flight task startup with the Ground loop. Other boards must provide a Ground-safe generated CubeMX main.c; importer hardware inventory, platform matching and source-graph machinery are shared with Flight. A standalone .ioc can be imported for pending hardware configuration; readiness reports GROUND_CUBEMX_GENERATION_REQUIRED until CubeMX generates the project sources.
