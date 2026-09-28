# SilverStar

**SilverStar Rocket Avionics & Ground Suite** · pre-release version **0.1.0**.

This repository contains three applications:

| Application | Purpose | Start from repository root |
| --- | --- | --- |
| FCCG | Flight Controller Code Generator | `python FCCG.py` |
| GSHC | Ground Station Host Computer | `python GSHC.py` |
| FLP | Flight Log Processor | `python FLP.py` |

Use one Python 3.11+ environment: run `tools/setup_venv.ps1`, then use `.venv/Scripts/python.exe` for all three launchers. The root `VERSION` is the product release authority. AIR M0, SSLOG 0.0, `.ssdecoder` 1.2, project semantics, navigation revision, FreeRTOS, board, MCU and vendor versions remain independent.

See [documentation](docs/README.md), [architecture](docs/architecture/MONOREPO_ARCHITECTURE.md), and the [migration report](docs/architecture/MIGRATION_0_1_0.md). Runtime and generated work belongs below ignored `.work/` or an explicitly selected external user project.

No public 0.1.0 release has been made.
