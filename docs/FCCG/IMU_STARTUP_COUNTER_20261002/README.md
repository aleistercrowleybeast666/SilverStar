# JY901B startup counter checkpoint, 2026-10-02

Base 492f30880e9936a7b72091b14354a21b32af33c4. Independent branch fix/imu-startup-20261002. No firmware changes, UART/COM/DAP access, flash, merge or push in this checkpoint.

## Actual generated Host counter

Fresh paired project uses the actual RadioRuntimeFaultHotfix post Flight_Controller/SilverStar.ssproject, with only candidate project name changed. The driver, startup, F4 UART and resource/task declarations match the burned source as raw bytes (raw_source_proof.json). Host includes the real generated jy901b_device.c translation unit and normal platform mock. Automatic mock register replies are disabled. Each case zeros the actual static driver context to model MCU BSS startup, then calls actual reset/init/start/poll operations. Injected backlog is 143 bytes, below the real UART1 511-byte usable RX capacity.

Accepted baseline: compile_v2.log exit 0 with C11/O2/Wall/Wextra/Werror/pedantic, old_counter_v2.log exit 1, 26 checks and 4 failures. This is expected pre-fix evidence, not a passing gate.

1. Normal IMU_Poll twice during an active register read leaves a complete reply available for actual AsyncPoll. Guard/isolation case passes. Ordinary IMU_Poll stealing the reply is not supported by this counter.
2. A checksum-valid acceleration frame `55 51 00 00 00 00 00 00 55 5F 5A`, immediately followed by checksum-valid register reply `55 5F 07 00 00 00 00 00 00 00 BB`, loses the reply. Old parser starts its candidate at acceleration payload bytes 8/9 and consumes the next reply's header inside that false candidate. After invalid checksum it preserves only a final 55 byte, so the real reply header is lost. At end frame[1]=5F, index=0, active=1. Two checks fail (Complete and returned 7).
3. At start=109ms, queue 12 valid acceleration frames plus reply at 708ms. First AsyncPoll consumes 64 bytes and stays Pending; second at 709ms consumes another 64 bytes and returns Timeout although the reply remains queued. frame[1]=00, index=0, active=0. Two checks fail. Deadline remains exactly 600ms.
4. With no response, Pending at 599ms and Timeout at 600ms pass; output sentinel stays unchanged.

First v1 counter log is preserved, but its normal frame checksum was 5C instead of 5A and context persisted between cases. It is INVALID as legal-frame/BSS evidence. Only v2 above is accepted. Initial generation attempt used the nonexistent parent directory ssproject path; corrected path is explicit in generation_command.py. No nonexistent-path failure counts as a test.

## Relation to hardware

Hardware retained state: USART1 230400, first BAUD 04 read started 109ms and failed at 709ms; TX FF AA 27 04 00, no UART transport errors, normal IMU frames continue. No raw RX from this window is available. It is not established that a reply never arrived, that TF caused the fault, or that either counter occurred on hardware. Overlap counter ends with frame[1]=5F and differs from hardware 00; backlog counter has matching retained 00, but this alone does not establish its trigger. Scheduler/RX history is still missing.

Adapter Baro/Mag/Quaternion synchronous VerifyConfig routes exist. Their ConfigAccessCheck checks runtime_owner_active, not register_read_active; startup sequencing and actual callers still need full review before excluding every other reader. This checkpoint excludes only ordinary guarded IMU_Poll, not all possible concurrent operations.

## Proposed narrow correction for review

Keep CRC and 600ms deadline. Consume complete checksum-valid normal frames without scanning their payload for register headers; retain bounded suffix/header candidates after a malformed frame so a valid subsequent reply is not swallowed. Drain a fixed bounded number of 64-byte chunks before testing timeout, using the existing bounded normal processing limit, no RX buffer expansion. Run fragmentation, checksum rejection, mixed normal/reply, queued-before-deadline, no-reply, initialization and full startup read/write/verify regressions. This is a proposal, not a patched or validated binary.

If parent requires hardware discrimination, first-read-only fixed-capacity diagnostic trace remains appropriate: DMA-before-ring candidate observation across blocks, full 11-byte candidate/checksum/time, TX enqueue and real DMA start/end, discard/reset and actual poll result, freeze at first completion. Do not add output traffic or change consumption/deadline/readiness. No 2KiB trace has been implemented or its overhead measured in this checkpoint.

## Limits

ARM, full Host, analyzer, architecture, PoT, artifact and resources were NOT RUN for a repair; no repair ELF/BIN exists. Static critical-contract, hardware timing/stack and flight qualification remain NOT PROVEN. Parent can review the exact original function source and these accepted counter logs before authorizing the next focused patch/diagnostic decision.
