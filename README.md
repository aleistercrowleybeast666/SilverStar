# SilverStar

**SilverStar Rocket Avionics & Ground Suite** · pre-release version **0.1.1**.

This repository contains three applications:

| Application | Purpose | Start from repository root |
| --- | --- | --- |
| SCG | System Configuration & Generation（系统配置与生成） | `python SCG.py` |
| GSHC | Ground Station Host Computer | `python GSHC.py` |
| FLP | Flight Log Processor | `python FLP.py` |

Use one Python 3.11+ environment: run `tools/setup_venv.ps1`, then use `.venv/Scripts/python.exe` for all three launchers. SCG retains the compatible `apps/FCCG/FCCG.py` launcher, `silverstar-fccg`, the `apps/FCCG` implementation path and existing project schemas for compatibility; new installations also expose `silverstar-scg`. The root `VERSION` is the product release authority. AIR M0, SSLOG 0.0, `.ssdecoder` 1.2, project semantics, navigation revision, FreeRTOS, board, MCU and vendor versions remain independent.

FCCG keeps Flight Controller configuration and adds an optional Ground Station target. Both targets consume one [AIR Link](docs/architecture/AIR_LINK.md); Ground bridges opaque AIR packets to GSP over UART or USB CDC. See the [target model](docs/architecture/TARGET_MODEL.md), [Ground firmware boundary](docs/architecture/GROUND_STATION.md), [Device variants](docs/architecture/DEVICE_VARIANTS.md), and [documentation index](docs/README.md). Runtime and generated work belongs below ignored .work/ or an explicitly selected external user project.

Recommended project workflow: create a [SilverStar project root](docs/architecture/PROJECT_FOLDER_CONTRACT.md) in FCCG, configure the two targets and AIR Link, generate Flight and/or Ground from their hardware pages, build each target independently, copy TF/SD logs into `Log/`, then open that project folder in FLP. USB CDC Ground firmware still needs a complete CubeMX-generated CDC project and real hardware verification.

Round 5 has a [frozen software reference](docs/field/FIELD_TEST_REFERENCE.md), [field qualification checklist](docs/field/FIELD_TEST_CHECKLIST_0_1_0.md), [blank session record](docs/field/FIELD_QUALIFICATION_RECORD_TEMPLATE.md), and [evidence report](docs/architecture/ROUND5_FIELD_QUALIFICATION_REPORT.md). The software candidate awaits F407/F103 bench integration, actual TF logs and target timing evidence before it can be called field-test ready.

Original SilverStar first-party source is offered under the [Apache License 2.0](LICENSE). Bundled vendor code and Python dependencies retain their own terms; see the [source license audit](docs/architecture/SOURCE_LICENSE_AUDIT.md).

No public 0.1.1 release has been made.
