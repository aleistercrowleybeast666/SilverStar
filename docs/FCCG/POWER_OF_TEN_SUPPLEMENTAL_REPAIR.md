# Power of Ten supplemental source audit — 2026-09-30

Baseline `4a1f3db315aa97fbd591d8ad8001e07f266f1f1d` was clean at task start. This audit used newly generated projects under ignored `.work/post-round5/supplemental-fresh-v2/`; it did not modify or rebuild the six Round5 frozen artifacts. Full, separate logs are in ignored durable `release-evidence/post-round5-source-validation-4a1f3db/`.

## Root causes and repairs

1. The old checker compared two approved file paths containing Windows backslashes. On POSIX this rejected the estimator build guard and FreeRTOS idle-hook ABI declaration. `Get-PowerTenRelativePath` now normalizes relative paths before exact-path policy checks. Positive tests exercise slash and backslash paths; negative tests reject lookalike filenames, wrong directories and unauthorized code. No scanned directory or exception was broadened.
2. Six typed-object assertions in `flight_task.c` checked the address of a static diagnostic array. Four in `device_task.c` checked addresses of local objects. These addresses cannot be null in defined execution; they were removed. Where contracts provide defensible state bounds, `flight_task.c` now checks alignment/calibration enum and readiness ranges plus START diagnostic result/reason ranges. `device_task.c` now checks valid-field subsets, known diagnostic field masks and boolean ranges. The assertion failure path remains the existing fatal safety handler. Other old address assertions, including static radio state, still require file-by-file semantic review.
3. The checker now excludes literal true/false assertions and object assertions on direct local/global addresses or known static arrays from its Rule 5 count. The tests show both empty and meaningful examples. This is a conservative syntactic screen, not proof that every remaining assertion is meaningful.
4. The Ground `pc_byte_stream.c` emitter now includes `<stddef.h>` itself in fallback UART and USB CDC variants. A minimal HAL header compile test covers fallback UART; the existing UART DMA and USB CDC tests cover their code paths without vendor header assumptions.
5. The real `silverstar_fccg.build` Python source package was present locally but absent from Git because a generic `build/` ignore rule matched it. A narrow exception now tracks exactly its three `.py` files; generated build trees remain ignored. This is the actual implementation imported by `FccgService`, not a stub.

## Official checker results

| Run | Source | Result |
| --- | --- | --- |
| Earlier independent Linux baseline | Submitted externally as context; no local re-execution | Ground PASS 455 checks; Flight FAIL 2 path findings. Its diagnostic edited copy was not the official result. |
| Windows fresh Flight, first semantic screen | New generated project, original checker entry | FAIL 201 Rule 5 assertion-coverage findings; the two cross-platform path findings are absent. |
| Windows fresh Flight, latest assertions | `.work/post-round5/supplemental-fresh-v2/Flight`, `Tools/check_power_of_ten.ps1` | **FAIL 194** Rule 5 findings across 108 scanned first-party `.c` files. |
| Windows fresh Ground, semantic screen | `.work/post-round5/supplemental-fresh/Ground/Ground_Station`, same official checker with `-TargetKind Ground` | **FAIL 13** Rule 5 findings across 15 scanned first-party `.c` files. |

The remaining findings are genuine gaps under the stricter Rule 5 policy, concentrated in NEO-M9N (45), system console (27), telemetry service (21), system startup (15) and SX1281 (13). Adding assertions that merely restate known true addresses would make the number smaller without proving safety. A reviewed invariant and failure-policy audit or safe function decomposition is required for each finding. **Power of Ten is not currently a PASS.** The earlier Ground PASS used the weaker count and is not evidence for the revised semantic criterion.

## Ten-rule coverage and limits

| Power of Ten principle | Automated evidence in this checker | Required human review / gap |
| --- | --- | --- |
| 1. Simple control flow | Rejects `goto`, `setjmp`/`longjmp`, suspected direct recursion and unapproved `for (;;)` | Indirect recursion/call-graph and architecture review |
| 2. Bounded loops | Rejects `while`/`do` forms and unapproved infinite loops | Prove each remaining `for` bound, event/work limits and ISR work |
| 3. No dynamic allocation after initialization | Rejects direct allocator calls in scanned C | Review transitive vendor/library allocation and link map |
| 4. Small functions | Counts non-comment code lines, limit 60 | Complexity and generated-code readability remain manual |
| 5. Assertions for safety properties | Requires two counted runtime checks for functions over 20 code lines; known vacuous patterns are excluded | **194 Flight + 13 Ground failures;** inspect actual semantics and fail-safe action for every assertion |
| 6. Narrow data scope | No general automated proof | Review globals, `static` ownership, DMA/ISR state and aliases |
| 7. Check returns and parameters | Typed-object and explicit assertion patterns are counted where meaningful | Review every error path and parameter contract; regex cannot prove handling |
| 8. Limited preprocessor | Flags conditional compilation except exact build/ABI policy | Review headers, macros and configuration combinations |
| 9. Restricted pointers | Flags function-pointer declarations and double pointers except the FreeRTOS idle ABI | Review pointer lifetimes, arithmetic, alignment and ownership |
| 10. Strict build/checks | Checks Makefile warning set, heap-zero linker, source class and checker entry | Static analysis, ARM build, stack/memory audit, hardware evidence remain separate |

The script scans `.c` under its named first-party target directories, including generated first-party source in the selected project. It does not scan headers as standalone translation units, unselected plugin variants or other generated projects. ST HAL, CMSIS, FreeRTOS kernel, FatFs and Semtech vendor C are outside this first-party policy; that is an ownership boundary, not a safety or license approval. Successful regex checks cannot establish full compliance with all ten principles or formal verification.

## Reproduction

From a new generated Flight directory, run `powershell -NoProfile -ExecutionPolicy Bypass -File Tools/check_power_of_ten.ps1`. From a new Ground directory, use the same command with `-TargetKind Ground`. Host tests live in `apps/FCCG`: `python -m pytest tests/test_power_of_ten_checker_paths.py tests/test_ground_pc_uart_dma.py tests/test_ground_usb_cdc_ring.py tests/test_navigation_integrity_host.py tests/test_ground_bridge_bounds.py tests/test_runtime_safety.py -q`. Run from the project's Python environment with `PYTHONPATH=src`. The supplemental test fixture is deliberately minimal and cannot substitute for ARM or board validation.
