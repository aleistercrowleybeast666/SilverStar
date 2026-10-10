# First-batch ordinary USB lifecycle closure - 2026-10-10

Tested code `80db26338bba77950a9b8e9bbc03d8a77e33567b`; prior code/evidence `838f148` / `e176458`. Worktree `D:\python_software\SilverStar\.work\ccdi`, branch `feature/scg-classic-cdc-contract-20261009`. The earlier parent ordinary review covered 838/e176 only, not this increment. The platform-stopped independent b66 USB safety review still has NO PASSED OUTCOME; it was not retried or bypassed. No malformed USB input or alternate-owner expression research was performed. Formal generation remains blocked.

## Concrete ordinary lifecycle coverage

| Operation | F103C8T6 / 72 MHz | C071FBP6 / 48 MHz |
|---|---|---|
| Normal enumeration | Actual generated core/ctlreq/ioreq/class/descriptor sources: device descriptor, 9-byte configuration header then complete multi-packet configuration, language/manufacturer/product/serial strings, valid address/configuration and both interfaces queried | Same; native PCD plus byte-pinned companion remains the exact input classification |
| Valid class control | Seven-byte SET/GET line coding plus DTR/RTS through the real generated call sites | Same through the real C071 interface implementation |
| RX and TX lifetime | 64-byte RX is copied into the bounded stream; caller TX bytes are copied and cannot overwrite pending transfer; 64-byte TX remains owned through a trailing ZLP | Same; existing transmit completion callback and endpoint service are present |
| Unconfigure/reset/disconnect/reconnect | Actual core/class retirement clears unread RX and old sessions, cancels pending TX and pending valid control OUT; fresh configuration accepts only the new session | Same |
| Stop and DeInit | Success closes all endpoints before class free; DeInit errors propagate and allow cleanup retry | Same; repaired class/core derivatives retained with provenance |
| Failed endpoint close | Class and TX bytes retained, write blocked, retry frees only after successful close | Repaired; pre-fix class free happened despite CloseEP failure |
| Reinit after failed cleanup | Rejected while class resources remain, preserving the cleanup binding | Repaired; pre-fix Init could overwrite the retained class binding |
| Initial endpoint open / RX arm failure | Existing failure abort/cleanup checked with valid SET_CONFIGURATION | Repaired; pre-fix native class discarded both LL results and published configured state |
| TX start returns failure | Session invalidated; ambiguous TX bytes remain owned until successful retirement | Existing LL-result hook/endpoint service invalidates the session; TxState and bytes remain owned until retirement |
| RX rearm returns failure | Existing failure path deconfigures and discards old-session unread bytes | Existing endpoint service retries the arm on the main owner; accepted bytes remain readable once in their session |

The final Host run contains two target tests executing twelve named scenarios each (24 scenario executions), not 24 independent pytest tests. HAL/PCD controller calls, UID registers, static allocator accounting and Cortex intrinsics are explicit Host substitutes. These tests establish the recorded normal core/class/adapter sequence and buffer contracts. They do not execute native HAL/PMA/IRQ internals or prove every IRQ/main interleaving, suspend/resume corner, actual host-driver behavior, or physical transfer cancellation. Hardware is unnecessary for the software checks completed here; these remaining limits are not being used to excuse a known normal implementation defect. Whole-program stack/WCET and manual critical-contract acceptance remain separate NOT PROVEN items.

## Repairs and traceability

C071 compiles two explicit additional ordinary lifecycle derivatives of the pinned b66 class/core, without changing the original companion or its EP0 functions. Narrow init/deinit/stop changes check real LL returns, retain class memory on failed endpoint closure, propagate errors, and reject reinitialization until cleanup succeeds. Original-to-derived hashes and reproducible patches are verified by the architecture gate. C071 private Export now emits a Makefile matching the final source graph and rejecting heap owner; shared compilation still emits its additional ABI probe truthfully. F103 composes its top-level Init/DeInit guard/result repair with the existing ordinary control/bulk derivative. F407 adaptation and GUI source remain unchanged.

Parent P3 is repaired: C071 backend receipt and build index now save project_root, runtime_project, snapshot_root and receipt hashes. The shared compiler also saves runtime_project, its byte hash and snapshot_root. Fresh tests assert these paths and hashes, and this archive retains the saved model itself.

## GUI entry wiring still required

It is not only a release gate. Existing widgets can remain visually unchanged, but their handlers are wired to the older ordinary flow:

1. `ui/main_window.py:_GroundCubeMxImport_Request` calls `CubeMxProject_Import`, not `UsbGroundProject_Import`. An exact-target dispatcher must resolve trusted SDK/companion facts and the fixed clock/SPI/GPIO recipe. Unknown configurations must continue to reject.
2. `_GroundCubeMxImport_Complete` currently reconstructs hardware and clears resource assignments. It must apply the returned bound model without discarding binding/resources, then use the existing save/reload flow. The F103 private model and C071 PCD-only capability representation must remain truthful.
3. `_GenerateOrApply_Request` uses `GenerationPlan_Create/Apply`, whose formal guard intentionally rejects these candidates. Integration needs an explicit candidate Plan/Export result adapter and safe disjoint output handling; it cannot simply remove the guard or mark a candidate formally ready.
4. `_TargetAction_Request` uses `BuildRunner.Target_Run` on an existing Ground_Station Makefile and assumes `build/ground.elf` plus a catalog MCU ID. The new route must dispatch `UsbGroundCandidate_Build`, preserve its compiler/backend/model receipts and use its actual `build/native.elf`/analyzer artifacts and independent device facts. Cancellation/progress and artifact display need corresponding result handling. The private Build API currently has no GUI cancellation/progress callback contract; that wiring remains to be implemented before a usable normal GUI path is claimed.
5. Quality/result status must display the completed software checks and outstanding acceptance separately; formal release still needs its applicable acceptance decision. No GUI behavior or styling was changed in this increment.

## Separate final verification runs

- `ul14`: 2 passed, 0 skipped, exact source `80db26338bba77950a9b8e9bbc03d8a77e33567b`.
- `uc09`: 22 passed, 0 skipped, exact source `80db26338bba77950a9b8e9bbc03d8a77e33567b`.
- `ucr04`: 67 passed, 0 skipped, exact source `80db26338bba77950a9b8e9bbc03d8a77e33567b`.
- `STM32F103C8T6`: 339 actual commands all exit 0; normal/analyzer ARM links, no compiler/analyzer diagnostics. ELF normal `5d44702c99bea19270756ca148f4984681e0f63544c8c7c6bc1b658d1fb69d69`; analyzer `5d44702c99bea19270756ca148f4984681e0f63544c8c7c6bc1b658d1fb69d69`.
- `STM32C071FBP6`: 351 actual commands all exit 0; normal/analyzer ARM links, no compiler/analyzer diagnostics. ELF normal `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`; analyzer `ee90e6871f5f5723982701e8b6783dd2638f4bd76f352f5099d2d38e031028b9`.

`ucg03` contains eight successful checks: architecture, ordinary generated Host, current artifact and unchanged PoT for each exact target. The generated bridge Host gate still uses its established C071 endpoint-service mock; the separate lifecycle run above compiles the actual C071 interface and service. Existing pytest unknown cache_dir warnings and Host vendor unused-parameter warnings are retained and are separate from firmware zero-warning acceptance. No whole-repository or independent safety PASS is claimed.

Pre-fix evidence is retained: ul07 C071 premature class free; ul09 F103 DeInit failure loss and C071 retained-class reinit; ul10 C071 initial OpenEP/RX-arm failure loss. ul01-06 also retain Host-fixture declaration/model errors (including ST normal EP0 status-phase stalls), which were corrected without weakening the data, return, lifetime or session expectations. ul08/11/12/13 are intermediate scoped passes; ul14 is the final exact-commit run.

Evidence: `evidence/native_usb_lifecycle_normal_20261010/verification.json`. Its manifest enumerates the retained subset and build/saved-model/receipt paths. Daily HEAD remains `56448bd35736221d7885a26704f2f953b0fe5055` with the same three untracked inventory files. No hardware, serial/DAPLink, flash/START, GUI/FINAL edit, push or merge occurred. Ordinary lifecycle tests were not platform-rejected; the earlier independent safety review remains blocked. Parent QA for this new commit and any later notified local acceptance merge remain separate.


Later scope note: the F103 ordinary Reset/Disconnect failure-return P2 and existing-widget GUI wiring gaps above were addressed in 4926f77/e782a33/f91f82e. Final normal software verification and exact build/source-snapshot identities are recorded in [NATIVE_USB_GUI_FLOW_20261010.md](NATIVE_USB_GUI_FLOW_20261010.md), tested code 63771a1. This retains the earlier report's original scope; b66 independent safety review remains NO_PASSED_OUTCOME.
