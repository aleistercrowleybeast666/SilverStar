# 0.1.3 USB CDC compatibility audit and experimental integration — 2026-10-15

Status: **experimental software evidence; production admission, critical-contract acceptance and hardware validation NOT PROVEN**. This work does not promise support for every STM32, change the old F103/C071 gates, or make an ACK imply READY.

This document preserves the compatibility batch and its executed `validate12`
evidence. The subsequent SCG project/service/build-page integration is documented
in [Native USB workflow](USB_NATIVE_WORKFLOW_20261015.md); its separate build
receipts do not replace or turn this batch's failed acceptance run into a pass.

## Ownership and current implementation

CubeMX remains the owner of the complete native project: `.ioc`, middleware, HAL/CMSIS, clock/IRQ setup, descriptors, startup, linker and native build inventory. SCG owns a separate transport kit and explicit derived replacements. The importer never executes the supplied Makefile and the exporter never overwrites the input project or an existing output directory.

Relevant sources:

| Source | Responsibility |
| --- | --- |
| `src/silverstar_fccg/app/usb_transport.py` | Bounded read-only inspection, result/reasons, separate opt-in export and CLI |
| `src/silverstar_fccg/hardware/usb_transport_capabilities.py` | Literal Make or declarative source inventory, actual function definitions, static allocation/configuration checks; unresolved cases rejected |
| `src/silverstar_fccg/hardware/usb_transport_profiles.py` | Reviewed middleware/HAL component and callback-region signatures; historical whole-input fingerprints retained as reference identities |
| `src/silverstar_fccg/generator/usb_cdc_transport.py` | Existing protocol-independent static RX/TX state machine and classic ABI port; unchanged in this batch |
| `src/silverstar_fccg/generator/usb_cdc_integration.py` | Source-bound callback/core/interface/endpoint-retirement derivatives, patches and replacement manifest |
| `src/silverstar_fccg/generator/native_usb_data.py`, `native_usb_indexed.py` | Existing checked bulk transformations reused read-only; their owning gates and implementations unchanged |
| `tools/validation/usb_transport_validate.py` | Explicit integrated ARM graph, real normal/analyzer builds, vector/ABI checks and unmodified Power of Ten invocation |
| `tests/test_usb_transport*.py` | Detection, source preservation, export, ABI and generated callback fault regressions |

`app/usb_ground.py:UsbGroundTarget_Validate` still admits only the existing exact F103C8T6/72 MHz and C071FBP6/48 MHz first-batch paths; F407 remains a separate private candidate. `generator/multi_target.py:GroundFiles_Render` retains its native backend rejection. The compatibility batch did not edit either gate, `app/service.py`, `project/`, `ui/`, `source_graph.py`, shared contracts or legacy payloads. The follow-up workflow adds project/service/UI integration while preserving those Ground gates.

## What the capability result means

`Experimental` means that conservative textual prerequisites are present. It is not a compiled ABI, effective preprocessor, board configuration, clock, memory or hardware proof. `capabilities.scope` explicitly says `DECLARED_BUILD_AND_SOURCE_CHECKS_ONLY`; the runtime review fields remain `NOT_PROVEN`.

The scanner requires a nonempty literal build inventory, unique source owners and function bodies, declared CDC/core/interface compilation, native startup/linker files, a single FS CDC registration, and a recognized static class allocator. It rejects empty middleware/build bodies, omitted owners, unresolved DMA assignments, cache activation, composite definitions, scheduler start calls and known unsupported stacks. It does not execute Make, CMake or IDE scripts. Native compiler dependencies must subsequently verify the declaration.

For a complete CMake/IDE project without a literal CubeMX Makefile, an explicit `scg-usb-build.json` can supply the inventory. Its exact fields are `format: "silverstar.usb.native-build"`, `version: 1`, `sources`, `asm_sources`, `include_dirs`, `defines`, `cpu`, and `linker_script`. The first four collection fields are nonempty string lists; `cpu` and `linker_script` are strings. Paths are relative to the inspected root, include directories omit `-I`, and defines omit `-D`. Exactly one startup and linker are required. Both Makefile and manifest at the root are rejected as ambiguous. Expressions, escaping paths, unknown fields, missing files and duplicate sources are rejected. This local experimental inventory is not a new shared `contracts/` authority.

The nine recorded negative mutations previously qualified: `(1U)` DMA, macro DMA, empty core, empty class, empty Makefile, a composite header define, replacing the static allocator with `malloc`, a scheduler start call, and removing the class from `C_SOURCES`. They are now rejected. These checks do not attempt to infer all C/preprocessor semantics, function behavior, caller handling or allocator correctness from tokens.

Automatic lifecycle integration has a stronger independent condition: reviewed middleware/HAL files and edited callback bodies must match their signatures, controller/PCD bindings must match, and the native main service region must be empty. The fallback checks component and hook ownership rather than a whole-project fingerprint, so unrelated project comments and native clock/pin configuration can vary. Existing application calls to `CDC_Transmit_FS` prevent automatic ownership takeover. Edited callbacks and unknown component revisions receive `UNREVIEWED_LIFECYCLE_SOURCE`; an otherwise eligible project can still receive a manual kit and structured missing-hook description. These are automatic-patch boundaries, not a family whitelist or runtime acceptance.

`UsbAdaptation_Describe` exports `usb-adaptation.json` with capability layers, source hashes/owners, build inventory, native authority, symbol bindings, buffer sizes, required lifecycle hooks, source attachments, configuration findings and required evidence. Its readiness is `BLOCKED` or `EXPERIMENTAL_UNVERIFIED`, and acceptance is always `NOT_PROVEN`. Current bindings use standard CubeMX names (`hUsbDeviceFS`, `MX_USB_DEVICE_Init`, `CDC_*_FS`); arbitrary renamed bindings remain future work.

## Exact reference configurations

The reference input root supplied for validation is `C:/Users/chdxm/Documents/Codex/2026-10-08/task/usb-validation` (the local redirected folder resolves under `D:/Codex_Work`). Full per-file hashes and the complete compilation graph are retained in each validation receipt.

| Reference | Provenance from `.ioc` | Classic ABI / peripheral | Automatic derivation fingerprint |
| --- | --- | --- | --- |
| `cube-f103-usb` / STM32F103C8T6 | Cube FW_F1 V1.8.7, HCLK 72 MHz, declared USB 48 MHz | Legacy `pClassData`, FS PMA, `hpcd_USB_FS` | `a6f4aa841b62181d9864a6d69de32846ea4bb11679b6129d683ef84ebe2239d7` |
| `cube-f407-usb` / STM32F407VET6 | Cube FW_F4 V1.28.3, HCLK 168 MHz | Indexed `pClassDataCmsit[0]`, OTG_FS FIFO, DMA disabled, `hpcd_USB_OTG_FS` | `c582351fa3907fa2d768577e11fd78d837cc5b2bf592adfdf227753aee48e1c4` |

The existing C071 input at `C:/Users/chdxm/Documents/Codex/2026-10-08/task/c071-cubemx-input/full-native-clean/C071FBP6_PCD_TEST` is PCD-only. It declares HSI48/USB SOF CRS and USB_DRD_FS IRQ ownership, but lacks the complete native CDC middleware/application required by this kit. The generic inspector rejects it; it does not silently attach the old companion stack.

## Callback and ownership contract

`--integrate` produces `lifecycle-integration.json`, derived files and unified patches under `Native/`, plus `usb_cdc_retire.c/.h`. The original project is unchanged. Build each derivative **instead of** its original, include the derived configuration header first, and compile all manifest `additional_sources`. The existing plain `UsbCdc_Attach` fragment alone does not perform this source replacement or attach retirement code.

The generated callback chain performs these operations:

1. Before native class initialization or initial RX arming, a configuration guard checks the PCD/device binding and the effective PMA/FIFO geometry. Native class initialization then checks endpoint opens, interface initialization and the first RX arm before transport configuration succeeds.
2. RX checks the original 32-bit length before narrowing, copies at most one 64-byte packet, and removes unconditional callback rearming. Main-loop service rearms only when the 512-byte ring has room for a complete packet.
3. TX copies at most 256 bytes into one owned static slot. Native `TxState`, including the terminating ZLP, controls completion. A submission error invalidates the session but does not release potentially referenced bytes.
4. Reset, disconnect, stop and suspend invalidate the transport session. Successful class retirement checks endpoint abort/close and controller-disabled postconditions before clearing pending completion state and stale software transfer pointers, then calls `UsbCdc_Quiesced`. Any failure retains class/TX ownership and blocks reconfiguration. F4 pending global RX FIFO data blocks OUT retirement; it is not flushed because EP0 shares that FIFO. A later retry can succeed after the pending data drains.
5. Suspend/resume deliberately leaves the transport offline until a fresh reset/reconfiguration. No timeout releases ownership. The generated main loop only services the transport; it does not add a protocol consumer or echo application.

Native data callbacks also check the exact PCD/backpointer, endpoint index before array access, and the core callback result. Missing class `DeInit`, native rearm failure, ZLP failure and late callbacks invalidate or retain ownership as appropriate. Host tests execute function bodies extracted unchanged from delivered derivatives, the full generated transport core and generated configuration/retirement helpers. HAL/registers are models; this does not prove physical cancellation, interrupt races, bus timing or MCU recovery. The native-init harness intercepts its terminal `Error_Handler` only on the host; this is not target recovery.

`USBD_LL_Init` and `SystemClock_Config` are unchanged byte-for-byte in the derivatives. F1 geometry checking covers five single-buffer regions, their 512-byte PMA limit and non-overlap with the reviewed base-zero endpoint table. F4 checks the controller's FIFO capacity, RX and TX0/1/2 sizes and pairwise non-overlap, with DMA disabled. The original F407 allocation has no TX2 and is deliberately rejected before CDC becomes online. The valid alternative layout used in Host tests is a model, not a native-input change or board result.

## Remaining safety blockers

These are acceptance blockers, not claims of completed safety fixes:

- Original LL initialization, PMA/FIFO setters, parts of HAL's lower-level return propagation and EP0 policy remain vendor-owned. The runtime geometry guard catches the demonstrated missing/overlapping/out-of-range layouts; it does not prove every native initialization contract. The reference F407 config sets RX=0x80 words, TX0=0x40 and TX1=0x80, consuming all 320 FIFO words; it has no TX2 allocation for CDC notification EP2. Its owner must correct the CubeMX native configuration, then reimport and rerun. No private-backend layout was transplanted.
- Both reference linkers declare `_Min_Heap_Size = 0x0` and `_Min_Stack_Size = 0x800`, but the native build inventory still includes heap-support `sysmem.c`, which the project gate rejects. Native HAL/middleware retain callbacks, polling, preprocessing and functions outside the project's first-party Power of Ten limits. Their presence must be inventoried and reviewed; passing a restricted text scan would not establish whole-firmware compliance.
- The retirement code is tied to the reviewed HAL/controller components. F1 uses single-buffer PMA endpoint state and CTR clearing. F4 uses checked abort/close, disabled endpoint/mask readback, IN FIFO flushing and interrupt clearing. Pending OUT FIFO data now prevents pointer release, but physical drain/retry liveness, reset/late-interrupt ordering, device-specific errata and worst-case masked interrupt time still need review and board tests. Changed PMA table-base/IRQ semantics cannot inherit this evidence.
- The PRIMASK ownership model is one main owner plus USB ISR, no RTOS/DMA/cache/composite. It is not a portable lock abstraction for a preemptive scheduler. Other IRQ nesting and full main/MSP/callback/library stack bounds are NOT PROVEN.
- GCC analyzer diagnostics, gate failures and skips are retained in full. A successful compile/link does not make them PASS. No firmware has been installed, no serial/DAP/USB hardware has been operated, and no electrical, throughput, suspend/resume or flight qualification is claimed.

## Extension matrix and smallest next steps

| Input capability | Current treatment | Required extension / evidence |
| --- | --- | --- |
| The two classic FS references | Experimental derivatives; F407 native FIFO configuration is blocked at runtime | Correct native configuration through its owner; resolve diagnostics/critical contracts and exercise real boards before admission |
| Complete classic FS legacy/indexed project using reviewed components/hooks | Generic inspection and component-bound derivation | Compile its exact effective configuration, verify unique ownership, endpoint/IRQ bindings, native memory configuration and board behavior |
| Complete classic FS with another HAL/middleware/controller revision | Generic inspection/kit and explicit manual-hook requirements | Add a reviewed controller/ABI adapter and representative immutable fixtures; no MCU-name admission shortcut |
| Complete CMake/IDE native project | Explicit declarative inventory supported | Verify the declared inventory against actual compiler dependencies; no imported build-script execution |
| C071/other PCD-only project | Reject incomplete CDC | Obtain a complete user-selected CubeMX CDC project; retain its origin and select an explicitly reviewed adapter |
| USBX standalone | Reject; separate adapter needed | `*_read_run`/`*_write_run` task-state semantics, activation/deactivation, transfer abort, fixed resource budgets and bounded polling |
| USBX with ThreadX | Reject; separate adapter needed | Task/mutex ownership, blocking/status/actual-length contracts, initialization-only resource policy, cancellation and scheduler-aware tests |
| HS / ULPI | Reject | Speed-specific descriptors/MPS/buffer sizing, PHY/clock/VBUS, native FIFO and IRQ proof; do not reuse FS packet assumptions |
| DMA or data cache | Reject | DMA-accessible RAM regions, alignment/cache-line ownership, clean/invalidate ordering, barriers and cancellation proof |
| Composite / multiple CDC instances / RTOS classic | Reject | Instance-owned queues/state, scheduler synchronization and callback provenance; no inferred single-instance aliasing |

The scalable architecture is **native capability audit → structured adaptation description → transport/lifecycle adapter → compiled and board evidence**. CubeMX supplies clocks, pins, PCD and USB initialization. SCG supplies static transport queues, backpressure, lifecycle ownership and an explicit build attachment. Compile-only coverage can grow through complete representative PMA/DRD/OTG FS projects; automatic edit signatures remain a narrower safety mechanism. This supports a route toward most USB Device-capable STM32 parts, without claiming those parts have already been validated.

A board run requires separate user authorization. Its retained evidence must bind the board/MCU revision, `.ioc`, SDK, source snapshot, ELF hash, host tool/OS, exact traffic script and captured results. Use these steps:

1. Correct F407 TX2 through the native project owner; inspect effective FIFO/PMA registers after native initialization and before configuration. Check USB clock, VBUS/PHY and IRQ wiring on each board. Confirm invalid layout cannot publish online.
2. Capture enumeration, device/configuration descriptors and endpoint addresses/MPS; verify single FS CDC behavior. Run sustained full-duplex sequences with counters and payload hashes, including empty, short and 64/128/256-byte ZLP boundaries.
3. Stop the consumer until the 512-byte RX ring fills. Observe NAK/backpressure without overwrite, resume the consumer and verify ordering. Saturate the single 256-byte TX slot and verify busy behavior, copied-buffer lifetime and completion through ZLP.
4. Reset, disconnect, cancel and unconfigure during IN and OUT transfers. Delay USB IRQ handling and create pending RX FIFO entries; verify failed retirement retains pointers/class ownership and offline state. Drain and retry, checking no old-session delivery or pointer reuse. Repeat configuration cycles.
5. Suspend/resume and verify the intended offline-until-reset/configuration policy. Inject abort/close/flush/readback failures and clock/CRS faults where the board permits; capture bounded failure behavior. Neither elapsed time nor ACK permits READY.
6. Measure maximum PRIMASK interval and ISR response under traffic/faults. Establish main/MSP and relevant nested-ISR stack bounds including actual linked libraries/callbacks; high-water observations supplement, rather than replace, static bounds. Unresolved timing/stack bounds remain NOT PROVEN.

Cache/DMA, USBX, RTOS and HS require distinct scenarios and cannot inherit this FS CPU-copying evidence.

## Integration boundary for the parent task

The independently editable USB scope is exactly these nine files: the three changed `app/usb_transport.py`, `tests/test_usb_transport.py`, `tools/validation/usb_transport_validate.py`; the five new `generator/usb_cdc_integration.py`, `hardware/usb_transport_capabilities.py`, `hardware/usb_transport_profiles.py`, `tests/test_usb_transport_capabilities.py`, `tests/test_usb_transport_integration.py`; and this document. Paths are relative to `apps/SCG/` (source modules are under `src/silverstar_fccg/`). The handoff inventory records complete paths and hashes.

The following paths were read only. Parent coordination is required before integrating them into normal project generation:

| Exact path under `src/silverstar_fccg/` | Proposed interface responsibility |
| --- | --- |
| `app/service.py` (`FccgService`, existing import methods) | Call `UsbTransport_Plan(input_path)`, expose `UsbAdaptation_Describe(plan)`, and invoke `UsbTransport_Export(input, separate_output, integrate=...)` through a bounded job; retain the selected native root and digest |
| `project/model.py`, `project/folder_contract.py`, `project/validation.py` | Persist a versioned native-reference/adaptation/replacement/validation-receipt reference; reuse workspace path policy and invalidate evidence when source/configuration changes; no implicit migration to admitted Ground |
| `generator/source_graph.py`, `generator/multi_target.py` | Attach every manifest replacement exactly once instead of its original, one assertion owner and all additional sources; verify effective dependencies, architecture and linked artifact ownership before normal generation |
| `ui/pages/targets.py`, `ui/pages/build.py`, `ui/workers.py` | Show capability layers, missing bindings, native configuration findings and validation status; perform inspection/build outside the GUI thread; preserve explicit user-selected native input |
| `app/usb_ground.py` | Future admission decision only after reviewed evidence and parent authorization; current exact F103/C071 gates are unchanged |

`usb-adaptation.json` and `lifecycle-integration.json` are local experimental artifacts. If their schema becomes a shared cross-application contract, the parent must establish that authority in `contracts/`; this task has not done so. Source-graph and GUI integration are not implied by a successful kit export. The gate owner `plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1` is unchanged; inherited vendor findings do not authorize a broader allowlist.

## SDK facts and bounded claims

`validate12/native/{f103,f407}/sdk-function-facts.json` retains source hashes, effective preprocessed translation-unit hashes and active function bodies from real ARM preprocessing of PCD, PCDEx and USB LL. It distinguishes the F1 PMA branch from inactive OTG source text.

- Both reviewed HALs check the core initialization operations and return failure to CubeMX's terminal `Error_Handler`. Endpoint close discards `USB_DeactivateEndpoint`'s result; the selected deactivation body returns success, so the new postcondition readback is relevant. Transmit/receive discard `USB_EPStartXfer` returns; this conclusion is tied to the reviewed active bodies, not all HAL releases.
- F4 `USB_EPStopXfer` and FIFO-flush paths have counted polling limits. These do not require a progressing SysTick, but a source loop count is not a measured STM32 WCET. The runtime wrapper checks their failures and retains ownership.
- F4's RXFLVL handler reads FIFO data through `OUT_ep[epnum].xfer_buff`. Clearing that pointer with queued FIFO data was unsafe in the pre-fix model. The new guard blocks retirement while RXFLVL is set. It deliberately does not flush the global RX FIFO or claim hardware liveness.
- Linked vendor HAL, USB core/class, CMSIS/startup and GCC/newlib libraries remain inventoried. Vendor callback tables, HAL callbacks, polling, preprocessing, long functions and heap-support source are controlled review subjects with unresolved call-graph, stack and timing consequences. This work grants no new Power of Ten exceptions or whole-firmware compliance.

## Official upstream context

The classic library separates core and class code; its availability across STM32Cube packages does not establish a particular board's complete project or ABI. See [ST classic device middleware](https://github.com/STMicroelectronics/stm32-mw-usb-device).

USBX and classic can both be relevant even within newer families. ST publishes a [U575 USBX CDC ACM application](https://github.com/STMicroelectronics/STM32CubeU5/blob/main/Projects/NUCLEO-U575ZI-Q/Applications/USBX/Ux_Device_CDC_ACM/README.md) and [U5 classic middleware applications](https://github.com/STMicroelectronics/stm32u5-classic-coremw-apps). Select from the imported implementation, not a family-name assumption. [ST's H5/U5 classic integration guidance](https://community.st.com/stm32-mcus-60/how-to-use-stmicroelectronics-classic-usb-device-middleware-with-new-stm32-families-122491) describes explicit middleware integration.

USBX's [standalone write implementation](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_cdc_acm_write_run.c), [threaded write implementation](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_cdc_acm_write.c) and [deactivation path](https://github.com/eclipse-threadx/usbx/blob/master/common/usbx_device_classes/src/ux_device_class_cdc_acm_deactivate.c) have different lifetime and execution contracts from `USBD_CDC_TransmitPacket`/`TxState`. These upstream links were research references, not imported code or evidence for this batch's binary.

Hardware/PHY choices must be checked against the exact device and board; see [ST AN4879 USB hardware guidelines](https://www.st.com/resource/en/application_note/an4879-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics.pdf).

## Reproduction and retained evidence

From the repository root, with Python, Host GCC and ARM GCC on PATH:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
python -B apps/SCG/tools/validation/usb_transport_validate.py --baseline --reference '<complete-native-reference-root>' --output '<new-baseline-directory>'
python -B apps/SCG/tools/validation/usb_transport_validate.py --integrated --baseline-evidence '<executed-baseline-directory>' --reference '<complete-native-reference-root>' --output '<new-integrated-directory>'
```

The validator uses direct argument arrays, never the imported Makefile. It retains source text/hashes for the dirty USB implementation and unchanged transformation dependencies, tool versions, exact commands/exit codes, full logs, a source replacement graph, compiler dependencies, `.su`, ELF/map/vector artifacts and input/library hashes. All C units receive real `-fanalyzer` in the analyzer build. First-party files use strict warnings as errors. Vendor warnings remain visible and make the aggregate check fail. The source graph verifies unique replacement ownership and the linked USB vector slots; it is not the Ground architecture checker or full-program analysis.

Power of Ten uses the unchanged owning `silverstar_core_0_1_0` script and the exact command emitted by `multi_target._Makefile_Render`. Its checker Makefile is a projection of the actual direct compiler graph, not a runnable Ground project. Complete vendor-derived C files are additionally copied under `Generated/UsbVendorReview` for conservative scan coverage of owned edits. They are not separately compiled. This intentionally exposes retained vendor violations without exempting new edits or changing any threshold.

Task evidence is under `.work/usb013-compat-20261015/`. Earlier failed/intermediate attempts are preserved. `precheck.log` records the nine pre-fix false positives; `cap02.log` records 29 detector/export tests; `integration01.log` records the first callback run. `prefix06.log` records five pre-fix failures for active endpoints and pending RX data; the final run includes their post-fix cases. No cleanup has been performed or authorized. Retained evidence and historical releases are not cleanup targets.

Final complete execution: `.work/usb013-compat-20261015/validate12/`; aggregate exit **1**, recorded in `validate12-exit.txt`. This is a failed acceptance run, not a stitched suite pass. Its 214 recorded commands include all Host tests, both complete native targets, real analyzer compilation/linking, six effective HAL/LL preprocessor outputs and both unchanged gates. The source snapshot identifies commit `5af1efa18c4770a4fc91e8b4e87e94a60728eb65` plus the exact dirty source contents/hashes; the commit alone is not the tested implementation.

| Check | Recorded outcome |
| --- | --- |
| Host regression | **98 passed, 5 skipped, 1 warning**. F103 skips one FIFO-flush and two global RX FIFO cases; PMA disable/CTR/abort/close cases run. F407 skips setter-call positions 4/5 absent from its three-call native configuration; missing TX2 is exercised and rejected. Warning: pytest's pre-existing `cache_dir` config while cache plugin is disabled. |
| F103 normal and analyzer builds | Both compile/link; actual ARM attributes and USB_LP_CAN1_RX0 vector slot 20 verified |
| F407 normal and analyzer builds | Both compile/link; actual ARM attributes and OTG_FS vector slot 67 verified |
| First-party new transport/port/retirement units | Strict normal and real analyzer compilation without diagnostics in this run |
| Full native analyzer | **Not clean**: two `-Wanalyzer-null-dereference` diagnostics in each unchanged UART HAL (`HAL_UART_Transmit`, `HAL_UARTEx_ReceiveToIdle`). Complete diagnostic traces retained; not classified as proven defects or false positives. |
| Power of Ten | **FAIL**: 7 reported groups for F103, 10 for F407. Includes native permanent loops, conditional compilation, overlong vendor/mixed-owner EP0/core functions and `sysmem.c` in the compiled graph. Rule 5 recommendations remain nonblocking, critical-contract review **NOT PROVEN**. |
| Input integrity | All inspected native input hashes unchanged after both builds |
| Hardware, cancellation, IRQ latency, complete stack proof | **NOT PROVEN**, no hardware operations |

Tool versions: ARM GCC 14.3.1 20250623 (Arm GNU Toolchain 14.3.Rel1), MSYS2 Host GCC 16.1.0, Python version recorded in `python-version.log`. Gate SHA256: `a02b24e2305dd65f99aff49f58a0cd10ddf954b8860f90b3d01096f499f06286`; no gate revisions were made.

Final ELF hashes (normal and analyzer outputs are independently built and happen to match within each target):

- F103: `18d5a13a027ee3be44a5c0b1ae34bbf56c3d1c99e181672096d8f7f4c1d6f295`.
- F407: `1ddf4afcfd535a7dd6187698417b37956c66f71e8eee3af1d557a1628fe8ad3a`.

The unchanged native baseline is `baseline04/`, with the same inspected input hashes. Its two normal and two analyzer links completed. `validate12/baseline-attribution.json` compares complete UART analyzer logs byte-for-byte and normalizes diagnostic line locations/function lengths only for matching existing gate categories. Raw logs retain actual lengths.

| Finding | Unmodified native baseline | Final derived output | Disposition |
| --- | --- | --- | --- |
| UART analyzer diagnostics, each target | Two diagnostics | Identical complete log | Existing vendor diagnostics; neither proven defects nor waived false positives |
| F103 Power of Ten | 8 failure groups | 7 failure groups; 26 existing normalized items, zero new items | FAIL remains |
| F407 Power of Ten | 11 failure groups | 10 failure groups; 52 existing normalized items, zero new items | FAIL remains |
| Entire-target zero runtime assertion candidates | Present in both native baselines | Absent with existing transport/assertion owner | Explains one fewer group per target; no useful-density or critical-contract proof |
| Overlong mixed-owner functions | F103 `DataInStage`: 62 lines; F407 `DataOutStage`/`DataInStage`: 71 lines each | 64 and 74/74 lines respectively | Already over threshold, now longer after checks; still FAIL, not exempted by attribution |
| Active endpoint / pending RX pointer release | Five demonstrated failures in `prefix06` | Fault cases pass in the full final run | Scoped software fix, physical cancellation still NOT PROVEN |
| F407 missing TX2 | Present in native configuration | Native initialization unchanged; class-boundary guard rejects it | Native owner action remains required before board operation |

Earlier execution details remain available: `validate01` stopped at the first vendor UART diagnostic; `validate02` exposed an absolute-linker projection bug; `validate03` repeated the whole workflow with a byte-identical relative linker and recorded 54 passed/1 skipped, four links and 7/10 gate groups. That is historical evidence, not the final binary. `prefix05` had a Host-model unused-variable error; `prefix06` establishes the real pre-fix retirement failures. `retire07` recorded the initial retirement fix. `initprefix08` recorded 16 failures while probing a broader proposal to rewrite native LL initialization. Following the clarified CubeMX ownership boundary, that proposal was not adopted: current tests preserve native initialization and test the new class-boundary guard, and do not claim native return propagation or cleanup was fixed. `callback10` and `host11` are intermediate Host checks; `validate12` reruns the final complete suite. All prior logs and artifacts are retained.

`validate12/commands.json`, `source-snapshot.json`, `summary.json`, `inventory.json`, `baseline-attribution.json`, each native `receipt.json`, and task-level `inventory-final.json` provide provenance. Task-level `handoff-final.json` records the nine owned files, exact source snapshot match, baseline attribution and remaining actions. Earlier `handoff.json`/`inventory.json` describe the initial `validate03` handoff and are preserved without alteration. Other workspace writers' files are outside this task's ownership; no staging, commits, branch changes, hardware actions or pushes were performed.
