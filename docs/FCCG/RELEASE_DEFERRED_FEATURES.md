# SCG 0.1.1 deferred features

2026-10-01 GUI closeout policy; this document does not qualify firmware for hardware or flight use.

| Feature | Retained implementation | First-release boundary | Restoration requirements |
| --- | --- | --- | --- |
| Magnetometer selection, calibration and TF calibration persistence | Declarative device plugins, magnetic alignment/calibration services, storage payloads, GSHC calibration page module and schemas | SCG omits magnetic choices and capabilities; GSHC omits the calibration tab. Generated device descriptors expose no magnetic endpoints. Generated configuration rejects magnetic enable overrides. Legacy magnetic configurations report blocking compatibility errors without rewriting navigation. | December policy review; re-enable GUI and descriptor exposure together; restore the qualified-provider success test; test exact old project import, explicit migration, calibration failure/cancel, persistence integrity and generated ARM/Host behavior. |
| Variable vector constraint count | Alignment schema and add/remove implementation methods | GUI offers external attitude or exactly gravity plus one known direction. Legacy constraints remain in the loaded model; the explicit fixed-pair draft button requires confirmation before publication. | Re-enable controls only with independent-vector and reentry regressions; verify old schemas and generated model agree. |
| Wireless automatic backup switching | Existing configuration/protocol implementations remain | No new automatic multi-radio switching is implemented in this GUI stage. | Separate approved work; transport readiness, shared resources, old-source rejection, debounce and hardware evidence. |

Opening a legacy magnetic project preserves its model and blocks first-release generation. The explicit migration button asks for confirmation and a new empty directory outside the original tree. It creates a KF6 copy with gravity plus a known direction; existing direction parameters are retained where present, otherwise the default requires review. The Compatibility directory preserves the exact original descriptor bytes, the complete loaded model and both configurations in the migration record. Source logs and decoder packages remain untouched at their original location. This workflow was unfinished in the historical stage-one report and is now covered by copy/cancel/failure/reopen regressions. Existing schemas, `FCCG.py`, `silverstar-fccg`, `apps/FCCG` paths and historical evidence names remain compatible.

The ordered IMU/GNSS/barometer cold-backup requirement is unfinished engineering work, not an implemented deferred feature. The existing selector does not establish long-fault cold-backup behavior. Shared UART/I2C/device ownership and actual initialization/settling limits must be established before accepting that work.

See [the candidate checkpoint](gui_closeout_20261001_v1/CANDIDATE_REPORT.md) and [the exact cold-backup gap](gui_closeout_20261001_v1/COLD_BACKUP_GAP.md). A configured standby sensor does not imply accepted cold-backup operation.

A new six-dimensional fixed-gain estimator and automatic RAM relocation are planning topics only; neither is implemented or validated by this stage.
