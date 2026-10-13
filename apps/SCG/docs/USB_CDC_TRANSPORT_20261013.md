# USB CDC transport development — 0.1.3

This development branch adds an experimental, protocol-independent integration
kit. It does not change the frozen 0.1.2 release, existing private Ground target
admission, or grant firmware/hardware acceptance.

## Ownership and compatibility plan

CubeMX owns the complete generated MCU project: clocks and their USB tolerance,
PHY/VBUS/pins, PCD/PMA/FIFO, startup/vector table, IRQ priorities, device stack,
descriptors and initialization. SCG inspects those files without executing their
build recipes, and exports a separate transport kit. The kit never patches or
overwrites the supplied project. Its CMake fragment adds only its own sources to
an explicitly selected existing target; native sources remain in that target.
The unchanged first-party `silverstar_assert` implementation, compiler header and
Apache-2.0 license are included. `UsbCdc_Attach(target BUNDLED)` supplies this
fail-stop owner to a plain CubeMX target; `EXISTING` explicitly reuses a compatible
owner already linked by SCG. Never compile both copies. Native ST license files
are inventoried independently; their terms are not replaced by the kit license.

This entry point is a source-checkout developer CLI; it is not an entry point
in the frozen portable 0.1.2 package. From `apps/SCG` with `src` on `PYTHONPATH`,
inspect without writing:

```text
python -m silverstar_fccg.app.usb_transport <complete-CubeMX-project>
```

Add `--output <new-disjoint-kit-directory>` to export. An existing output is
refused; changing source inputs during export aborts publication. The manifest
records the inspected source bytes and all kit file hashes. The normal Ground
GUI/target admission is unchanged; this explicit backend/CLI is the experimental
generic entry point.

| Input capability | Kit decision | Remaining conditions |
| --- | --- | --- |
| Complete traditional ST USB Device, single FS CDC, legacy class handle | Experimental adapter | Explicit lifecycle/RX hooks, one serialized owner, real build and hardware checks |
| Complete ST USB Device with indexed class storage | Experimental adapter | Class 0 only, no composite or additional classes; same checks |
| Exact F103/F407 inputs used in existing tests | Representative source/ABI tests | These are exact projects, not support for their whole families |
| Existing exact C071 native PCD plus pinned companion | Existing private route unchanged | PCD alone is not a generated CDC project |
| USBX | Rejected by this adapter | Needs its own thread/standalone, activation and transfer cancellation adapter |
| HS, DMA/cache, composite/multiple instances, RTOS ownership | Rejected by this first adapter | Needs explicit memory/coherency/concurrency review |
| Missing IOC, CDC, init/IRQ owner, stack headers, startup/linker/build files | Rejected | Supply a complete generated project |
| Unknown stack or unrecognized ABI | Rejected | Add an independently reviewed adapter |

An inspection result is a text/file capability report, never proof of clock
correctness, linked IRQs, stack semantics or successful cancellation. Inspecting
an unfamiliar part is permitted; matching an MCU family name never grants support.

## Lifecycle and integration contract

The generated interface owns bounded RX storage and a copied TX buffer. All
access is serialized using the fixed Cortex interrupt mask port; use one main
owner and the native USB ISR, on one core. No runtime callback registry, dynamic
allocation or blocking USB waits are introduced. Maximum individual writes are
256 bytes; this is a transport chunk limit, independent of GSP frames.

Call `UsbCdc_LinkDown()` for reset, disconnect, unconfigure, stop, suspend and
faults before allowing further application work. It invalidates the session and
discards unread RX, but retains submitted TX storage. Only call
`UsbCdc_Quiesced()` after successful endpoint closure/controller cancellation
proves that the old buffer is no longer referenced. Never use a timeout or a
cleared CONFIGURED flag as that proof. Configure a new session only after this
retirement. Session exhaustion blocks further use until MCU restart.

The CDC Receive hook calls `UsbCdc_Receive()` once, while the endpoint is not
rearmed. The transport copies a whole packet or reports backpressure; it never
publishes a partial packet. The hook must remove the original unconditional
rearm: `UsbCdc_Service()` rearms only when a full FS packet fits. A BUSY receive
means an integration error or unsupported concurrent producer; the packet must
not be acknowledged as delivered by a higher protocol. Read returns its session;
responses supply that same session so reset cannot replay an old reply.
Validate the callback's length pointer and its full `uint32_t` value against
the 64-byte FS packet bound before narrowing it to `uint16_t`. Route only the
selected device/class instance and handle every non-OK transport result.
Call `UsbCdc_Configure()` only after successful native class configuration;
native CDC Init already owns the first receive arm. Do not arm it a second time.

`UsbCdc_Write()` success means copied into the local one-slot queue. It does not
mean delivered. BUSY leaves caller data untouched and requires application retry.
Service submits and retains bytes until the native class clears TxState after
completion, including a trailing ZLP. Ambiguous submit/rearm failure invalidates
the session and retains storage until confirmed retirement. Suspend retains
ownership; resuming without retirement requires a separate adapter review.

The adapter does not repair unknown vendor middleware. Some ST versions discard
LL return values. USBD_OK therefore establishes only stack acceptance; native
LL error propagation, endpoint cancellation and the complete critical contracts
remain NOT PROVEN and block deployment acceptance. Preserve and inventory the
actual input licenses/version evidence; no new vendor code is copied into the kit.

## Protocol boundary

GSP/AIR and the separate [log file service contract](../../../contracts/log_file_service_v1.json)
sit above a byte transport. The USB kit itself implements no file listing,
download, filesystem access or remote deletion; it is not automatically bound
to that service. The service owns framed requests, capability negotiation,
file/session identity and offset/chunk checksums. Its v1 contract forbids resume
and deletion when identity is unknown; any future extension owns those semantics.
Bulk log download is restricted to maintenance serial/USB, never the radio link.

## Acceptance limits

Host tests and ARM compile/link results are software evidence only. Physical USB
enumeration, reconnect behavior, clock/IRQ validity, host-driver interoperability,
DMA/cache behavior, complete call graph/stack bounds and hardware/flight readiness
remain NOT PROVEN. The generated unmodified Power of Ten checker is a project
gate, not original Power of Ten compliance or NASA certification.

## Recorded software verification

The [evidence index](evidence/usb_transport_20261013/README.md) records separate
runs and their source snapshots. `final03` passed 20 Host regressions and two
fresh real native backend builds. The generated core and both legacy/indexed
ports compiled and linked against those exact F103C8T6/F407VET6 Cube/HAL/USB
inputs, with strict warnings and real ARM `-fanalyzer` compilation. Each new
ABI ELF retained all public transport operations and passed the recorded
attribute/vector/symbol checks. The existing native source graph passed its
architecture gate; the additional kit source graph and actual commands are
recorded separately. The kit was **not hooked into native
callbacks**: these are ABI and link results, not integrated transport execution.
The emitted Power of Ten checks included the new generated C and returned zero
while explicitly reporting critical-contract review NOT PROVEN.

`export04` separately passed 21 Host regressions after Python export publication
and bounded-read changes; it requested no target build. The evidence verifies
that its renderer and all generated target C/header bytes match `final03`.
The earlier failures, one existing pytest configuration warning, exact commands,
source/firmware hashes, library inventories and stack-frame reports are retained.
This is not a full repository regression or a whole-program stack proof.

ST's [classic CDC implementation](https://github.com/STMicroelectronics/stm32-mw-usb-device/blob/master/Class/CDC/Src/usbd_cdc.c)
and [component repository](https://github.com/STMicroelectronics/stm32-mw-usb-device)
are reference material, not pinned kit dependencies. Actual input source and
license hashes in each native snapshot are authoritative. The historical
[USBX architecture introduction](https://wiki.st.com/stm32mcu/wiki/Introduction_to_USBX)
establishes its separate adapter boundary; it does not define current USBX
standalone capabilities.
