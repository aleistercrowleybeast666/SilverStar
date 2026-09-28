# Compact FLP software evidence

All raw input and matching decoder hashes are preserved in the per-log reports. The final 426-pass full suite includes current source/C parity and both final C-codec arrival order cases. Nine unrelated manual fixtures were explicitly skipped because their required external inputs were absent.

A later C-only prediction/history transaction fix passed a separate 20-test delta (18.82 s), including 600 ms rejection rollback, multiple-prefix commit, 192-slot overflow and original math/window/delay/golden cases. No extra global/full-state storage was added. The full-suite result remains separately dated.

All five four-way reports live at ../four_way_comparison/SS0000 through SS0004. All five ESKF 15-state diagnostic reports live at ../five_logs_contract_final/SS0000 through SS0004. Numerical NPZ/run JSON files are kept locally and hash-listed here; do not add temporary builds, DLLs, executables, cache directories or raw BIN files.

Final binding of max-gap/threshold/cap uses the same explicit 120 ms / 10 m / 4 values stored in every completed C replay. The retirement patch does not change those numerical inputs. The independent parameter-effect regression demonstrates all three values really affect new-policy windows.

actual_backend_logger.json records a separate actual production backend/LoggerBus/LoggerTask closed loop: 491 records, exact decoder, FAITHFUL numeric comparison, 361 exported files and zero export failures. Two unavailable legacy corrected-IMU plots are explicitly skipped. Its synthetic host sink is not a target FatFs timing test. Initial complete covariance is mandatory; Flight explicitly disabled periodic covariance is reported unavailable. Unattempted numeric diagnostics are unavailable only after exact admission and result comparison.

Package smoke builds 0.0.5 offline and loads the wheel extraction, plugin and contract/translation resources; no install or publication. Offscreen screenshots load the existing Windows Chinese font and are not physical-display certification.

These are software fixtures and old-log What-if analyses, not hardware or flight acceptance. SS0002 origin failures and SS0000/2/4 ESKF INVALID results remain visible.
