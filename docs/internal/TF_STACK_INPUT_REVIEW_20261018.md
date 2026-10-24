# TF installation calibration: exact candidate stack input review, 2026-10-18

Owner: TF calibration integration task on `feature/usb-transport-0.1.3-20261013`.
Baseline: commit `7896c1d09a7f9138c41cdac35beef38347d94b78`, with the pre-existing
dirty changes preserved. Candidate:
`D:/stm32_project/SS_0_5_CAL_TF_CANDIDATE_20261018_01`, Release, GCC ARM 14.3.
This is a reviewed integration of specific inputs, not permission for the checker
to learn hashes from builds. The v20 failed report is retained.

## Scope and evidence

The owning checker revision `tf_calibration_integration_20261018_v21` adds
29 exact input versions, 11 dependency graphs and 159 exact source/compiler-input
tuples. `.work/dev013_mag_tf_20261018_v3/review_registration.json` records all
compiled inputs, normalized and raw hashes, their owning payload or renderer,
the paired closures and the old/new checker hashes. Every candidate input was
matched to the generated inventory; payload bytes were also matched to their
current owning source. All changed tracked payload inputs have a HEAD baseline
already registered by v20; the installation-calibration interface is new.

The complete source diffs are retained in `unreviewed_input_git_diffs.txt` and
`mag_core_git_diff.txt` in that task directory. Review was against the actual
code, compiler `.d` files and linked artifact. The first successful task-stack
report must come from the emitted `make stack-report`, not a diagnostic script
which skips input verification.

## Reviewed changes and contracts

| Inputs | Review and consequences |
| --- | --- |
| `system_mag_calibration.c/.h` | Four bounded entries, independent candidate and committed packets. Quality, finite values, determinant, CRC, sequence and active source checks precede publication. APPLY is absolute replacement; SAVE completion publishes only its matching request; failure restores committed runtime state while retaining a retryable candidate. No heap, new callback or recursion. Entry snapshots use existing critical sections. CPU-only state moves to zeroed CCM without changing capacity or automatic frames. |
| `system_installation_calibration_if.h`, `system_mag_calibration_storage_if.h` | Versioned scalar constants and direct typed interfaces. New envelope carries schema/kind/algorithm/convention and descriptor/instance/config/driver/model identity. No manufactured IMU group or relative rotation result. Old unbound records cannot silently acquire a current identity. |
| F4 `mag_calibration_storage.c` | Bounded one-record load/save service; ordinary card/storage/input errors remain nonfatal. Save uses atomic dual-slot operation and exact readback before successful completion. Internal completion and load-fault results are checked; an impossible descriptor/request transition enters the established terminal assertion path. Both were demonstrated red/green with distinct fault injections. The 116-byte envelope is CPU-only CCM; the independent 530-byte storage record remains main SRAM before filesystem/DMA access. F1 carries the same source fix but this candidate's linked proof is F4 only. |
| `persistent_storage.c` | Metadata chooses a slot, then the selected slot is reread into the existing storage record and length/generation/CRC are revalidated. Removal/corruption between reads is VerifyFailed. No large replacement automatic buffer. Opposite-slot atomic write/sync/readback and bounded two-slot policy are unchanged. The reread also affects mission snapshot readers, covered by full Host regression. |
| `logger_task.c`, `serial_task.c` | Maintenance storage service runs before logging-disabled/no-session/finalized early returns. Compile-exclusive SerialTask fallback when logging is absent preserves a single filesystem owner. No new task or mutex bypass. Logger bootstrap may close a diagnostic log without a flight-ready mission snapshot; owned queues drain, flush and close before ready publication. |
| `logger_bus.c/.h` | Bounded maintenance bootstrap draining is accepted in addition to streaming-ready. Existing queue capacities, critical sections and admission lock remain. No dynamic ownership or callback registry. |
| `system_console.c`, `debug_log.c` | Existing fixed buffers reserve CR/LF and reject oversized/failing formatted output. Console asynchronous data uses an owned bounded static frame and the existing transactional whole-frame write. Debug output is explicitly best-effort; failed whole-frame publication is not reported as a sent prefix. No new indirect calls. |
| UART console driver/adapter | Uses existing atomic WriteFrameAsync rather than partial-write publication; dropped-byte counters saturate with existing critical ownership. No new HAL callbacks or queue growth. |
| `system_log_file.c` | Response mailbox is copied under its lock with explicit capacity failure. The checked bounds govern the copy. No additional filesystem execution context. |
| JY901B driver/MAG adapter | Explicit B/S gain and profile selection, bounded 100 ms stale limit; unverified 0x54 temperature removed. Absolute vector qualification remains zero. No new callback targets. Physical B/S revision remains a hardware identity limitation, not proved by software configuration. |
| `vector_constraints.c/.h` | Exact hashes match `.work/0.1.3-initial-alignment-20261017/validation_summary.json`. Existing review covers a direct acyclic helper graph, at most six observations/fifteen pairs, dimensions 3/4 and sixteen SVD sweeps; finite/norm/rank/reflection/nonconvergence checks precede complete output publication. Caller retains ACCEPTED versus READY separation. Numerical oracle: 2,890 cases. Its host timing is not MCU WCET. Linked helper/call frames must still pass this candidate's stack gate. |
| `system_user_config.h`, `system_version.h` | Fixed build/maintenance flags and identity strings; no new function-pointer policy. Version text alone is not evidence of matching firmware. |
| Generated flight/config/capability/instance/resource headers and device-instance source | Compared with the fresh production renderer and hardware inventory. Static MAG facade dispatch uses selected instances; board pins and physical endpoints remain equal to the preserved comparison projects. Descriptor/config identities intentionally change with configuration. Architecture check covers source graph and capability closure. No manually inserted runtime dispatch. |
| Generated metadata/decoder/log-config sources | Generated fixed tables and bytes bound to this configuration and decoder; no dynamic callback or executable plugin import. Existing SSLOG framing/schema is unchanged. Historical MAG reproducibility still requires a future full snapshot companion; latest TF slots alone are insufficient. |

## Unchanged proof policy

AST comparison preserves every checker function except the two registration
lookup functions, every previous registration and all nonbinding policy values.
The minimum task margin and context allowance remain 256 bytes each. No stack
capacity, library-frame rule, recursion rejection, dynamic-frame check,
indirect-call recognition or named callback exception changes. Existing HAL,
FreeRTOS, FatFs and library provenance/exceptions remain in scope as before;
their source coverage is not erased.

The final validation exercises the real candidate inputs and rejects a changed
source, changed included header, changed dependency graph, and a mixed tuple
containing an individually registered old header. The candidate is never
mutated for these fault tests. Historical v19/v20 fixtures remain executable.

## Explicit limits

This review covers the changed contracts and exact compiled task-call inputs.
Whole-firmware critical-contract acceptance, complete MSP/main/ISR nesting,
measured task high-water margins, STM32 WCET, navigation accuracy and flight
qualification remain **NOT PROVEN**. The existing checker reports that limit
even if its scoped task-budget gate succeeds. The 108-byte linked main-SRAM
budget headroom is a resource observation, not a stack or timing proof.
Any flash under the user's separate authorization is a development candidate,
with no START/flight/actuator test implied.
