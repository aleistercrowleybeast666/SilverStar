# Logger snapshot request contract

Baseline: 24aa71195df1c566f1b8b998ce8b5bd996b4b96f. Logger bus and FlightTask
blobs equal those at 7fa06c4 and 34bbd38. No SSLOG schema, codec, algorithm,
normal queue capacity or producer cadence changes.

The previous capacity precheck did not reserve slots: a producer after the first
SYSTEM_CONFIG could leave an incomplete batch. Entire capacity rejection also
did not advance overflow diagnostics. The new single request slot accepts a
bounded snapshot independently of the ordinary queues. BUSY means retryable
request admission, with no published records and an admission capacity_reject_count;
FULL remains ordinary queue data loss with existing sequence-gap accounting.

The claimant owns BUILDING and copies config and all stream policies, including
disabled streams. The policy copy holds one bounded lock over 40 small configs;
the record batch is constructed outside locks. Generated device/algorithm
descriptor tables, mission parameters and estimator profiles are immutable.
READY publishes the complete request under a short lock. LoggerTask alone pops
it in order. No producer holds an IRQ lock over batch construction; no heap or
batch-sized stack array is used. Pop and NextPop are single-consumer operations.
Reset requires quiescent producers/consumer, as for the existing queues.

FlightTask captures timestamp and initial/mission/calibration identities once,
then retries admission each bounded task iteration. Successful admission copies
the payload. Repeated accepted generation tokens do not recopy caller data or
duplicate records. The logger emits complete config metadata followed by mission
config, mission identity, all configured magnetic identities, initial state and
MISSION_START. The last record leaves BARRIER pending until successful aggregate
write and sink flush. This prevents continuous producers from delaying START
sync indefinitely. Acknowledgement is internal and does not change AIR READY,
START ACK or lifecycle/navigation decisions. The established no-storage boot
path suppresses requests and keeps nonblocking startup.

Write/sync faults remain latched ordinary storage errors. They retain an
unacknowledged faulted request and prevent overwrite/false durable success;
they do not roll back an already committed flight or claim MCU recovery. This
does not repair media damage or replay a partial write.

Tests include fault injection into the original generated baseline, complete
descriptors after preemption, capacity-independent admission, copied START
ownership, duplicate token handling, busy admission, flush barriers under
producer traffic and sync failure. The compact test uses an explicitly
synthetic shadow configuration (8 normal / 4 estimator slots); production
generated configuration is preserved.

Manual acceptance remains NOT PROVEN pending independent review. Host timing,
ARM linking, scanner success and static RAM delta are scoped evidence; IRQ
latency, actual stack margin, hardware storage behavior and flight qualification
are not established by these tests. Preserve all failed/intermediate run logs.

New state is grouped into two CPU-only owned objects and uses the target's
existing PLATFORM_CPU_FAST_BSS placement. Neither object nor any interior
pointer goes to HAL/FatFs/DMA/sink interfaces. Targets lacking that section use
ordinary BSS. This is RAM placement, not a resource-budget exemption; total
and per-region deltas must remain explicit in the evidence.

The baseline producer hook uses a non-LTO build: LTO can inline the queue push
and bypass the linker wrapper. START tests use LTO to discard unused RTOS task
loops and also inject after the first consumed configuration record. Keep these
two recorded scopes distinct. Final Debug artifact checking preserves the
baseline's 28-byte main-SRAM budget violation; it is not converted to PASS.
