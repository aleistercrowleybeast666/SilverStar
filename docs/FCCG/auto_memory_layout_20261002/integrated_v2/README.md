# Integrated automatic static-memory layout: final software evidence

Product/source commit: `c61968c1e13b30e9e58d19b107af8920ef517b76`. Independent branch: `fix/software-reconnect-ground-20261001`. Main remains `d410f4a7254f0433e91a22adb237b2944939fd99`. No merge, push, tag, release, reset, clean or hardware actions were performed.

The exact authorized eight-commit parent range was applied sequentially. The logger conflict kept the stronger exact SF6 record type/version/name/length assertions; current SF6 source and the new ESKF backend reference-validity ABI were retained. `SourceOwners_Check` is unchanged from the accepted parent product: fresh generated component provenance binds every protected C/header/startup/linker input, including the actual selected linker. Clean current SF6/ABI files pass and isolated edits to either are rejected (`compatibility.json`). No old SF6 implementation or old hashes were restored.

One complete post-fix matrix actually executed **32/32 successful commands**: each of four saved-auto configurations ran ARM Release compile/link/artifact audit, architecture, the Power10 gate exactly as emitted, Host regressions, real ARM `-fanalyzer` compile/link and memory/stack report (24 commands); each fresh legacy configuration ran ARM artifact and memory/stack comparison (8 commands). Legacy Host/analyzer/architecture were not rerun in this 32-command matrix. All eight configurations were saved and reopened identically. All initially generated file hashes were rechecked after tests and UI opening and remained unchanged.

The preceding integrated v1 matrix actually completed 28/32 passes and four architecture failures. Saved auto selected the Make macro but EIDE omitted it. The owning `_Eide_Render`/`_EideTarget_Render` fix exports saved-layout defines to both EIDE configurations, while leaving the shared source graph free of layout overrides. Architecture equality was not weakened. Its fresh generated v2 gates all pass. Pre-fix logs remain under `pre_fix_v1`; no passes from separate revisions are stitched together. This validates Make auto linking and EIDE configuration equality, not a separate native EIDE auto linker workflow.

Post-fix Python scope: **43 passed** (auto real-ARM faults, GUI smoke, release 0.1.1). Earlier collection error and out-of-application temporary-settings path failures are preserved: the latter demonstrate unchanged workspace protection, fixed by choosing a new test fixture directory inside `apps/FCCG/.work`, without product/allowlist changes. Complete commands, exits, durations, logs, configuration, generated source hashes, ELF hashes, map/stack reports and compiler versions are archived.

| Algorithm | Layout | FLASH B | Main SRAM B | CCM B | Physical RAM total B |
|---|---|---:|---:|---:|---:|
| PureINS | legacy | 284748 | 83000 | 44016 | 127016 |
| PureINS | auto | 284748 | 83320 | 43696 | 127016 |
| KF6 | legacy | 317124 | 102328 | 55432 | 157760 |
| KF6 | auto | 317124 | 102648 | 55112 | 157760 |
| ESKF15 | legacy | 303276 | 100928 | 63456 | 164384 |
| ESKF15 | auto | 303276 | 117920 | 46464 | 164384 |
| SF6 | legacy | 291420 | 101704 | 44016 | 145720 |
| SF6 | auto | 291420 | 101704 | 44016 | 145720 |

Capacities: FLASH 524288 B, main SRAM 131072 B, independent CPU CCM 65536 B. Physical total is SRAM+CCM used, an accounting sum for MCU selection; CCM is not extra DMA-accessible SRAM. Only the previously approved exact CPU BSS groups move. DMA buffers, initialized data and task stack sizes stay fixed. All actual UART/DMA bank and startup-zero/alignment audits pass. ESKF history moves to SRAM; its SRAM spare is 13152 B (10.03%), still a yellow static margin. KF6 CCM spare is 10424 B (15.91%), also yellow. Auto does not create memory or prove runtime stack/timing safety.

The original v8 physical totals were reverified against its manifest: PureINS 127016 B, KF6 157760 B, ESKF15 164384 B, SF6 145720 B. PureINS would have only 4056 B under a hypothetical 128 KiB combined capacity. This is not proof that F411 can run the project: it lacks the currently required USART3/PCB routing and no port was built or tested. The other three exceed 128 KiB static physical total. **Minimum required MCU clock: NOT MEASURED.** No board DWT evidence exists; MHz is not inferred from FLASH size, algorithm dimensions or Host execution time.

Bounded real link enumeration tried 2/4/16/2 candidates for PureINS/KF6/ESKF15/SF6. Each uses real physical bank capacities; expected overflowing candidate links are retained inside decision records. Selected maps/ELFs match the decision hashes. The parent-authorized explicit-auto 100 KiB historical SRAM budget is advisory; legacy/manual budgets and physical overflow remain blocking. Old evidence and policy are preserved.

Native SF6 export from the actual generated v2 auto sources/configuration passed 29655 checks. The new synthetic log opens through production `LogOpenCoordinator` using its own exact `.ssdecoder`/Descriptor: 1000 state and 104 measurement records, recorded calibration NONE/READY identity, no covariance/NIS; wrong/missing decoder reject and source hashes remain unchanged (**1 targeted FLP test passed**). This is not hardware-originated flight evidence. The prior full GSHC/FLP suites belong to the frozen single-candidate scope and were not repeated or relabeled as new full auto suites.

GUI automated regression and image review are distinct. **All 16 `GUI_Opened` screenshots were actually viewed**: four algorithms x Chinese/English x light/dark, 1360x920, normal `MainWindow._Project_Open` path, per-process registered fonts. Checks covered auto selection, exact linked region values and warning colors, compact 0.1.1 header, visible memory rows and generated Flight status. Artifact summary is supplied from each real CLI artifact log; per-fixture toolchain detection remains Not Checked and no build/upload buttons were pressed. Earlier model-only `GUI` captures are retained as limited renderer evidence and do not prove generated status. English sidebar captions remain elided in the established fixed-width navigation; dark region text is less contrasted than the main body. No blanket perfect-GUI, accessibility, desktop DPI, OpenGL, interactive hardware or all-pages claim is made.

Original frozen single-sensor Delay10 candidates remain byte-identical. Their firmware source is `170f1cb55daedf8e8d308a7bc845b2fa5b79d102`; final evidence commit is `5d6d12bab617f003d9721a2df024e78448f7c53f`. The exact ZIP, generated/frozen ELF/BIN copies and ZIP entries were compared. `post_fix_v2/single_candidates_identity.json` lists complete paths and hashes. These packages exclude auto, Baro and GroundMulti.

**KF6 original single Delay10**

Generation root: `D:\python_software\SilverStar\.work\SF6_20261001_v1\KF6_v8`.
Frozen root: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\KF6_Delay10`.
ZIP: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\KF6_Delay10.zip`.
ZIP SHA256: `ca0d945e5cbc65750c77f5b63621d0431c6782147bafc184db837e15b8e8a9f2`.
ELF: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\KF6_Delay10\Firmware\SilverStar_0_1_1.elf`; SHA256 `7c5f80ccfa9d85778f051052d048179d8b8f162c98ef539bb885e25f522d37e3`.
BIN: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\KF6_Delay10\Firmware\SilverStar_0_1_1.bin`; SHA256 `59c7f6f39a7f0751805889ea17aaedd3df0fb520166da7a2415052148eb19601`.

**SF6 original single Delay10**

Generation root: `D:\python_software\SilverStar\.work\SF6_20261001_v1\SF6_v8`.
Frozen root: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\SF6_Delay10`.
ZIP: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\SF6_Delay10.zip`.
ZIP SHA256: `fc088fdc17678020b4a53091f436965bc58e1c76bad804f7c23c4e0d89262dee`.
ELF: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\SF6_Delay10\Firmware\SilverStar_0_1_1.elf`; SHA256 `3e9885f9b5d5a5f6903cefc1dbff1094869e0a9d6b59be62d57e16765066bb32`.
BIN: `D:\python_software\SilverStar\.work\SoftwareCandidates_20261002_Single_v1\SF6_Delay10\Firmware\SilverStar_0_1_1.bin`; SHA256 `4cd53f00b172a542fdf65e3c3721ff448635c983bce21a008d6bb7cb0bec239f`.

New integrated legacy BINs are not the original v8 bytes. Complete emitted C/header/linker differences are recorded in `generated_delta_from_v8.patch/json`: configuration digest and project-semantics/generation-profile hashes change, besides approved memory annotations/headers/hooks and Host metadata tests. SF6 kernel/backend sources remain unchanged. Each new project therefore carries its own decoder and hashes. The new artifact ZIP is software-review evidence, not a replacement of the original single frozen candidates.

F Prime-inspired Power10 text checks retain critical-contract review **NOT PROVEN**. SF6 remains 18592 B context (+10256 B versus its initial implementation), gains 0.2 untuned; replay uses bounded prior-IMU-boundary quantization up to 20ms, not fractional interpolation. Whole-firmware call graph/stack/MSP/ISR nesting, MCU WCET, minimum clock, navigation accuracy, hardware initial-alignment timeout and flight qualification remain NOT PROVEN/unmeasured. Source 255 UNKNOWN remains truthful for barometer provenance; separate reference/epoch/cold-backup work is excluded. Baro c65be2a and GroundMulti were not integrated.

No TEST_4 or other user firmware/configuration/logs, frozen packages, visible desktop or user applications were modified. No serial/probe/reset/programming/OptionBytes/unlock/actuator command was executed. Generated roots are all under `.work/AutoMemory_Integrated_20261002_v2`, with exact configuration paths in `generation.json`.
