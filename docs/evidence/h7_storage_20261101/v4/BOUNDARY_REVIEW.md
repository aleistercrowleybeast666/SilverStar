# H743 owning storage boundary review

Reviewed the complete owning diskio, BSP, generator replacement contract and
emitted Host source changes before final generation. Code is commit
`267e7ad4a5e1b1668dffb2873a89f205f968049c`; `source-snapshot.json` records raw file
hashes and all generator Python files. Other agents' concurrent GUI/model work
is explicitly present in its dirty-status snapshot. No hardware was exercised.

| Boundary | Implemented behavior / evidence |
|---|---|
| Imported input and owner | Ten exact input hashes, retained original files, exact H743/custom/plugin-authoritative selection; two C replacements in Make and both IDE configurations; edited local owning C or shadow headers rejected without overwriting. |
| Initial ownership | Only running scheduler, LUN 0 and one successful critical-section claim; static queue is created once. Error during initialization cannot publish READY. |
| Request arguments | Null, zero/oversize count, invalid LUN and 32-bit sector wrap rejected; maximum 128 sectors. No unchecked caller buffer retained after return. FatFs ABI still supplies buffer capacity. |
| DMA memory | Static 512-byte / 32-byte-aligned bounce buffer; H7 BSP requires AXI SRAM accessibility, disabled DCache, exact SDMMC1 and one sector. No caller memory is granted to IDMA. |
| Start and wait | Checked queue reset, checked HAL/BSP DMA start; 30-second total RTOS deadline, checked before/after ready result and at sector submission; 30,000 ready-poll bound. |
| Completion | One-entry static queue, exact read/write event, finite queue timeout; overflow/wrong/missing event poison storage. |
| HAL callback routing | Exact `&hsd1` only; foreign handles/NULL ignored; error/abort poisons even outside the active DMA phase; no dynamic callback registry. |
| Data publication | DMB before IDMA start and before receive wakeup. Read reports error if poisoned; writes cannot restart or reuse uncertain DMA scratch. |
| Card information / ioctl | Known command only; nonnull output where required, positive sector count and 512-byte sector; asynchronous error fails before info publication. `memcpy` avoids unaligned output casts. |
| Terminal error | NOINIT and poison persist until reset; reinitialization, late same-kind callbacks and later disk requests cannot unpoison or start further DMA. Ordinary I/O failure retains ordinary FatFs error results. |
| Loop/allocation model | Owning loops are 128-sector request or 30,000 ready polls. Static buffer/queue only. Fixed `SD_Driver` vendor ABI table is inherited; no new runtime registry, allocation or first-party callback exception. |
| Host clock | Pure query in all disk/logger modes. Explicit queue/DMA waits (normal completion 2 ticks), task delays, startup 300 ms stall, explicit 20–100 ms jitter and existing bounded producer scheduling advance time. 1,000 queries add zero ticks. Zero-drop, overload-accounting, byte-integrity, timeout and no-reuse assertions are unchanged. |

The old Host `s_ticks++` query implementation made added safety reads create
milliseconds and hence producer epochs. The unmodified v3 logger expectation
failed with 287 drops; its log is retained. After the Host model correction,
both F407 and H743 preflight complete storage runners passed. Final fresh output
reruns have separate commands and complete logs and are the final authority.

Actual-C before/after witnesses are retained: v2 modes 1/2/3 fail the late-ready,
completion-after-error and initialization-error assertions; v3 mode 4 fails the
card-info error assertion. All five modes (normal plus four faults) pass against
the final generated C. No assertion was relaxed to obtain these results.

## Unproven boundaries

This is a software review of the owning adapter and a precisely pinned imported
candidate. It is not a whole-firmware critical-contract proof. HAL command/init
timeouts, FreeRTOS scheduling, interrupt nesting and third-party calls retain
their existing upstream behavior and require independent timing/stack review.
The Host model does not establish STM32 WCET, power-loss recovery, cache or bus
electrical behavior, SD-card guarantees, flight readiness, or navigation quality.

The existing strict H743 stack gate rejects the new build declarations until a
new exact compiler/dependency closure is reviewed. No hashes or allowlists were
expanded. `.su` and linked artifacts show compiler-local data, not whole task,
library, indirect-call, MSP or nested-ISR bounds. Power10 text checks remain the
project's F Prime-inspired adaptation with critical-contract review NOT PROVEN;
they do not prove original Power of Ten compliance or certification.
