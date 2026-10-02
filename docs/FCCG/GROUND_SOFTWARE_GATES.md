# Generated Ground software gates

The Ground declarative core owns `Tools/check_ground.py` and `Tests/Host`.
Fresh generation emits `architecture-check`, `host-tests`, `artifact-check` and
the existing unchanged `power10-check`. Python 3, host GCC and the selected ARM
toolchain must be available; missing tools or an unsupported PC adapter fail
instead of silently skipping acceptance. `PYTHON` and `HOST_CC` can be selected
with Make variables.
`static-analysis` performs real ARM GCC `-fanalyzer` compilation of first-party
sources and an ARM link in the separate `build/analysis` tree; it does not reuse
normal objects or present syntax-only compilation as analyzer execution.

Architecture checks compare the Make source lists with the generated graph,
validate workspace bounds and actual paths, enforce source ownership, and
require the Ground bridge startup without Flight tasks. Host tests compile and
execute the emitted bridge, parser, CRC and selected UART DMA/USB adapter using
fake HAL/radio ports. They exercise bounded RX processing, frame capacity, PC
backpressure, errors, DMA buffer ownership and ring overflow.

Artifact checks require an ARM ELF, required bridge symbols, the declared
objects in the actual link map, allocated sections within selected linker
regions, fresh sources and matching ELF-derived BIN. The metadata version is
configuration provenance; this gate does not prove an embedded Ground product
version marker. None of these gates proves RF behavior, STM32 timing, stack
margin or completed critical-contract manual review. Those remain NOT PROVEN.

Flight command retries now match every AIR command field and expire after four
seconds. A validated new Capability ACK invalidates previous cached business
responses; Capability ACKs always validate the current advertisement before
responding. Pending START retains its full original request. Malformed packets
retain their ordinary error responses and do not enter the retry cache. AIR M0
has no session nonce: a wire-identical command within the retry lifetime is
still indistinguishable from a retransmission. No START or unlock is replayed
automatically by GSHC.

The shared SX1281 owner task preserves a 120 ms RX scheduling dwell between
transmissions, including a continuously populated TX ring. Existing FIFO
ordering, telemetry-level ACK/event precedence and ordinary queue-full errors
remain. Host IRQ/clock injection demonstrates an RX opportunity and delivered
mock command under continuous load, including millisecond-counter wrap. The
120 ms policy is not an RF airtime or collision guarantee, and changes effective
downlink throughput. PHY-dependent packet loss, queue pressure and command
round-trip latency need bench measurement before hardware acceptance.
