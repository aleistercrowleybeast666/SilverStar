# Linked memory resource summary

Unallocated banks and summed free bytes are not a contiguous allocation guarantee.
Physical free bytes and review-budget free bytes are different limits.
No unused RAM value establishes dynamic stack safety; strict stack failures remain failures.
null review budget means none recorded for this bank, never an inferred budget.

| Case / MCU | Bank | Used / physical bytes | Used % | Physical free bytes (%) | Review budget / free bytes | Reserved in used | Allocated span / tail | Stack |
|---|---|---:|---:|---:|---:|---:|---:|---|
| f407 / STM32F407VET6 | FLASH | 355892 / 524288 | 67.881% | 168396 (32.119%) | — | 0 | 355900 / 168388 | strict command FAIL; whole program NOT PROVEN |
| f407 / STM32F407VET6 | RAM | 102148 / 131072 | 77.933% | 28924 (22.067%) | 102400 / 252 | 1024 | 102152 / 28920 | strict command FAIL; whole program NOT PROVEN |
| f407 / STM32F407VET6 | CCMRAM | 60888 / 65536 | 92.908% | 4648 (7.092%) | — | 0 | 60888 / 4648 | strict command FAIL; whole program NOT PROVEN |
| installation / STM32F407VET6 | FLASH | 408316 / 524288 | 77.880% | 115972 (22.120%) | — | 0 | 408324 / 115964 | strict command FAIL; whole program NOT PROVEN |
| installation / STM32F407VET6 | RAM | 102316 / 131072 | 78.061% | 28756 (21.939%) | 102400 / 84 | 1024 | 102320 / 28752 | strict command FAIL; whole program NOT PROVEN |
| installation / STM32F407VET6 | CCMRAM | 63304 / 65536 | 96.594% | 2232 (3.406%) | — | 0 | 63304 / 2232 | strict command FAIL; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | FLASH | 369056 / 2097152 | 17.598% | 1728096 (82.402%) | — | 0 | 369064 / 1728088 | task estimate only; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | RAM | 218096 / 524288 | 41.599% | 306192 (58.401%) | — | 0 | 218096 / 306192 | task estimate only; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | DTCMRAM | 8192 / 131072 | 6.250% | 122880 (93.750%) | — | 8192 | 131072 / 0 | task estimate only; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | RAM_D2 | 0 / 294912 | 0.000% | 294912 (100.000%) | — | 0 | 0 / 294912 | task estimate only; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | RAM_D3 | 0 / 65536 | 0.000% | 65536 (100.000%) | — | 0 | 0 / 65536 | task estimate only; whole program NOT PROVEN |
| h743 / STM32H743ZIT6 | ITCMRAM | 0 / 65536 | 0.000% | 65536 (100.000%) | — | 0 | 0 / 65536 | task estimate only; whole program NOT PROVEN |
| sx1278 / STM32F407VET6 | FLASH | 344268 / 524288 | 65.664% | 180020 (34.336%) | — | 0 | 344276 / 180012 | task estimate only; whole program NOT PROVEN |
| sx1278 / STM32F407VET6 | RAM | 92844 / 131072 | 70.834% | 38228 (29.166%) | 102400 / 9556 | 1028 | 92848 / 38224 | task estimate only; whole program NOT PROVEN |
| sx1278 / STM32F407VET6 | CCMRAM | 60888 / 65536 | 92.908% | 4648 (7.092%) | — | 0 | 60888 / 4648 | task estimate only; whole program NOT PROVEN |
| sx1278-ground / STM32F103C8T6 | FLASH | 17500 / 65536 | 26.703% | 48036 (73.297%) | — | 0 | 17500 / 48036 | no full stack gate; whole program NOT PROVEN |
| sx1278-ground / STM32F103C8T6 | RAM | 5380 / 20480 | 26.270% | 15100 (73.730%) | — | 1028 | 5384 / 15096 | no full stack gate; whole program NOT PROVEN |
| bundle / STM32F407VET6 | FLASH | 355900 / 524288 | 67.883% | 168388 (32.117%) | — | 0 | 355908 / 168380 | strict command FAIL; whole program NOT PROVEN |
| bundle / STM32F407VET6 | RAM | 102148 / 131072 | 77.933% | 28924 (22.067%) | 102400 / 252 | 1024 | 102152 / 28920 | strict command FAIL; whole program NOT PROVEN |
| bundle / STM32F407VET6 | CCMRAM | 60888 / 65536 | 92.908% | 4648 (7.092%) | — | 0 | 60888 / 4648 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | FLASH | 372132 / 2097152 | 17.745% | 1725020 (82.255%) | — | 0 | 372140 / 1725012 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | RAM | 218708 / 524288 | 41.715% | 305580 (58.285%) | — | 0 | 218712 / 305576 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | DTCMRAM | 8192 / 131072 | 6.250% | 122880 (93.750%) | — | 8192 | 131072 / 0 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | RAM_D2 | 0 / 294912 | 0.000% | 294912 (100.000%) | — | 0 | 0 / 294912 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | RAM_D3 | 0 / 65536 | 0.000% | 65536 (100.000%) | — | 0 | 0 / 65536 | strict command FAIL; whole program NOT PROVEN |
| h743-owned-v6 / STM32H743ZIT6 | ITCMRAM | 0 / 65536 | 0.000% | 65536 (100.000%) | — | 0 | 0 / 65536 | strict command FAIL; whole program NOT PROVEN |
| native-private-STM32C071FBP6 / STM32C071FBP6 | RAM | 10512 / 24576 | 42.773% | 14064 (57.227%) | — | 2052 | 10512 / 14064 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32C071FBP6 / STM32C071FBP6 | FLASH | 42276 / 131072 | 32.254% | 88796 (67.746%) | — | 0 | 42276 / 88796 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32F103C8T6 / STM32F103C8T6 | RAM | 11308 / 20480 | 55.215% | 9172 (44.785%) | — | 2052 | 11312 / 9168 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32F103C8T6 / STM32F103C8T6 | FLASH | 40300 / 65536 | 61.493% | 25236 (38.507%) | — | 0 | 40304 / 25232 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32F407VET6 / STM32F407VET6 | RAM | 13976 / 131072 | 10.663% | 117096 (89.337%) | — | 2052 | 13976 / 117096 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32F407VET6 / STM32F407VET6 | CCMRAM | 0 / 65536 | 0.000% | 65536 (100.000%) | — | 0 | 0 / 65536 | reserved linker bytes only; whole program NOT PROVEN |
| native-private-STM32F407VET6 / STM32F407VET6 | FLASH | 41912 / 524288 | 7.994% | 482376 (92.006%) | — | 0 | 41912 / 482376 | reserved linker bytes only; whole program NOT PROVEN |
