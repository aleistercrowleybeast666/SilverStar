# NRF24 paired transport: isolated source checkpoint, 2026-10-06

This is an incomplete integration checkpoint for parent review. It is not a
release candidate or hardware qualification. Baseline is
`cd76d8e0c8ccddb28e823e0f6ab6d47613276f51`; branch is
`feature/nrf24-pair-20261006`. No daily tracked files, FLP/GSHC branch, user log,
recorded dataset, decoder package, hardware or remote branch was modified.

## Implemented scope and boundaries

The declarative NRF24L01+ plugin contains its own register driver, portable
fragment codec and existing SystemTelemetry adapter. SCG accepts one NRF pair,
five-byte address, 250/1000/2000 kbps, integer MHz channel 0..125, documented
chip power levels, CRC16 and bounded retries. NRF-specific UI rows replace the
displayed LoRa rows. Persisted legacy outer AIR fields remain readable but are
not interpreted as NRF settings or emitted as fake LoRa macros. New configs
with `nrf24` require this SCG revision; compatibility with old readers is not
claimed. SX remains the default and its emitted AIR/Ground bytes are compared
directly with the clean baseline.

The required resources are SPI, CSN, CE and time. This backend polls STATUS/FIFO
from its owner and has no IRQ/EXTI handler or IRQ resource requirement. SPI
transfers contain at most 33 bytes and use a 2 ms timeout; radio startup, CE
pulse, TX completion and retry recovery are owner states. The fresh software
fixture changes the imported radio RESET pin to a low-idle CE output; it is not
a verified board wiring or a substitute for physical inspection. CSN/CE are
distinct and SPI is mode 0/MSB first, 500 kHz..10 MHz. No SX RESET/BUSY resource
or LoRa bandwidth/spreading parameter is fabricated.

The physical MTU is 32, the logical MTU is at most 61, and the existing M0 maximum
FLIGHT_STATE remains 50. `contracts/nrf24_fragment_v1.json` describes the ten-byte
versioned envelope and 22-byte chunks, up to three fragments, CRC16/CCITT-FALSE,
250 ms assembly and duplicate windows. Only complete, CRC-checked frames are
published. Length/CRC conflicts, inconsistent duplicate chunks, bad DPL width,
loss, timeout, and busy completed receive storage have bounded ordinary paths.
Control has priority between complete frames; it cannot preempt half a frame.
Hardware TX_DS for every fragment is required for a receipt. Receipt success
does not assert business ACK or readiness. MAX_RT and TX timeout flush retained
TX FIFO payload, clear status and abandon the frame. Recovery drops queued
commands and does not replay them.

Two pre-fix failures are preserved: peer reboot with repeated volatile tag and
low sequence was suppressed indefinitely; repeated missing-device recovery
consumed session identity and trapped after 65535 attempts. Duplicate history
now expires after 250 ms. Failed recovery preserves the allocated TX sequence;
it does not consume a new session and still retries in bounded rounds. The
65537-round Host case then reconnects successfully. Neither fix proves replay
protection across MCU reboot.

## Shared contracts awaiting explicit user approval

Ground production generation deliberately reports
`GROUND_NRF24_METRICS_CONTRACT_PENDING`. Ground runtime routing/adapter is not
implemented, and no NRF Ground firmware is represented as generated or linked.
The old direct LoRa Ground runtime remains intact. Driver portability on F103,
paired business handshake, live CMD/ACK, Ground congestion and complete F103
link acceptance remain NOT PROVEN.

GSP AIR_RX currently encodes signed RSSI, signed SNR_Q4 and length in three
bytes. It has no unsupported value or backend identity. NRF's RPD bit is not
RSSI or SNR. The proposed minimum is a jointly specified unavailable pair
`(127,-128)`, decoded to nullable values, plus an optional versioned radio
capability/identity message advertising backend and metric availability.
Do not select a message ID until the shared contract inventory is reviewed.
Keep SX AIR_RX and GS_STATUS bytes unchanged. A configuration-bound client is
an alternative, but must carry trustworthy current backend information through
logs; a UI guess or offline default is insufficient.

Existing GSHC `GspParser.feed` accepts a CRC-valid arbitrary message type and
`parse_gsp_frame` returns None for unknown types. This establishes that parser
behavior only, not compatibility of every deployed client/controller. Old
clients still interpret the unavailable AIR_RX pair numerically, so ignoring a
new identity message alone does not make the sentinel backward compatible.
SNR_Q4=-128 alone is a valid SX -32 dB measurement. RSSI+127 is not produced by
the current SX decoder but is permitted by the historical signed-byte GSP
contract; absence of historical pair collisions is NOT PROVEN.

Minimum reader impact: GSHC nullable packet metrics; explicit clearing of GUI
state on unavailable values (current event handling otherwise retains stale
metrics); AIR_RAW/AIR_PARSED nullable persistence; and the GSHC log exporter's
raw-GSP fallback, which currently would recreate numeric 127/-32 link samples.
Skip unsupported link samples without changing M0 fields. No GSP, GSHC, GUI,
FLP decoder or immutable recorded data has been changed here.

Full F407 compilation also fails in the storage plugin's
`MissionSnapshot_AirProfileWrite`: schema-2 SSMS section 0 places a fixed 15-byte
LoRa profile between calibration identity and alignment fields. It is not a
TLV. The external PersistentStorage CRC32 covers the 14-byte header prefix plus
payload; snapshot section hashes use FNV1a; normal atomic slot/bank generation
rules still apply. Removing storage is rejected by STORAGE_DEVICE_REQUIRED.
No fake LoRa macros or gate exception is supplied to bypass this failure.

Proposed minimum extension: retain SX schema-2 bytes exactly; use SSMS schema 3
for NRF section-0 only, with a typed versioned length-prefixed opaque NRF profile
at that position. Proposed tag/version/length header is 1+1+2 bytes, and payload
is 14 bytes: channel, rate code, signed chip power, five address bytes, retry
delay code, retry count, CRC mode, physical MTU, logical MTU, envelope version.
Unknown schema/profile tags must be rejected or preserved opaquely, never
interpreted as LoRa. Recompute normal section hashes/outer CRC and preserve the
atomic write policy. This is a proposal, not an implemented/approved format.

Repository FLP consumers currently read SSLOG record 0x29 version 1 (24-byte
MISSION_SNAPSHOT_IDENTITY), not this SSMS profile payload. That record need not
change for the proposal. Host storage readback expectations and any external
SSMS parser still need schema-3 review, compatibility fixtures and reader
inventory. Unseen downstream tools are NOT PROVEN. Production FLP's exact
Descriptor/.ssdecoder and LogOpenCoordinator rules continue to apply.

## Integrity and command limitations

A preserved counterexample gives old, new and mixed 50-byte datagrams with equal
CRC16 and reused session/sequence/length. The actual C reassembler accepts the
mixed complete frame, as CRC16 cannot distinguish that collision. This is an
explicit limitation, not a PASS for collision resistance. Current M0 CMD is
nine bytes, so it fits one fragment and cannot itself be chunk-mixed. A delayed
whole old CMD can still reappear after the duplicate window or peer reboot.

The unchanged M0 TelemetryService compares all CMD wire fields in its finite
ACK cache, expires entries at four seconds, and clears the cache on a newer
Capability handshake. It also retains pending-start and lifecycle/state gates.
Those mechanisms do not prove permanent command anti-replay or unique boot
identity. This checkpoint changes no command token, sequence, handshake or ACK
semantics and adds no automatic business retransmission. Complete paired
business acceptance remains NOT PROVEN.

## Gate revision and evidence scope

Parent explicitly authorized backend-aware architecture checks on 2026-10-06
in thread `01a0f0e9-0660-751e-be43-e88f257f5014`. The original SX-specific scope,
context-bound and Semtech callback rules remain on the SX path. Both selections
now cross-check saved/semantic ownership, generated AIR header family, uniquely
selected driver source and absence of the other backend. NRF requires its
actual Inc/Src/Adapter directories, all three C sources, one owner and generated
SPI/CSN/CE/time bindings; missing/unknown selection fails. NRF receives the same
portable/platform/runtime rules and a corresponding indirect-dispatch check.
No Power10 threshold, source exclusion or allowlist is changed.

The package manifest identifies the exact source commit and SHA256 of sources,
generated inputs and retained artifacts. Complete logs include abandoned test
fixtures, original architecture failures, actual pre-fix failure/after-fix
tests, Windows path-length fixture failure and full build failures. Selected
Host regressions are not represented as an unexecuted full-suite pass.

Actual F407 ARM object compilation and `-fanalyzer` compilation use the fresh
generated Makefile's strict flags. An intentional double-free canary fails
with an analyzer diagnostic to establish real analyzer execution. Object BSS
and `.su` values are object-level evidence only; no successful firmware link,
whole-program call graph, task/ISR/MSP stack margin, target WCET, radio range or
flight qualification is inferred. Full firmware analyzer/link/artifact/stack
acceptance remains blocked by the stored AirProfile contract. Linked middleware
and indirect paths therefore remain NOT PROVEN rather than removed from scope.

The original emitted Power10 checker continues to print critical-contract
review NOT PROVEN even on successful text-check exit. Recommendations retain
the F Prime-inspired project adaptation; no original Power-of-Ten compliance
or NASA certification is claimed. All hardware evidence is
**HARDWARE_UNVERIFIED**. No hardware action, merge, publish or push was performed.

Specification source: Nordic nRF24L01+ Product Specification v1.0,
<https://docs.nordicsemi.com/r/bundle/pdf_ps_nrf24l01p/>; vendor-authored PDF mirror
<https://cdn.sparkfun.com/assets/3/d/8/5/1/nRF24L01P_Product_Specification_1_0.pdf>.
