# SilverStar

**SilverStar Rocket Avionics & Ground Suite** · pre-release version **0.1.0**.

This repository contains three applications:

| Application | Purpose | Start from repository root |
| --- | --- | --- |
| FCCG | Flight and Ground target configuration and code generation | `python FCCG.py` |
| GSHC | Ground Station Host Computer | `python GSHC.py` |
| FLP | Flight Log Processor | `python FLP.py` |

Use one Python 3.11+ environment: run `tools/setup_venv.ps1`, then use `.venv/Scripts/python.exe` for all three launchers. The root `VERSION` is the product release authority. AIR M0, SSLOG 0.0, `.ssdecoder` 1.2, project semantics, navigation revision, FreeRTOS, board, MCU and vendor versions remain independent.

FCCG keeps Flight Controller configuration and adds an optional Ground Station target. Both targets consume one [AIR Link](docs/architecture/AIR_LINK.md); Ground bridges opaque AIR packets to GSP over UART or USB CDC. See the [target model](docs/architecture/TARGET_MODEL.md), [Ground firmware boundary](docs/architecture/GROUND_STATION.md), [Device variants](docs/architecture/DEVICE_VARIANTS.md), and [documentation index](docs/README.md). Runtime and generated work belongs below ignored .work/ or an explicitly selected external user project.

No public 0.1.0 release has been made.
