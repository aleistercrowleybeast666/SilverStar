# Alignment evidence admission and storage contract

The ordinary 7000b5c path suppresses ALIGNMENT_EVIDENCE during BOOT despite an
enabled mandatory stream. Push returns OK with zero admission; FlightTask's
terminal-state marker prevents later emission. The real FlightTask event writer
and LoggerBus host reproduction records this failure before correction.

Only ALIGNMENT_EVIDENCE is added to the existing BOOT allowlist. Raw/preflight
data filtering, ordinary queue sizes, policy, wire layout, alignment algorithms
and lifecycle decisions remain unchanged.

FlightTask owns one bounded copied evidence and its original capture timestamp.
FULL or BAD_STATE retains it for a later task iteration. Retry precedes a new
alignment terminal event, so a later snapshot cannot overwrite a rejected first
evidence. Queue admission clears the pending copy once, and unchanged terminal
status does not duplicate it. Existing event/result emission is unchanged; this
fix does not claim reliable delivery of every preflight event or every historical
alignment transition. Disabled-no-storage boot retains intentional suppression
and nonblocking startup.

A changed alignment start_sequence invalidates only the logging state marker,
so a second READY generation emits its evidence even if the preceding generation
also ended READY. A retained older evidence is admitted before processing that
new generation. Lifecycle/alignment readiness and algorithms are unaffected.

Queue OK means admission, not durable storage. Evidence now uses the existing
critical aggregate flush deadline and empty-queue flush. The deadline is not
extended by ordinary traffic. Actual write/sync errors latch logger io_fault and
close the session; no uncertain partial write is replayed and no durable-success
acknowledgement is fabricated. Existing storage readiness checks reject io_fault.
Admission to a latched failed writer is rejected specifically for evidence under
the queue lock; the FlightTask retry copy remains pending. A test-only quiescent
Reset can clear the logger fault to check retained ownership; this is not target
firmware I/O recovery or permission to replay uncertain writes.
The bounded host tests cover both successful flush and failed sync. Hardware
storage latency, main/MSP/ISR stack bounds and flight qualification remain
NOT PROVEN. Preserve the existing Debug28B budget FAIL and original gate rules.

The copied state is CPU-only PLATFORM_CPU_FAST_BSS, never a DMA/FatFs buffer.
Record the new per-region map delta relative to 7000b5c. Validation reuses the
owned disposable generated project with explicitly recorded revisions/hashes;
no user project or stable working tree is regenerated.
