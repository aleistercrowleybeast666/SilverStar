# NRF24L01+ pair checkpoint 1 — 2026-10-06

Base: cd76d8e0c8ccddb28e823e0f6ab6d47613276f51. Isolated branch
`feature/nrf24-pair-20261006`; daily checkout has three pre-existing untracked
inventory files, no tracked changes. No merging, pushing or hardware action.

## Implementation boundary

New declarative device plugin owns first-party NRF24 driver, fragment codec,
static transport queues and Flight adapter. SPI mode 0, CSN output inactive high,
CE output inactive low, monotonic time, optional falling-edge IRQ flag. No
SX128x RESET/BUSY or LoRa PHY fields are consumed by NRF24.

Physical payload maximum 32 bytes; logical packet MTU 61 bytes (GSP wrapper
uses 3 of 64 bytes). AIR M0 maximum 50 bytes and every M0/CMD/ACK byte remain
unchanged. Fragment envelope lives below AIR codec, with magic/version,
session, sequence, total length, fragment index and whole-frame CRC16.
One pair only, no mixed-family failover or multi-node addressing.

Owner state machine does bounded SPI operations and handles all radio waits.
ISR records a flag only. TX receipt follows all fragments' TX_DS, never enqueue
or a hardware ACK interpreted as a business ACK. Failure discards the current
logical frame; business commands are never automatically replayed. Recovery
continues indefinitely with bounded individual attempts. Static control/data
queues allow control priority between complete logical frames.

Reassembly publishes only a complete, validated frame. Duplicate fragments,
out-of-order fragments, metadata conflicts, missing packets, timeout, wrap and
restart are explicit cases. Session tags are not authenticated and volatile
boot time is not a unique persistent boot identity: adversarial/delayed replay
across restart is NOT PROVEN. Existing AIR session negotiation remains the
business authority.

## Expected affected files

- New `plugins/builtin/silverstar_device_telemetry_nrf24l01p/` payload/manifest.
- SCG manifest radio validation, AIR link model/validation/header renderer,
  radio variant resolver, Ground renderer/source graph routing.
- Focused Host SPI/register/fragment tests and SCG generation tests.
- Documentation and small versioned evidence directory.

## Contract decision requested before crossing GSP/GSHC boundary

GSP AIR_RX and GSHC have no unsupported RSSI/SNR sentinel. Proposed minimum:
retain layout and reserve RSSI=127, SNR_Q4=-128 as unavailable; parser maps to
None. Old clients display misleading numeric values, requiring paired client
update. No GUI layout or AIR profile changes. Pending explicit decision;
independent driver/fragment work proceeds.

## Acceptance scope

Use existing F407 Flight/F103 Ground toolchains, fresh small generated projects.
Retain failures and logs. Execute emitted Power10 gate, Host regressions,
actual GCC analyzer compilation, ARM compile/link and affected source graph,
memory/stack reports. Tool PASS does not complete critical-contract review.
HARDWARE_UNVERIFIED; no inherited LoRa distance, timing or flight qualification.

Reference: Nordic nRF24L01+ Product Specification v1.0 (September 2008),
https://docs.nordicsemi.com/r/bundle/pdf_ps_nrf24l01p/ ; vendor-authored PDF mirror
https://cdn.sparkfun.com/assets/3/d/8/5/1/nRF24L01P_Product_Specification_1_0.pdf .
