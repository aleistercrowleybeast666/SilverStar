# Ground bounded backpressure repair — 2026-10-09

The shared four-frame PC queue previously treated normal congestion as `GROUND_BRIDGE_PC_ERROR`. Three independent pre-fix Host cases reproduce this: USB never configured reaches the error after four synthetic seconds; five valid eight-byte commands can publish five radio commands before their fifth ACK fails; and four radio frames can fill the queue before a due periodic status attempts a fifth entry.

The daily checkout at `253edffb0b88ce0e10d59887d09333e6fa798f90` has the same bridge implementation. Its F1/F4 generated main ignores the Process result, so the confirmed consequence there is failed ACK/status publication, not a demonstrated terminal fault. The separately reviewed C071 main checks the result and enters its fail-stop handler. This repair changes the owning Ground plugin; it does not change either main-loop error policy, Flight, the GUI, or the user's manual-test checkout.

## Repair and contracts

- PC input is read one byte at a time only while one queue slot remains available for the resulting ACK. A complete command therefore has an ACK slot before radio publication. Main is the only queue producer; transport reset IRQs invalidate sessions but never allocate these slots. The existing session critical section still protects command publication.
- Each Process call still consumes at most 64 PC bytes, dequeues at most four radio packets, and makes at most eight transport write attempts. Queue depth stays four. No heap, retry loop or larger receive buffer was introduced.
- Periodic status is coalesced and deferred while full; one due status gets a slot before radio receive publication when available. Sustained PC command load can still defer status. Input-backpressure and status-deferred counters expose this behavior and saturate.
- Real write errors still return `GROUND_BRIDGE_PC_ERROR`; unexpected internal capacity failure remains an error. No published command ACK is silently discarded because the queue was full. Explicit session reset still cancels old queued/in-flight frames and unread input; ACK delivery across reset is not guaranteed.
- Finite transport rings retain their existing overflow policies. A peer that sends indefinitely while not receiving can exceed bounded storage; the bridge does not promise lossless unlimited traffic. The peer must pace outstanding commands.

## Executed evidence

Fresh outputs were generated from the current owning source into `%TEMP%/ssbackpressure-run1`, using existing immutable CubeMX snapshots from `usb-validation/dep9`. The exact emitted `make -B -j2 all architecture-check host-tests artifact-check power10-check static-analysis` ran for F103 USB, F103 UART and F407 USB; all three complete invocations exited zero. These include actual ARM release/analyzer compilation and linking, source/dependency/vector checks, and Host tests. No generated firmware was patched to obtain these results.

The scoped backend suite completed with **162 passed, 1 deselected**. The deselected historical mixed BMI088/SD interface-conflict test and the three GUI-owned files excluded from this backend scope are listed in the JSON. This is not a claim of a full monorepo-suite pass.

The shared asynchronous transport contract and actual USB adapter execute nine scenarios each: 60,000 synthetic seconds without connection; five-command burst; four radio frames coincident with status; 10,000 slow-transmit turns with twelve commands; 1,000 ACKs with 800 radio frames; 100 partial-frame reset cycles; queued session cancellation; 64-byte budget; and a real write-error result. Tests retain the transport's asynchronous TX pointer and verify its bytes until completion. Existing USB, DMA UART, radio and session tests also run. The common UART pressure mock is a contract model; separate C071 validation runs these scenarios against its actual IT UART adapter with mocked HAL.

Pre-fix compilation succeeds, and the same three pressure regressions reject the old bridge at their expected error-counter assertion. An early new-fixture attempt had strict conversion-warning setup errors; the explicit cast corrected the fixture. Complete failure logs remain in the evidence, alongside the later successful runs.

Machine-readable index: [backpressure-repair-summary.json](ground-usb-evidence/backpressure-repair-summary.json). It records full commands, timestamps, tool versions, exact dirty source snapshot, fresh generated inputs, ELF/BIN/MAP and dependency/stack-artifact hashes, gate logs and warning details. The auditable base is `dfaad79ee361879df70f57ba3af034e897c1602e` plus the five explicitly listed source files. Uncommitted C071 adaptation files and its separately authorized PoT registration are outside this common-fix batch.

## Remaining evidence boundary

`POWER10_CONTRACT_REVIEW|NOT_PROVEN` remains present. Gate success is not original Power of Ten compliance, completed critical-contract review, whole-program stack/WCET proof or hardware qualification. Synthetic time is not measured MCU time. USB enumeration/ZLP/physical disconnect, UART hardware latency and actual radio operation remain subject to hardware validation. The C071 permanent-main exception is separately recorded and does not authorize other loops or relax other rules.

No hardware, serial/probe, EDA, FINAL, daily checkout, remote push or publication actions were performed.
