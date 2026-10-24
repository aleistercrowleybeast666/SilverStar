# E32-400M20S / SX1278 experimental SPI payload

Status: **EXPERIMENTAL / HARDWARE_UNVERIFIED / shared generation integration pending**.
This is independently authored SilverStar code. No Ebyte or Semtech driver source
is copied, adapted or linked. Existing SilverStar telemetry interfaces are reused.
Repository license policy applies to the new source; document links confer no
vendor code license. No vendor example ZIP is included.

## Admitted profile

One explicit `e32_400m20s` instance, 433 MHz, 32 MHz reference, SF7, BW125 kHz,
CR4/5, 16-symbol preamble, explicit header, payload CRC, private sync word 0x12,
ordinary IQ, 61-byte packet bound, normal PA_BOOST +17 dBm chip setting.
The module's marketed +20 dBm capability is not enabled. No UART E32, SX1276
868/915 MHz, E19, M30S/M33S, hopping, CAD, FSK, ranging, mixed-family failover,
multiple instances or arbitrary radio combinations are admitted.

The generated catalog uses the existing `validated_frequency_*` schema fields to
express this software-admitted interval. These field names do **not** mean this
new profile has been measured or hardware validated.

## Module wiring boundary

Use a regulated **3.3 V supply and 3.3 V IO**. Never use 5 V supply or TTL for this
profile. Module pins: RXEN 6, TXEN 7, VCC 9, DIO0 18, active-low RST 19, MISO 20,
MOSI 21, SCK 22, NSS 23, ANT 25; all specified GND pins connect to ground.
DIO1 pin 17 and DIO2/3/4/5 pins 8/13/14/15 are unused by this backend. SX1278
has **no BUSY pin**. DIO0 maps RX Done in RX and TX Done in TX; the platform ISR
only records an edge. `Process` consumes that hint and also polls flags so a lost
edge is not a permanent wait. No SPI occurs in EXTI, Init, Start, Stop or Send.

NSS is mode-0 active-low, MSB-first, 8-bit blocking SPI, 0.5–10 MHz. RXEN and TXEN
are mandatory independent push-pull outputs, initially low. The module RF switch
uses RXEN high/TXEN low for receive, the inverse for transmit. Both are first
driven low before selecting a direction; failed GPIO operations revoke READY and
attempt reset. Software cannot prove that a failed physical output changed level.
RST uses open drain with pull-up so high releases the reset line, consistent with
the Semtech reset/POR instructions. The driver measures from completion of the
GPIO operation and uses 2 ms/6 ms tick guards. One tick of quantization still
leaves at least 1 ms low and 5 ms after release before SPI.
The caller must provide stable power before Start;
POR rail sequencing and the first power-up interval still require bench evidence.

The current Chinese manual has 1.8–3.6 V in its table/pin section but 2.5–3.6 V in
its overview. English manual 3668 has incompatible 3.3–5.5 V and 1 W overview/pin
text alongside a 1.8–3.6 V, 100 mW parameter table. The website also has different
typical/max power tolerance values. This implementation adopts the common 3.3 V
operating point only; those vendor contradictions remain for vendor confirmation.

## Runtime boundaries

`sx1278_chip` owns register/FIFO transactions; `sx1278_device` owns module reset,
RF switch, queueing and lifecycle. Only one task may call Process. Init/Start/Stop
are asynchronous requests; an accepted Start is not READY and an accepted Stop
requires Process to perform physical quiescence. Stop is latched across a later
Start; old work is discarded before that restart. `Sx1278_StopStatusGet` reports
Busy until the owner confirms quiescence and preserves IO failures. The Flight
adapter returns SYSTEM_DEVICE_BUSY until confirmation, never early successful
Stop. Parent integration must keep the owner running during cleanup; the existing
source selector retries Stop without servicing this asynchronous owner.
Concurrent callers use platform
critical sections for requests, bounded queues, receipts and published health.

Each SPI call has a 2 ms timeout and an attempted NSS release on failure. Startup
uses a fixed 23-register verification table plus reserved-bit-preserving detection
setup (64 bounded SPI transactions including RX start). Mode writes are read
back, and running processing checks the mode bank before interpreting IRQ flags;
an uncommanded reset revokes READY. RX processing uses at most 19 transactions
when followed immediately by TX, or 16 when resuming RX; an ordinary TX start uses
at most 11. A delayed read across an autonomous mode transition may conservatively
fault; MCU scheduling remains unproven.
These counts are software bounds, not STM32 WCET or scheduling guarantees.
There are two control and two telemetry queue slots, two RX slots and four
terminal receipts. Control has priority; expired queued data cannot be hidden
by it. Queue lifetime is 1000 ms; expiry faults the current session and discards
unstarted work. IDs never wrap and alias retained receipts; exhaustion requires
an MCU restart. Every TxDone is polled, and a completion at/after the 250 ms TX
deadline is a timeout. Queue expiry is checked before IRQ processing so repeated
nonterminal flags cannot hide expired work. A Stop accepted before receipt
publication prevents a late successful receipt. SPI timeout, malformed packets, bad CRC and full queues
retain ordinary error paths. Impossible queue indices/lengths and state enum
values use the established terminal assertion trap.

Maximum packet airtime for this fixed PHY is 121.088 ms using the Semtech formula.
RX uses a 150 ms platform-tick window between sends to permit a complete reply. This is an
experimental half-duplex scheduling choice; peer startup symmetry, collisions,
command latency and actual duplex delivery remain unmeasured. Recovery waits
1000 ms, resets/reconfigures, and never replays discarded control/data work.
RX packet extraction enters standby and re-reads IRQ flags before checking header-reported CRC presence
as well as CRC error. No RSSI/SNR claim is exposed by either adapter.
Health timestamps retain the platform's 64-bit microsecond epoch. Diagnostics
publish aggregate transport errors/timeouts; per-SPI fault attribution is not
claimed because the path also includes module GPIO and mode-readback errors.

## Primary references and register interpretation

- [Ebyte product and pin table](https://www.ebyte.com/product/1673.html).
- [Chinese E32-400M20S product manual](https://www.ebyte.com/downpdf/1673.html),
  downloaded 2026-10-15, copyright 2012–2024, 13 pages.
- [English manual 3668](https://www.cdebyte.com/pdf-down.aspx?id=3668), retained
  solely to document the contradictory supply text.
- [Semtech SX1276/77/78/79 Rev. 7, May 2020](https://www.ebyte.com/pdf-down/2879.html),
  vendor-hosted original Semtech document: pp. 30–41 explicit CRC/FIFO handling,
  p. 46 DIO mapping, pp. 108–115 LoRa registers, pp. 116–117 reset.
- [Semtech register definitions](https://github.com/Lora-net/LoRaMac-node/blob/master/src/radio/sx1276/sx1276Regs-LoRa.h)
  cross-check the IQ convention: TX inversion disabled has bit 0 set. Datasheet
  p. 115's bit-0 prose differs; 0x27/0x1D is the selected normal IQ configuration.
  Only register facts were cross-checked; no source implementation is imported.

`RegVersion == 0x12` is only a bus sanity check. It does not identify an SX1278 or
the E32 module. Module identity remains the explicitly selected profile. FRF
0x6C4000 follows 433 MHz × 2^19 / 32 MHz. PA config 0x8F/PaDac 0x84 uses the
normal +17 dBm setting. Low-frequency LNA defaults are kept. DetectOptimize keeps
reserved middle bits and clears AutomaticIFOn (0x43 for reset value 0xC3); BW125 IF settings use 0x2F=0x40,
0x30=0x00 per the referenced errata convention. Exact RF behavior, oscillator
tolerance, supply margins and antenna matching remain unverified on hardware.

The parent integration handoff lists the remaining AIR/resource/config renderer,
Ground backend ownership, architecture gate, UI and recorded-profile decisions.
The payload must not be presented as a completed normal-generation feature until
those integration tests, emitted gates and full Flight/Ground ARM links pass.
