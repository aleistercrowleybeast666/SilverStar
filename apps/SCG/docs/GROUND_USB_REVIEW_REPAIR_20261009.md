# Ground CDC review repair, 2026-10-09

This follow-up fixes the two P1 and four P2 findings independently reported
against `d1eb4bf95a52a192dc750c7a18dd23d8145386cf`. It changes the owning
Ground plugin/templates and complete-import boundary, not disposable firmware
alone. Core Ground is now 0.1.2. GUI work is separate: main `8b41894` routes the
Ground import and uses its selected linker. No GUI files were changed here.

## Defects and resulting contracts

1. Actual CubeMX CDC Init/DeInit contain a return inside USER CODE regions.
   Insert reset before that return. Preserved official F1/F4 callback fixtures
   execute both callbacks and count two resets, including real adapter
   deconfiguration/reconfiguration checks.
2. A main-loop-only reset flag allowed an old complete command to survive a USB
   reset after Read; an old prefix could also join a new-session tail. RX reads
   now return their session atomically. Main owns parser/PC queue synchronization;
   TX accepts only the queue's session. Frame delivery validates the same epoch
   and publishes to the bounded radio queue under one short PRIMASK section.
   The inspected SX1281/NRF enqueue backends copy to bounded static queues; no
   radio I/O or waiting occurs in that publication section. Already committed
   radio commands linearize before a later reset; this is not a cancellation
   guarantee for commands already accepted. Epoch overflow permanently blocks
   USB sessions instead of wrapping. UART uses a stable zero epoch and retains
   its transport behavior. The whole processing loop is not interrupt-masked.
3. An IRQ source existing on disk is insufficient. Selected enabled handlers
   must be in compiled sources; an explicit TIM HAL timebase also requires its
   source and selected IRQ. Linked gates require strong handlers and inspect
   actual vector bytes. F407's selected TIM1 timebase permits an unused weak
   SysTick; it requires TIM1_UP_TIM10. USB IRQs are always checked on USB targets.
4. Complete imports reject outside/path-alias dependencies, unsafe or macro C
   includes, assembler file inclusion and GNU linker file/search directives.
   These first profiles accept one self-contained linker. Build recipes unexport
   ambient C include search variables. Actual compiler `.d` files additionally
   verify every non-system dependency remains inside the copied target.
5. Snapshot verification compares the full file set and every hash, including
   the deterministic generated README. Adding `stdint.h` is rejected rather
   than silently shadowing a header. Check aliases before reading Ground input.
6. First-profile Makefile definitions accept only the selected MCU and
   USE_HAL_DRIVER; reject conflicting MCU/HSE/CMSIS virtual-header overrides.
   Final resolved SCG definitions receive the same MCU/HSE check. The artifact
   gate also preprocesses actual main and HAL RCC translation units with ARM GCC
   and verifies effective MCU/HSE values, catching source/header overrides.

The conservative include/definition/linker restrictions are explicit support
boundaries, not arbitrary C/GNU Make compatibility. Existing d1 Ground snapshots
must be reimported to capture the IRQ inventory and complete hash set. Legacy
Ground artifact checks explicitly report missing import contracts NOT PROVEN.
Default Flight import/schema routing and owned payload behavior remain intact.

## Reproduced failures and fresh validation

Evidence root is the isolated local task's `usb-validation` directory. Before
editing, the original independent review probes were rerun on pinned d1:
callbacks reset zero times instead of two; cross-session/read-reset commands
were forwarded; external includes, added shadow header and HSE/MCU overrides
were accepted; removing compiled IRQ sources linked weak handlers to
Default_Handler. `review-before/results.json`, `boundary-results.json`, both
`review-*-before.log` and the negative ELF preserve those counterexamples.

`run-review-final.py build` regenerated all three official CubeMX 6.15.0 complete
inputs and forced `make -B -j2 all architecture-check host-tests artifact-check
power10-check static-analysis`. The final `*-review-final-macros.log` and
`generation-review-final-macros.log` all exit zero. ARM GCC is 14.3.1; native
Host GCC is 16.1.0. The analyzer compiles and links actual first-party code with
`-fanalyzer`, rather than performing only syntax checks. USB runs bridge bounds,
owned CDC buffer tests and production session race tests; UART runs bridge
bounds and DMA tests. Reset-before-read, cross-session prefix, reset-at-delivery
produce zero forwarded frames and the normal positive forwards once.

The formal boundary suite initially reports 24 passed, covering both actual
callback layouts, reset races, dependency/hash/definition rejections and linked
vector/dependency negatives. The expanded regression outcome and audited source
and artifact hashes are recorded in `ground-usb-evidence/review-evidence-summary.json`.
The executed backend run reports **115 passed, 1 deselected**, exit zero, in
93.04 seconds (`review-regressions-backend-final.log`). It includes all Ground
runtime/generation, F103 Ground reference, CubeMX and round-two target files,
excluding the separately owned GUI board/editor/activity files listed in the
recipe. This is the complete result for that declared selection.
Sandbox-denied temporary-directory attempts are retained as failed executions
and are not counted as successful tests. The preexisting mixed BMI088/SD plugin
identity duplicate case remains explicitly excluded, never a full-suite PASS.
An expanded run including separately owned GUI tests reports 148 passed,
2 failures and 7 setup errors (one unrelated case deselected): two GUI
enabled/status expectations failed, and seven GUI settings paths escaped their
test workspace. Those results are retained in
`review-regressions-final-macros-success.log` (the filename does not indicate a
successful run). No GUI repair or whole-suite success is claimed here.

| Target | text | data | bss incl. linker stack | unallocated RAM |
| --- | ---: | ---: | ---: | ---: |
| F103C8 USB | 36440 | 380 | 12000 | 8100 |
| F103C8 UART | 27536 | 12 | 7576 | 12892 |
| F407VE USB | 36788 | 248 | 14800 | 116024 |

Each actual ELF/bin/map, source graph, disassembly and `.su` belongs to these
fresh generated outputs. Stack reservation is 2048, heap reservation zero.
Observed known direct call frame sums are 600/616 for main initialization and
480 for Process; they are partial observations, not upper bounds. Library
frames, callbacks, tail calls and ISR nesting prevent a complete stack proof.
Linked spare RAM is not safe stack margin. Worst-case stack, MCU timing, hardware
enumeration/reconnect/radio behavior and complete critical-contract acceptance
remain **NOT PROVEN**. Power10 remains the existing F Prime-inspired project
adaptation; no assertion-density allowlist was expanded and no certification is
claimed. Independent post-repair review remains required.

No flashing, serial access, START, Flight bench operation, original FINAL edits,
push or merge occurred. C071 testing is a separate software candidate based on
official standalone classic middleware; it is not included in the F1/F4 complete
CubeMX import support claim or these artifact results.
