# Single-sensor software candidates: final v8 evidence

Firmware source: `170f1cb55daedf8e8d308a7bc845b2fa5b79d102`. GUI fixture identity updates: `112db65005a549dffa207421869754e17185a346`.
The frozen KF6/SF6 Delay10 ZIPs were created before final application retries; their bytes and internal manifests remain unchanged. `final_acceptance.json` binds the final software results to their exact SHA256s. No actual TEST_4 configuration, source, binary or logs were modified.

One executed four-algorithm v8 matrix passed all 24 commands: ARM compile/link/artifact audit, architecture, generated Power10 gate exactly as emitted, Host regressions, real ARM `-fanalyzer` compilation, and resource/stack reports. The separate v7 matrix had 22/24 passes (SF6 analyzer and ESKF Host failed); those original failures are preserved. The GNSS group boundary fix checks group before shifting/indexing and copies two constant-index elements. Group 4/32/255 post-fix fault tests trap; attempted UBSan pre-fix proof could not link its missing runtime and remains UNAVAILABLE, never a runtime pass.

GSHC full retry: 455 passed plus 3 subtests. FLP full retry2: 496 passed, 28 explicit skips (see complete log for unavailable real-log/manual and opt-in fixtures). FCCG GUI smoke/release retry: 19 passed. These are their executed scopes; earlier failed application runs remain archived. No combined, unexecuted suite pass is asserted.

| Algorithm | FLASH bytes | Main SRAM bytes | CCM bytes |
|---|---:|---:|---:|
| PureINS | 284740 | 83000 | 44016 |
| KF6 | 317124 | 102328 | 55432 |
| ESKF15 | 303276 | 100928 | 63456 |
| SF6 | 291428 | 101704 | 44016 |

Capacities are 524288 / 131072 / 65536 bytes. These linked region reports do not prove runtime stack margin or WCET. SF6 context is 18592 bytes, +10256 versus the initial implementation. Its six gains 0.2 are untuned defaults. Replay oracle tests cover cross-group ordering, attenuation, ring wrap, expiry/FULL/refusal recovery and atomic failure. Review supports only the implemented previous-IMU-boundary quantization (up to 20ms); it is not fractional interpolation or hardware timing proof.

Both frozen candidates use only Delay, 10.0 seconds; native tests consume their actual emitted configuration without overriding delay/mask and each pass 10556 checks including 9999/10000ms and exactly-once deployment. Existing actuator pin declarations and safety gates remain; they are not GPIO-disabled artifacts. No physical disconnection was verified.

The v8 native SF6 backend export passed 29655 checks. FLP production `LogOpenCoordinator` opened its exact decoder/Descriptor with 1000 state and 104 measurement rows, absent covariance/NIS; missing/wrong decoder rejects and immutable source hashes were checked. The synthetic fixture is software evidence, not a recorded hardware flight or accuracy qualification.

GUI captures are offscreen fixtures. `FCCG_GUI_Final_v8_Acceptance` is the accepted registered-font capture: visible light/dark Ground and CRC checkbox borders, disabled Ground action/status, six gains, compact Chinese single-line SCG identity and 0.1.1. Earlier tofu captures and incomplete page captures remain as failed capture evidence. `GUI_Final_v8` preserves all four GSHC language/theme combinations and bounded viewport geometry. Offscreen GL was hidden; desktop/hardware interaction is unverified.

The emitted F Prime-inspired assertion scanner is a project gate, not original Power-of-Ten compliance or certification. Critical-contract manual acceptance, whole-program call graph/stack/timing, hardware recovery and navigation accuracy remain NOT PROVEN. Source 255 UNKNOWN remains truthful for barometer provenance; actual source/epoch and cold-backup contracts await the separate Baro work. This archive excludes auto-memory and multi-radio changes. No serial/probe/reset/programming/OptionBytes/actuator commands were issued.
