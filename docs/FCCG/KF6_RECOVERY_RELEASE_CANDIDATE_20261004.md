# KF6 recovery release candidate — 2026-10-04

## Source and artifact identity

The release source is the isolated `release/kf6_recovery_20261004` branch. The firmware-source integration commit is `2e807c79ba4d8e330153b591e0e9dd73eefd87b3`, based on `b2516ed0fc7822a9fa3cb8d0f788eba95674fb00`. Reviewed GUI/Ground LED, GSHC and FLP changes plus two corrected legacy FCCG test fixtures are included through `755e84990a30136691d039574639b322a25d83a8`. The old `fe5a280` change was not duplicated. The generated candidate is `D:\stm32_project\SS_0_5_RELEASE_KF6_RECOVERY` (KF6, STM32F407VET6, OneFace, dual-vector alignment, 10 s Delay, legacy JY901B vertical module mode). No Ground firmware was generated or flashed as part of the GUI integration.

The exact flight BIN SHA-256 is `42C98D08A2F982E695CD062C0EDFAD85BD49E6460A90E5193B9FAC51C5BE0513` (328,076 bytes). The ELF SHA-256 is `40161EF06B483A03C0B952103125F69B47D286289660B0C49F8FD112809D71DA`; decoder SHA-256 `702F59719AE6BADB0A2570D374F0FBA303122631F5EB2300A489364406F3C69F`; descriptor SHA-256 `DB3EE69B5D01EDB8E0479D49EDADC7965F02474A7F1DF55EA0D42AE8E704CD27`.

After GUI integration, a fresh Flight generation probe compared 603 Flight files, the top-level descriptor and decoder against this board-tested candidate: zero missing files and zero byte differences. The GUI source commits therefore did not change this Flight image. The original `BLOCKING_AB` project and its evidence remain intact; a complete ZIP snapshot is retained in the isolated worktree evidence directory, SHA-256 `AFDFF1701E0F29826A6D033BD0E9FB6FC0669A03327CB8C7CAA4FAD8AB365AAC`.

## Software and bench evidence

At firmware source commit `2e807c79`, focused pytest passed 55/55; generated Host passed 75 executables and 4,439,190 checks with zero failures; generated architecture, Power of Ten project text gate, full fresh ARM Release compile/link, real ARM `-fanalyzer` compile/link, memory and stack reports exited 0. Linked FLASH was 328,064/524,288 B, main SRAM 102,716/131,072 B and CCMRAM 55,600/65,536 B. The Estimator static stack margin estimate was 836 B; Device was 416 B. The historical 100 KiB main-SRAM budget is exceeded by 316 B. The Power of Ten gate explicitly reports critical-contract review **NOT PROVEN**. These tool passes do not prove full stack closure, MCU timing, or field readiness.

After GUI integration, affected regressions passed: FCCG Ground LED/schema/generated runtime 46/46, corrected legacy FCCG GUI fixture 7/7, GSHC port/layout 23/23, and FLP export 16/16. The parent coordination thread separately reported a real Chinese export check with zero missing glyphs. The legacy test corrections aligned an SX1281 SPI fixture with the authoritative 10 MHz maximum and replaced fake ELF bytes in a UI binding test with an artifact-provider interface mock; production firmware and artifact gates were not relaxed.

The hardware coordination thread reports two bench runs of this exact BIN, each with full post-flash readback matching the BIN hash. Conditions: no TF card, no GNSS fix, +Y OneFace calibration, dual-vector alignment and 10-second Delay. Deployment occurred at 10.001 s in each run; landing at 14.010 and 14.008 s. Maximum AIR gaps were 0.586 and 0.574 s. Through approximately 11 min 58 s of post-landing observation, SPI error/timeout/BUSY counts and recovery count stayed zero. Each run still showed five radio TX timeouts, cause undetermined. The recovery fault branches were not exercised in this successful bench setup. Hardware access, flashing and readback were done by the separate coordinator, not by the source integration task.

## Open acceptance items

- Diagnose the five TX timeouts seen in each bench run. Do not infer that a zero SPI/BUSY count explains them.
- Exercise bounded recurring SX1281, GNSS and barometer recovery under controlled faults, with normal behavior confirmed afterward.
- Test START with actual GNSS fix and TF logging load. The no-TF/no-fix bench result cannot qualify those paths or field use.
- Ground activity LEDs remain disabled when unbound. Validate explicit GPIO binding and polarity before any Ground hardware build or flash.
- Complete critical-contract review and stack analysis across actual task paths, libraries, indirect calls and ISR/MSP nesting. Static margin and RAM spare bytes are not a stack or timing proof.
- The prior ESKF15 attempt failed on STM32F407VET6 under field conditions. Freeze that candidate; do not infer ESKF acceptance from KF6 results. Any future ESKF trial on a higher-capacity MCU needs separate generation, load testing with GNSS/TF, ARM gates and hardware evidence.

This is a KF6 software and limited bench candidate record, not hardware or flight qualification. No tag or GitHub Release is associated with it.
