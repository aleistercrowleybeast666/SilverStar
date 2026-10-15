# Native USB CDC workflow — 0.1.3 development, 2026-10-15

SCG's build page now provides an experimental native USB workflow: select and
inspect a complete CubeMX CDC project, prepare a separate derived project, run
ARM compilation or actual GCC analyzer compilation, and recheck saved evidence.
This is a software integration result. Production admission, critical-contract
acceptance, stack/WCET and hardware operation remain unproven.

## Product flow and ownership

The native project supplies `.ioc`, device-specific clocks, pins, PCD, USB
initialization, middleware, startup, interrupts, linker and source inventory.
SCG reads these files, binds a reviewed lifecycle adapter, and writes only a new
separate output directory. Existing outputs and native input files are not
overwritten. The original `Flight`/`Ground` generation paths and exact legacy
F103/C071 admission gates retain their existing authority.

The build-page panel operates through `FccgService` and the existing background
task worker. Model and project identity are checked before applying a completed
operation, so a result from a previous project cannot replace the current model.
Saved references show an unchecked state until inspected again. Compiler failure
or cancellation retains its diagnostic receipt and disables dependent actions.

Projects using this feature store optional `native_usb` data in project format
19: native root and source digest, separate output and kit/graph digests, and the
latest receipt path/hash. Projects without this field retain their earlier
serialized form. Saved hashes are evidence references, never admission flags.
Every build freshly checks the source inventory, derived files and graph; an edit
requires inspection and derivation into a new directory.

## Source graph and build contract

`generator/native_usb_graph.py` constructs an explicit local experimental graph.
Each native C replacement appears exactly once; additional transport and
retirement sources and one assertion owner are included. Derived configuration
headers precede native headers. The reviewed compiler/vector bindings currently
cover the F103 PMA and F407 OTG_FS reference controllers. Other CPU/controller
bindings require review; a family name does not grant support.

The build runner invokes selected ARM GCC tools using direct argument arrays.
It does not execute imported Make/CMake/IDE scripts. Preprocessor definitions
are literal, source paths remain inside inspected roots, and effective compiler
header traces must match native/kit inventories or recorded toolchain headers.
Environment include/library/compiler path overrides are removed only from the
compiler child environment. Compilation uses strict warnings for new first-party
units, retains vendor diagnostics, and uses real `-fanalyzer` compilation for
the analyzer action. Fresh object files are linked and checked for ARM attributes,
transport symbols and the independently specified USB interrupt vector.

Each run retains commands, exits, logs, compiler/library hashes, actual header
hashes, dependencies, stack-usage files, ELF/map/vector files and a receipt.
Commands are cancellable with a 120-second/8-MiB output limit; total build work
has a 30-minute limit and at most 512 C translation units. Cancellation stops the
owned compiler process tree. These host limits are not target timing proofs.
The product build action explicitly reports `power10: NOT_RUN_BY_THIS_BUILD`.
The separate compatibility validator executes the owning gate and currently fails;
the build-page receipt does not replace that validation.

## Compatibility and recorded limits

| Imported configuration | Result and reason |
| --- | --- |
| Exact F103C8T6 classic CDC reference, FW_F1 1.8.7 | Experimental automatic derivation; real ARM normal/analyzer links and vector checks; not tested on board |
| Exact F407VET6 classic CDC reference, FW_F4 1.28.3 | Experimental automatic derivation and ARM links; original native configuration lacks notification TX2 FIFO, so runtime guard rejects configuration |
| Complete classic FS CDC with reviewed component/hook shapes | Capability inspection can accept unrelated native project variation; automatic compiler/controller binding must independently match |
| Other classic CDC components or edited lifecycle regions | Manual adapter review; automatic derivation refused |
| Existing C071 PCD-only sample | Rejected: complete native CDC middleware/application missing; no companion stack silently inserted |
| USBX, unsupported stack, HS, RTOS, DMA/cache or composite configuration | Explicitly rejected by this adapter; needs a separately designed lifecycle and resource contract |

The detailed compatibility matrix, buffer ownership, BUSY behavior, backpressure,
disconnect/retirement semantics, licenses and upstream provenance remain in
[the compatibility audit](USB_CDC_COMPATIBILITY_20261015.md).

The F407 native fix was attempted only in a task-owned isolated copy (140 files,
8,363,076 bytes), using installed CubeMX 6.15 and the existing external F4 SDK.
A CubeMX user template proposes checked RX/TX0/TX1/TX2 allocations of
128/64/64/32 32-bit words. The CLI did not complete: its first sandboxed invocation
failed on Java preferences, and the approved retry timed out waiting for the
third-party component lock. **The template has not been applied or validated.**
The original input is unchanged. No corrected-native or runnable-F407 claim is
made. A fresh CubeMX home unexpectedly extracted 632,135,209 bytes of browser/MCU
database cache under the task directory on D:, recorded separately; no cleanup
has been performed or authorized, and no full firmware SDK was downloaded.

To close that native configuration item: successfully generate the isolated
CubeMX-owned project with an appropriate FIFO configuration; inspect its exact
changes and license provenance; reimport and verify guard normal/fault cases;
then rerun fresh ARM/analyzer/gate evidence. Board validation requires separate
hardware authorization. The prepared template is not a repository firmware fix.

## Validation and transport protocol boundary

Formal evidence is indexed at
[`docs/evidence/native_usb_workflow_20261015`](../../../docs/evidence/native_usb_workflow_20261015/README.md).
It records all failed and skipped attempts as well as final results. Known UART
analyzer diagnostics and the failed compatibility Power of Ten gates remain open;
no full-suite, whole-firmware compliance or hardware qualification is claimed.

The transport remains a bounded byte stream with explicit session changes and
asynchronous ownership. A future TF-log protocol must define framing, version,
request identity, bounded chunks, end-to-end integrity, resumable offsets and
session invalidation above either UART or USB. Deletion additionally needs a
separate authorization/confirmation and storage transaction contract. Neither
remote deletion nor a firmware file service is implemented here; protocol ACK
cannot establish device READY or successful durable deletion.
