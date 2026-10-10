# Ebyte SX128x variant implementation and handoff

This isolated branch starts at accepted `cc424443fe217cf6c9cf0fd674805158b5bfce45`.
Firmware implementation checkpoint: `0ee1b0201c001b1947a783c91b3f8323ed8e6fa0`.
本地机器路径已移除；源码位置以仓库相对路径及该组件声明为准。
No hardware, flashing, root synchronization, or remote push is part of this work.

## Supported hardware contract

| Module | Nominal module output | SX128x chip drive | SetTxParams power byte | External frontend | Official manual |
| --- | ---: | ---: | --- | --- | --- |
| E28-2G4M12SX | 12 dBm | 12 dBm | `0x1E` | none | [combined 12S/SX](https://www.ebyte.com/downpdf/2049.html) |
| E28-2G4M12S | 12 dBm | 12 dBm | `0x1E` | none | [12S](https://www.ebyte.com/downpdf/285.html) |
| E28-2G4M20S | 20 dBm | -2 dBm | `0x10` | RX_EN/TX_EN | [20S](https://www.ebyte.com/downpdf/304.html) |
| E28-2G4M20SX | 20 dBm | -2 dBm | `0x10` | RX_EN/TX_EN | [combined 20S/SX](https://www.ebyte.com/downpdf/2217.html) |
| E28-2G4M27S | 27 dBm | 0 dBm | `0x12` | RX_EN/TX_EN | [27S](https://www.ebyte.com/downpdf/527.html) |
| E28-2G4M27SX | 27 dBm | 0 dBm | `0x12` | RX_EN/TX_EN | [27SX](https://www.ebyte.com/downpdf/1920.html) |

There is no E28-2G4M28 entry. The manuals document the nominal PA points above,
not a calibrated output ladder. Each module has a singleton supported power list.
Passing 20 or 27 as the chip drive, or interpreting -2/0 as the module output,
is rejected by the configuration contract. The library's real encoder adds 18.
Current official Chinese manuals identify SX1281; older English descriptions
differ. This branch uses their compatible LoRa interface and does not infer
ranging support or a chip identity from an S/SX suffix.

M12 has reset pad 9, BUSY 10, DIO1 11 and no PA control pins (14-pad package).
M20/M27 have active-high RX_EN pad 8 and TX_EN pad 9, reset 11, BUSY 12,
DIO1 13 (16-pad package). Module pad numbers describe the module; they are
not MCU pin or logical GPIO numbers. All six manuals cap the SPI interface
at 10 Mbps; the manifest enforces 10 MHz. Existing Flight 5.25 MHz and
Ground 9 MHz wiring remain valid.

Official supply ranges are 1.8–3.6 V for M12/M20 and 2.5–3.6 V for M27.
Typical transmit currents are 45/140/580 mA respectively. Their different
pad layouts and supply demands require a verified board adaptation. The
synthetic CubeMX inputs in the evidence runner are software fixtures only.
Every newly added variant is labeled hardware unverified, not flight qualified.

## Configuration and runtime

The existing plugin ID `silverstar.device.telemetry.sx1281`, its original
M12SX module ID, and the AIR M0 protocol remain unchanged. Missing Flight
instance module/power fields retain the legacy M12SX/global-power behavior.
Explicit instance choices persist as project format 16; legacy 14/15
projects serialize without the new fields. Ground and Flight share one PHY
snapshot and use the same variant chip-drive mapping.

PA instances require two distinct output GPIOs with active-high polarity,
push-pull, no pull, low startup state, and glitch-free initialization. The
resolver rejects missing controls, GPIO aliases, peripheral pin conflicts,
and excessive SPI clocks. These checks cover Ground cold-standby instances,
not only the currently active radio. M12 typed resources carry the invalid
GPIO sentinel for both controls; the runtime performs no frontend GPIO writes.

Frontend transitions always write both controls low and check both results
before enabling RX or TX. Completion, timeout/error, recovery, forced RX,
deactivation, and fault paths retire the frontend. An I/O failure invalidates
READY and stops further normal radio work; a failed low write cannot prove
physical RF shutdown. Reset-low is a best-effort fallback. IRQ callbacks
continue to latch events only; GPIO transitions run in the owner task.

No regional policy mechanism was found in the accepted source. Existing
validated frequency and PHY limits are retained (2473 MHz is the sole
validated frequency). A technical nominal-power capability does not grant
regional operating permission. If a deployment policy requires a lower
module output, configuration must remain unsupported until official or
measured calibration evidence supplies that point; no conversion is guessed.

## GUI integration intersection

The separate GUI work owns `main_window.py` and page layout. This branch
does not edit those files. Its new manifest adds six module choices and two
conditionally required resources. The GUI must resolve requirements for the
selected instance instead of reading the raw family's optional requirements.

Use `FlightRadioConfiguration_Get(model, instance)` and
`FlightRadioConfiguration_Apply(model, instance_id, module_id, nominal_dbm)`
from `project.radio_variants`. Apply returns a copy and preserves unrelated
radios; selecting M12 removes that instance's obsolete PA bindings. Keep
module and power controls in each folded wireless instance panel.

In `_GroundTargetView_Refresh`, replace the current `len(flight_modules) == 1`
assumption with the selected instance module from the getter. Its supported
powers come from `manifest.radio.modules[module_id]`. Use the getter's power
for the selected instance rather than `model.flight_tx_power_dbm`. Ground
requirements should use `RadioManifest_Resolve` for each configured radio,
including the legacy single-radio representation. That helper accepts a
`DeviceInstance` with `module_variant` and `tx_power_dbm`.

When a Ground instance changes from a PA module to M12, the GUI integration
must also remove that instance's `radio_rx_en`/`radio_tx_en` assignments. The
existing generic `GroundRadiosConfiguration_Apply` drops assignments on plugin
changes, but a module change within this shared plugin keeps them. Stale
bindings should not survive the edit and then block generation as unknown
requirements. Flight's dedicated apply helper already performs this cleanup.

## Reproducible software evidence

`tools/run_ebyte_radio_evidence.py --output .work/<fresh-name> --analyze --host`
generates six modules for Flight F407 and Ground F103 from isolated synthetic
CubeMX inputs. It runs each emitted Makefile for ARM Release link, architecture,
Power-of-Ten, artifact/memory checks, real `-fanalyzer` builds, and host tests.
The JSON report records complete commands, exits, logs, source hashes,
configurations, warnings, and ELF/BIN/map/stack-usage hashes. No existing
Power-of-Ten exception or conditional-compilation allowlist was expanded.

The real encoder host fixture checks `0x1E`, `0x10`, and `0x12`, low/low before
single-high transitions, M12 with no frontend writes, completion/recovery,
forced RX, deactivation, GPIO failures, and no ISR GPIO work. Existing
duplex, handshake, runtime owner, resource, and Ground HAL suites are retained.

The initial synthetic Flight runs hit a byte-for-byte baseline fixture assumption
in `test_runtime_startup.c:112` (`PLATFORM_GPIO_6`). Both configurations map the
same physical `IMU_CAL_LED` pin: custom CubeMX assigns logical GPIO 0, while the
verified board assigns GPIO 6. The generic fixture now checks the actual configured
indicator GPIO and valid bounds. Existing verified-board fixed-index and physical
binding tests remain intact and pass. All original failures are retained; all six
corrected full Flight suites pass 75 executables, 4,430,924 checks, seven compile
success cases, and 17 expected compile failures apiece. The original verified
M12SX board separately passes its unmodified 75-job host suite.

Final source checkpoint `9b0948e` passes fresh ARM Release builds and architecture,
Power-of-Ten, and artifact/memory gates for all six modules and both roles.
Regression results are 148 passes plus a separate six-test indicator/board suite.
Twelve real analyzer runs at `0ee1b02` pass; Flight has no warnings, and Ground has
four consistent newlib unimplemented-syscall linker warnings. Every final executable
function and other build input is identical to those analyzed. The only firmware
differences are two fixed 16-byte SSLOG metadata hash initializers caused by the
provenance/test metadata update. Fresh final links and four targeted final startup/
SSLOG host jobs for each Flight variant cover those bytes. Analyzer warnings were
not suppressed, and the failed initial runs are not relabeled as passes.

Complete matrix outcomes and scope are in
`evidence/ebyte-validation-summary.json`（历史或内部参考，不纳入公共说明的验收依据）.

Passing these software checks does not prove the project's critical-contract
manual acceptance conditions. That scope remains **NOT_PROVEN**. RF output,
antenna isolation, board power integrity, pin timing on hardware, and flight
qualification also remain unverified. See the accompanying evidence summary
and command records for actual final outcomes and any failures.
