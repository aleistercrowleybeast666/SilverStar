# 0.1.3 USB CDC compatibility audit and experimental integration — 2026-10-15

Status: **experimental software evidence; production admission, critical-contract acceptance and hardware validation NOT PROVEN**. This work does not promise support for every STM32, change the old F103/C071 gates, or make an ACK imply READY.

This document preserves the compatibility batch and its executed `validate12`
evidence. The subsequent SCG project/service/build-page integration is documented
in [Native USB workflow](USB_NATIVE_WORKFLOW_20261015.md); its separate build
receipts do not replace or turn this batch's failed acceptance run into a pass.

## 2026-10-16 later continuation: executable failure attribution

This later continuation is sealed separately in `.work/usb013-gates-20261016/handoff-final.json`. The parent checkpoint is now `cd3fd0652a4162639a1ade55f5f1994f3b666544`. The earlier `usb013-compat-20261016` handoff, its 127-test run and its complete builds remain historical evidence for their exact source snapshot. They are not a full-suite result for the changes below. No shared service/model/graph/UI file, native input, vendor source, gate threshold, source coverage or exception was edited here.

The owning `_Ll_Derive` now rejects a missing class before entering native EP0 data-stage code; the indexed implementation also checks `classId == 0` before indexing. Rejection restores native DEFAULT and invalidates the stream without releasing transfer storage. The pre-fix cases produced **3 failures, 1 legitimate legacy-index skip**. The selected post-fix lifecycle run produced **44 passed, 4 skipped, 40 deselected**, including normal and existing fault expectations. The four skips are one F1 FIFO-flush case, two F1 global-RX-FIFO cases and the legacy class-index case. After the header-only guard change described below, the exact new fault cases were repeated against the final generator: **3 passed, 1 legacy-index skip, 84 deselected** (`final-callback-command.json`). These are targeted runs, not the complete integration suite.

The earlier phrase “zero new normalized failure items” did **not** establish that every failing source point was inherited. An added indexed `#ifdef USE_USBD_COMPOSITE` guard had the same text as other native directives, so text membership could conceal it. `UsbEvidence_Compare` now compares text multiplicities and separately maps failing physical source lines to equal baseline regions. Even multiplicities can cancel a removed old directive against an added identical one; unmapped source locations require review. A focused regression demonstrates that case (**1 passed**). Equal source lines still do not prove semantic safety or ownership of their surrounding function.

The generic indexed derivative removes only that exact borrowed preprocessor guard. Composite admission remains rejected by capability detection, the one-class-slot static assertion remains, and the actual pinned SDK exposes incompatible composite API signatures. Two extracted-header/definition ABI cases plus the capability-negative case pass (**3 passed**); a separate **actual ARM compile with `USE_USBD_COMPOSITE=1` fails as expected** on conflicting CDC API types. No runtime registry or new supported configuration was introduced. Native conditional branches remain in the scan and still fail it.

### All 17 remaining groups

The current unchanged emitted gate still returns **1**, with **F103 7 groups / F407 10 groups**. Every reported source point is mapped in `gate-attribution-final.json`, including absolute native/derived paths, line text, effective macros, minimum owner action and required validation. In the table, paths are relative to each selected complete native input; `CDC` means `Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c`, `Core` means `Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c`, and `Conf` means `USB_DEVICE/Target/usbd_conf.c`. Line numbers below are **native** locations, so they do not drift with generated insertions. This attribution grants no exception.

| Group | Exact native locations / owning responsibility | Minimum next action |
| --- | --- | --- |
| F103-G1 | `Core/Src/main.c:103,171`; native permanent loop syntax, SCG service in main-loop body | Native/gate owners coordinate a bounded service-iteration and terminal-fault proof; no cosmetic `while` replacement or blanket exception |
| F103-G2 | `Core/Src/main.c:176`; native `USE_FULL_ASSERT` conditional | Native owner supplies a reviewed fixed configuration with source/provenance retained |
| F103-G3 | Core `95,163`; native debug conditionals in a mixed file | Review a fixed middleware configuration, preserve owned checks, compare expanded tokens/ABI |
| F103-G4 | Conf `58,112,127,142,156,170,195,219,237,252,266,280,316,612`; native callback conditionals around owned wrappers | Native glue owner fixes callback mode; retain static ownership and pointer/class/index fault checks |
| F103-G5 | CDC `583`, `USBD_CDC_Setup`, 77 lines, unchanged native body | Fix real request-length/control-result contracts before any meaningful responsibility decomposition |
| F103-G6 | Core `361`, `USBD_LL_DataInStage`, native 62 → derived 64 lines | Review retained EP0 state/buffer/continuation contracts; preserve the adapter's checked bulk result |
| F103-G7 | `Core/Src/sysmem.c:54`, compiled native `_sbrk` | Native build/library owner provides a closed no-allocation contract; dead stripping and zero reserved heap are insufficient |
| F407-G1 | `Core/Src/main.c:105,194`; same mixed loop ownership | Same bounded service/fault proof and policy coordination as F103-G1 |
| F407-G2 | `Core/Src/main.c:199`; native assert conditional | Same fixed-native-configuration requirement as F103-G2 |
| F407-G3 | CDC `108,115,153,166,179,622`; native conditional points in a mixed file | Native CDC owner reviews a fixed non-composite configuration; alternate upstream evidence remains preserved |
| F407-G4 | Core `1168`, `USBD_GetEpDesc`; unchanged descriptor walk, symbol present in linked ELF | Bound by the actual descriptor object and validate nonzero/minimum `bLength`, total length and every step; return ordinary parse failure |
| F407-G5 | Core `22,100,106,208,218,236,271,281,318,363,386,442,788,898,1008,1048,1088,1119`; native conditional points | Reviewed fixed middleware variant, token/ABI comparison and EP0/bulk fault coverage; no source exclusions |
| F407-G6 | Conf `132,147,162,176,190,223,248,266,281,295,309,350,611`; native callback/test-mode conditionals in mixed file | Fixed callback ownership and retained wrapper checks, with actual callback/vector linkage validation |
| F407-G7 | CDC `432`, `USBD_CDC_Setup`, 85 lines, unchanged native body | Review raw callback length, result handling and control storage before responsibility decomposition |
| F407-G8 | Core `586`, `USBD_LL_DataOutStage`, native 71 → derived 74 lines | Review EP0 state/maxpacket/advancement and fallible continuation/status; keep bulk preconditions/results |
| F407-G9 | Core `684`, `USBD_LL_DataInStage`, native 71 → derived 74 lines | Same EP0 contracts as G8, including short/multiple/ZLP/status transitions |
| F407-G10 | `Core/Src/sysmem.c:54`, compiled native `_sbrk` | Same native build/library contract as F103-G7 |

Compiler-effective callback registration is `0`, debug is `0`, and full assertions, composite, HS and HS-test mode are not enabled in these selected configurations. This explains which branches execute; it does not exempt their emitted source from Rule 8. `_sbrk` is absent from both linked images, but its compiled native implementation can allocate available RAM; absence is not a source-policy waiver. The linked F407 descriptor walker is present and is not described as inactive.

A recording-stub probe compiles the **actual unchanged native `USBD_CDC_Setup` bodies and class storage types** with Host `-fanalyzer`, without performing an unsafe copy. For F103, a class request with `wLength=65535` forwards 65535 bytes to either RX preparation or TX submission against a **512-byte** class buffer; OUT also narrows the stored command length to 255 and returns success. This is a concrete transfer-boundary defect requiring native/vendor-owner remediation, not merely a style violation. F407 clips OUT to 64 and TX to 7, but passes raw 65535 to `Control` before clipping TX, so its callback/result contract still needs review; the probe does not establish the same F103 overrun there. Evidence is `vendor-control-length.json`, with recording stubs explicitly marked. No native/vendor file was patched.

The smallest coordinated vendor fix must reject invalid request-specific lengths before publishing storage or invoking callbacks, check storage/callback/result contracts, and retain ordinary USB stall/error behavior. Required cases include valid SET/GET_LINE_CODING, lengths 0/7/8/255/512/65535, bad request/index/recipient, missing storage/callback, and failed Control/LL operations. The descriptor walker additionally needs zero/one-byte `bLength`, object/total-length mismatch and no-match cases. Full EP0, all call/stack paths, ISR nesting, timing and hardware remain **NOT PROVEN**. Functions must not be split merely to evade the 60-line gate.

### Targeted compilation and C071 environment result

`incremental02` freshly compiles the changed F103 Conf and F407 Conf/CDC units in normal and real `-fanalyzer` modes: **6 ARM compilation commands, 4 fresh links**. All other object bytes and each recorded compiler dependency are checked against the earlier sealed inventories; unchanged rendered units are byte-identical. Independent ARM attributes and IRQ/vector checks pass. This is an incremental build with verified reuse, **not a newly executed whole-firmware analyzer or full Host/product run**. Both gate commands are exactly as emitted by the unchanged owning template. Gate hash remains `a02b24e2305dd65f99aff49f58a0cd10ddf954b8860f90b3d01096f499f06286`. F103 normal/analyzer ELF SHA-256 is `6e119fd987f180821a8112046a2ed2bd3a22778996ded837c4dab04136c88982`; F407 is `aa273b4935798635b4f481dd48e8404d22715a29137089af9e10722a5b85800f`. The initial `incremental` run precedes the guard removal and retains its own artifacts. Initial ABI harness encoding failure is retained separately; it is not counted as a firmware failure or a passing test.

The installed official package is `C:/Users/chdxm/STM32Cube/Repository/STM32Cube_FW_C0_V1.4.1`. Its complete `Projects/NUCLEO-C071RB/Applications/USBX/Ux_Device_CDC_ACM` example and `.ioc` use **STM32C071RBT6, USBX and ThreadX**, with UART DMA bridge behavior. This is a different part/configuration from the user's unchanged **C071FBP6 PCD-only** project. The local C071FBP6 CubeMX database exposes USBX; existence of USBX standalone parameters does not turn that ThreadX example into a tested standalone adapter.

Two bounded CubeMX 6.15 probes use copied official `.ioc` files and new task outputs, a fixed existing SDK, no install/refresh/login command and no large SDK copy. The first stops on Windows Java preferences access denial. With the environment permission issue resolved, project load/path/name/toolchain/custom-package commands succeed; **`project generate` requests ST login/download and returns KO**. The monitor stops there. `c071-generation02-receipt.json` reports no generated USBX application, CDC entry, PCD initialization or native build, and `generation_confirmed=false`. Both original `.ioc` hashes remain unchanged. The existing D-drive CubeMX operational cache was reused to avoid a further large extraction; its volatile preferences/logs may update, while prior captured evidence is retained. Proxy settings are not claimed as proof of offline execution.

C071 is therefore blocked on a coordinated local package/repository-registration/authentication environment or a supplied complete generated project. It is **not** blocked by absence of all local example sources, and no new download/login was attempted. A USBX/ThreadX adapter, or a separately generated standalone USBX adapter, still needs its own activation/deactivation/abort, scheduler, DRD/PMA, IRQ, storage and backpressure contracts, Host/ARM/analyzer validation and authorized board checks. Classic F1/F4 admission is unchanged. No blanket STM32 compatibility or hardware acceptance is claimed.

## 2026-10-16 continuation: native configuration and adapter boundaries

The parent integrated the experimental inspect/prepare/build/refresh workflow in commit `54b9267d05b9cb6437978be848f41c2a820ba590`. This continuation starts from descendant `21562359`; the nine USB files were clean against that integration. Concurrent navigation/FLP changes are outside this batch. The service, model, source graph, product runner and UI remain read-only here.

The original F407 input is unchanged. A new complete test reference is assembled under `.work/usb013-compat-20261016/native-inputs/cube-f407-usb`: the original 140-file inspected inventory, with only `USB_DEVICE/Target/usbd_conf.c` replaced by the retained CubeMX 6.15 user-template output. Its RX/TX0/TX1/TX2 allocations are **128/64/64/32 words, 288 of 320 words**, with all four setter results checked. Outside that FIFO block the normalized source matches the original. The template, native delta, original/fixture hashes, unique owners and generation receipt are recorded in `reference-inventory.json` and `native-fifo.patch`. This is assembly from a prior CubeMX-generated native file, **not a fresh full-project CubeMX generation**. This batch does not rerun CubeMX, download SDKs, duplicate its large cache or change a user's project.

The post-commit parent follow-up must be read alongside the initial workflow report: `cubemx-fifo-cached02` actually generated the native template but its copied project contained duplicate owners; `cubemx-clean03` requested ST login/download and did not generate a complete project. The new reference uses only the original unique inventory plus the generated configuration file. Existing historical evidence is preserved.

An additional safety defect was demonstrated before fixing it. The F103 PMA checker reserved three base-zero endpoint-table entries but did not verify `BTABLE == 0`. `prefix-table.log` records the failed injected table-base case against the old generator, with exact pre-fix source in `prefix-table-source.json`. The owning generator now checks BTABLE before class initialization/RX arm. The same fault, normal geometry, missing notification storage, capacity overflow and whole-class configure-before-RX barriers are covered in the final suite. No assertion was added for density.

A second failure was reproduced with the native EP0 caller's actual ordering: it sets CONFIGURED before calling `USBD_SetClassConfig`. On a rejected memory layout or missing class initializer, the old integration invalidated the byte stream but retained native CONFIGURED state. `prefix-config-state.log` records **4 failed / 4 passed** against the exact pre-fix generator. Configuration failure now explicitly restores DEFAULT while retaining transfer/class ownership as required. The final suite keeps these expectations for both controllers, including endpoint-open and initial-RX failures. This closes the owned configuration failure boundary; complete EP0 behavior remains outside this proof.

A third boundary concerns user-selected native buffer sizes: the adapter arms a 64-byte receive, but the native array could be smaller. `prefix-rx-storage02.log` records **2 failed / 2 passed**: 63-byte arrays were incorrectly accepted for both controller references, while 64-byte arrays compiled. Generated `CDC_Init_FS` now has a meaningful `_Static_assert(sizeof(UserRxBufferFS) >= USB_CDC_PACKET_SIZE)` before publishing the RX buffer. This is a compile-time capacity contract and earns no runtime density credit. The first `prefix-rx-storage` attempt had a missing test-header lookup and is retained as a harness failure, not defect evidence.

`hardware/usb_transport_profiles.py` now keeps middleware/header/hook signatures separate from explicit controller contracts:

| Contract | Bound implementation and restrictions | Independent compiler/IRQ evidence |
| --- | --- | --- |
| `pma-f1-single-v1` | Reviewed classic legacy ABI, F1 single-buffer PMA, 512 bytes, table base zero, FS/CPU copying, one main owner plus USB IRQ | Cortex-M3 soft float; USB_LP_CAN1_RX0 vector slot 20 |
| `otg-fs-f4-cpu-v1` | Reviewed classic indexed ABI, OTG FS shared RX/per-IN TX FIFO, capacity from the selected CMSIS device header, FS/CPU copying, same ownership model | Cortex-M4 hard float/FPv4-SP-D16; OTG_FS vector slot 67 |

These are reviewed adapter implementations, not MCU-family admission. PCD and PCDEx header signatures now accompany their source signatures. A class ABI alone cannot select an unimplemented controller: generation explicitly rejects an unknown controller contract. `usb-adaptation.json` carries the selected contract separately from native declarations. Native controller instance, PMA/FIFO API, literal FIFO calls and total declared words are source observations only; conditional execution and register state remain unproven until checked. Macro/duplicate/incomplete/small FIFO declarations are flagged. The generated runtime guard remains authoritative for effective geometry.

Unsupported USBX/HS/RTOS/DMA/cache inputs now keep their relevant layers `UNSUPPORTED_OR_UNRESOLVED` and eligibility `BLOCKED`; USBX receives no proposed classic class-data binding. Transport sizes describe the proposed classic FS adapter only. Local declarative inventories reject boolean `version` values instead of accepting Python's `True == 1`. These changes do not enable a new stack, speed, controller or scheduler.

| Reference | Current evidence level | Acceptance boundary |
| --- | --- | --- |
| F103C8T6 complete classic reference | Fresh source audit, extracted-function normal/fault Host cases and ARM normal/analyzer links in this batch | Text gate still fails; physical lifecycle, full stack/WCET and board behavior NOT PROVEN |
| F407VET6 original complete reference | Source audit identifies missing TX2; earlier exact binary/build evidence remains historical | Original runtime configuration remains rejected |
| F407VET6 corrected independent native reference | Unique ownership and native FIFO provenance; normal/fault Host, fresh ARM and actual product-workflow evidence recorded below | Software configuration item closed for this reference only; no board or original-user-project claim |
| C071FBP6 current input | Source audit only: **PCD_ONLY**, complete native CDC application/middleware absent | Generic adapter rejects it. `Core/Src/usb.c` declares USB_DRD_FS; `stm32c071xx.h` declares a 2048-byte PMA and the C0 LL header computes PMA start from used channels. F1's 512-byte/base-zero contract cannot be inherited. Historical companion-backend evidence is not this new adapter's evidence |
| Other PMA/DRD/OTG, USBX, HS, RTOS, DMA/cache or composite | Capability/contract review and suitable complete native fixtures still required | No support or hardware acceptance claimed from a part name or this matrix |

Final fresh commands and outcomes are `integrated11`, `workflow15`, `product-f40712`, `strict-derivatives13`, `native-layout-proof14` and `stack-observations11.json`. The unchanged native ARM baseline is `baseline02`. `integrated03`/`product-f40704` precede the configuration-state repair; `integrated06`/`product-f40707` precede the RX capacity repair. Earlier workflow and strict-audit runs retain their own scopes. Both native baseline and final integrated executions use the **same corrected F407 input**; the baseline adds no SCG hooks and its ARM sources are unaffected by generator-only repairs. UART diagnostics are compared as complete logs. Overlong-function line changes are reported explicitly alongside normalized category matching, and remain FAIL. A failed aggregate gate cannot be converted to PASS by attribution.

The extra whole-derivative strict-warning audit performs actual ARM `-fanalyzer` compilation of all five mixed-owner C files per target and their native counterparts. It retains every diagnostic and fails on warnings; comparison against the baseline is informational. It does not replace the validator's strict `-Werror` compilation of new first-party units or the unchanged full Power of Ten scan. `stack-observations11.json` records actual linked disassembly, unresolved indirect-call observations and compiler `.su` frames. It explicitly reports main/MSP/ISR/library bounds **NOT PROVEN**; neither a maximum individual frame nor spare RAM is accepted as a stack proof.

| Final check | Actual result |
| --- | --- |
| `integrated11` Host regressions | **127 passed, 5 skipped, 1 warning**; skipped: F103 FIFO-flush (1) and global RX FIFO (2), F407 nonexistent fifth setter (1) and PMA table (1). The pytest warning is the existing `cache_dir` option with its plugin disabled |
| `workflow15` complete product regressions | **26 passed, 1 existing pytest warning**. The sandbox `workflow01` failed owned-child termination; permission-enabled complete runs preserve their independent results |
| Integrated ARM evidence | Four fresh links: F103 and corrected F407, normal and actual analyzer; first-party strict units clean, independent attributes/vectors verified; full analyzer retains two baseline UART diagnostics per target |
| `product-f40712` actual inspect/prepare/build/refresh | Two fresh ARM links and verified receipts, 97 effective headers each; normal `Compiled`, analyzer `Diagnostics`. Product receipt correctly says Power of Ten `NOT_RUN_BY_THIS_BUILD` |
| Unchanged owning Power of Ten | **FAIL**: F103 7 groups, F407 10; baseline 8/11. Zero new normalized failure items, existing overlong functions remain FAIL. Aggregate validator exit **1**, critical contracts **NOT PROVEN** |
| `strict-derivatives13` whole mixed-owner diagnostic audit | **FAIL**, exit **1**: native baseline 29 primary diagnostics, derivatives retain 10; **zero new/changed diagnostics** by multiplicity, complete JSON locations/traces retained |
| `native-layout-proof14` | Same positive register-model geometry expectation fails on original F407 initialization and passes on corrected native initialization; actual original bytes unchanged |
| Stack, target timing, physical cancellation and hardware | **NOT PROVEN / NOT TESTED**; retained linked-call/frame observations do not close these obligations |

Final integrated normal/analyzer ELF SHA-256 values match within each independently built target: F103 `306ae25ae911cad9e0df0d8a92b844fc76dae382e9aad00c84eca17b728cb19b`; F407 `2aed574f3d90ebd8d1608335ec74975dd66bbb68e7b8365506ae5273f78f15ae`. The actual product workflow has its own F407 ELF `1a2811fc2f8f7aa463cbc5aeb933927a78bae8c0b6df326169971f484f48f734`. These artifacts are not substituted for one another. Final source, command, outcome and artifact provenance is indexed in `.work/usb013-compat-20261016/handoff-final.json` and `inventory-final.json`.

Remaining parent-coordinated patches, **not applied in this batch**:

| Read-only path/function | Concrete proposed change |
| --- | --- |
| `src/silverstar_fccg/generator/native_usb_graph.py:NativeUsbGraph_Resolve` | Consume generator-owned `controller_contract` compiler/IRQ requirements instead of selecting them from PCD variable names. Preserve native CPU validation, unique replacement ownership and independent linked-vector checks; reject unimplemented contracts. Exact unexecuted proposal: `.work/usb013-compat-20261016/parent-controller-contract.patch`, bound to its target hash in `parent-patch-proposal.json` |
| `src/silverstar_fccg/build/native_usb.py:NativeUsbBuild_Run` and `app/native_usb.py:NativeUsb_Build` | Add an explicit validation action/receipt bound to native, kit, graph and checker hashes. Keep product compilation's `NOT_RUN_BY_THIS_BUILD` for Power of Ten until the checker actually runs; cancellation/diagnostics retain their failure state |
| `src/silverstar_fccg/ui/pages/native_usb.py` | Display selected controller contract, source-only geometry findings, actual validation status and missing capabilities through the existing background worker; do not promote `Compiled` to READY |
| `src/silverstar_fccg/project/native_usb.py:NativeUsbReference` | If a new validation reference is persisted, validate its schema/digests and invalidate it on source, kit, graph or checker changes; let the parent own serialization changes |

The next new controller needs a complete native CDC fixture and an explicit controller adapter, with normal/fault Host, real ARM/analyzer/link and board evidence. C071/DRD requires its own PMA layout, endpoint cancellation and IRQ contract. USBX requires activation/deactivation/abort plus standalone or ThreadX execution semantics. HS and DMA/cache require independent descriptor, memory/cache and lifetime contracts. None should be enabled by adding MCU names to a whitelist.

## Ownership and current implementation (initial 2026-10-15 batch)

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
