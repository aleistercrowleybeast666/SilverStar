# SCG verification checkpoint

Recorded after the full Flight group completed, before the new USB GUI build group completed. No freeze is registered.

Daily HEAD `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`, SCG tree `e03ca99998df2d9d75ad3e817d25d83daba2bd8a`. No tracked changes. The three existing untracked inventory files and their bytes are preserved. Isolated ccdi remains clean at `5b99438ba4005ea02935e9734307e749e2e758e7`.

| Full explicit module group | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Backend fzb01 | 46 | 2 | 2 |
| GUI/native fzg01 | 138 | 0 | 0 |
| UART/Ground fzu01 | 150 | 0 | 0 |
| Flight fzf01 | 198 | 4 | 10 |

The two backend failures are F103 generic/pinned complete-model equality and generic-model unified Export rejected by the facts/profile binding guard before compilation. Current ordinary descriptor comparison shows evidence path/SHA256 differences; CPU, memory and IRQ fields are equal. The known equality baseline was not waived, and the second failing test was not silently treated as accepted.

The Flight failures are one broad catalog duplicate identity assertion (`sd_sdio_fatfs` versus `sd_sdio_fatfs_f1`), two `ModuleNotFoundError: tools` in historical runtime import tests, and a generated stack-report source-byte equality mismatch. These are recorded SCG Flight regression failures; no GSHC/FLP tests were run. No old SD/TF repair or investigation was undertaken. Their earlier baseline status has not been established. Ten Flight skips explicitly require a supplied real ARM Release artifact fixture. Two Backend skips require the separate private native ARM opt-in flag.

## Live continuation

Owned exec session **96012** is still running `python -B run_freeze_sequence.py`. At this checkpoint it has completed `flight_modules` and started `usb_gui` (`fzgui01`), which is still incomplete. It has not been terminated, detached silently, or counted as passed.

The sequence runs strictly in order: full actual offscreen USB GUI/F103/C071 build, full USB async group against those fresh receipts, fresh emitted native architecture/Host/artifact/PoT gates, real startup/launcher checks, then fresh normal GroundUART and Flight emitted `power10-check`, `architecture-check`, `host-tests`, `all`, `static-analysis`, `artifact-check`. All outputs are in Temp or this task directory, not user projects. The legacy runner selects the installed Windows `D:/msys64/ucrt64/bin/mingw32-make.exe`; no emitted Makefile or checker is patched.

Resume by polling the owned session with `write_stdin(session_id=96012, chars="", yield_time_ms=30000)` from this execution context. `fz-sequence.json` and each `fz*-command.json`/JUnit/log are the saved continuation state. Do not relaunch the sequence while this session is active. After it completes, run `python -B write_freeze_verification_report.py` to refresh the aggregate report. A wrapper exit of zero does not imply test success: original pytest/Make exits and JUnit are authoritative.

Fresh PoT results are **not available at this checkpoint**; previous dm02 passes belong to the prior verification, not this run. Formal generation and USB release remain blocked, independent safety review is `NO_PASSED_OUTCOME`, and NOT PROVEN limitations remain in force. No source/test/gate edits, hardware, push, tag, merge, or release occurred in this verification turn.

Companion aggregate: `SCG_FREEZE_VERIFICATION_20261010.json`; complete evidence uses `fzb01`, `fzg01`, `fzu01`, `fzf01`, `fzgui01`, `fza01`, `fzng01`, `fzlegacy-*`. This is the explicit ordinary module scope, not all historical repository tests.
