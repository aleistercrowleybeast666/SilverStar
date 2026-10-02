import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
DEST = ROOT / 'docs/FCCG/auto_memory_layout_20261002/integrated_v2'
resources = json.loads((DEST / 'resources.json').read_text(encoding='utf-8'))
identity = json.loads((OUT / 'single_candidates_identity.json').read_text(encoding='utf-8'))
lines = [
    '# Integrated automatic static-memory layout: final software evidence', '',
    'Product/source commit: `c61968c1e13b30e9e58d19b107af8920ef517b76`. Independent branch: `fix/software-reconnect-ground-20261001`. Main remains `d410f4a7254f0433e91a22adb237b2944939fd99`. No merge, push, tag, release, reset, clean or hardware actions were performed.', '',
    'The exact authorized eight-commit parent range was applied sequentially. The logger conflict kept the stronger exact SF6 record type/version/name/length assertions; current SF6 source and the new ESKF backend reference-validity ABI were retained. `SourceOwners_Check` is unchanged from the accepted parent product: fresh generated component provenance binds every protected C/header/startup/linker input, including the actual selected linker. Clean current SF6/ABI files pass and isolated edits to either are rejected (`compatibility.json`). No old SF6 implementation or old hashes were restored.', '',
    'One complete post-fix matrix actually executed **32/32 successful commands**: each of four saved-auto configurations ran ARM Release compile/link/artifact audit, architecture, the Power10 gate exactly as emitted, Host regressions, real ARM `-fanalyzer` compile/link and memory/stack report (24 commands); each fresh legacy configuration ran ARM artifact and memory/stack comparison (8 commands). Legacy Host/analyzer/architecture were not rerun in this 32-command matrix. All eight configurations were saved and reopened identically. All initially generated file hashes were rechecked after tests and UI opening and remained unchanged.', '',
    'The preceding integrated v1 matrix actually completed 28/32 passes and four architecture failures. Saved auto selected the Make macro but EIDE omitted it. The owning `_Eide_Render`/`_EideTarget_Render` fix exports saved-layout defines to both EIDE configurations, while leaving the shared source graph free of layout overrides. Architecture equality was not weakened. Its fresh generated v2 gates all pass. Pre-fix logs remain under `pre_fix_v1`; no passes from separate revisions are stitched together. This validates Make auto linking and EIDE configuration equality, not a separate native EIDE auto linker workflow.', '',
    'Post-fix Python scope: **43 passed** (auto real-ARM faults, GUI smoke, release 0.1.1). Earlier collection error and out-of-application temporary-settings path failures are preserved: the latter demonstrate unchanged workspace protection, fixed by choosing a new test fixture directory inside `apps/FCCG/.work`, without product/allowlist changes. Complete commands, exits, durations, logs, configuration, generated source hashes, ELF hashes, map/stack reports and compiler versions are archived.', '',
    '| Algorithm | Layout | FLASH B | Main SRAM B | CCM B | Physical RAM total B |',
    '|---|---|---:|---:|---:|---:|',
]
for row in resources:
    regions = row['regions']
    lines.append(f"| {row['name']} | {row['layout']} | {regions['FLASH']['used']} | {regions['main SRAM']['used']} | {regions['CCMRAM']['used']} | {row['physical_ram_total_bytes']} |")
lines += ['',
    'Capacities: FLASH 524288 B, main SRAM 131072 B, independent CPU CCM 65536 B. Physical total is SRAM+CCM used, an accounting sum for MCU selection; CCM is not extra DMA-accessible SRAM. Only the previously approved exact CPU BSS groups move. DMA buffers, initialized data and task stack sizes stay fixed. All actual UART/DMA bank and startup-zero/alignment audits pass. ESKF history moves to SRAM; its SRAM spare is 13152 B (10.03%), still a yellow static margin. KF6 CCM spare is 10424 B (15.91%), also yellow. Auto does not create memory or prove runtime stack/timing safety.', '',
    'The original v8 physical totals were reverified against its manifest: PureINS 127016 B, KF6 157760 B, ESKF15 164384 B, SF6 145720 B. PureINS would have only 4056 B under a hypothetical 128 KiB combined capacity. This is not proof that F411 can run the project: it lacks the currently required USART3/PCB routing and no port was built or tested. The other three exceed 128 KiB static physical total. **Minimum required MCU clock: NOT MEASURED.** No board DWT evidence exists; MHz is not inferred from FLASH size, algorithm dimensions or Host execution time.', '',
    'Bounded real link enumeration tried 2/4/16/2 candidates for PureINS/KF6/ESKF15/SF6. Each uses real physical bank capacities; expected overflowing candidate links are retained inside decision records. Selected maps/ELFs match the decision hashes. The parent-authorized explicit-auto 100 KiB historical SRAM budget is advisory; legacy/manual budgets and physical overflow remain blocking. Old evidence and policy are preserved.', '',
    'Native SF6 export from the actual generated v2 auto sources/configuration passed 29655 checks. The new synthetic log opens through production `LogOpenCoordinator` using its own exact `.ssdecoder`/Descriptor: 1000 state and 104 measurement records, recorded calibration NONE/READY identity, no covariance/NIS; wrong/missing decoder reject and source hashes remain unchanged (**1 targeted FLP test passed**). This is not hardware-originated flight evidence. The prior full GSHC/FLP suites belong to the frozen single-candidate scope and were not repeated or relabeled as new full auto suites.', '',
    'GUI automated regression and image review are distinct. **All 16 `GUI_Opened` screenshots were actually viewed**: four algorithms x Chinese/English x light/dark, 1360x920, normal `MainWindow._Project_Open` path, per-process registered fonts. Checks covered auto selection, exact linked region values and warning colors, compact 0.1.1 header, visible memory rows and generated Flight status. Artifact summary is supplied from each real CLI artifact log; per-fixture toolchain detection remains Not Checked and no build/upload buttons were pressed. Earlier model-only `GUI` captures are retained as limited renderer evidence and do not prove generated status. English sidebar captions remain elided in the established fixed-width navigation; dark region text is less contrasted than the main body. No blanket perfect-GUI, accessibility, desktop DPI, OpenGL, interactive hardware or all-pages claim is made.', '',
    'Original frozen single-sensor Delay10 candidates remain byte-identical. Their firmware source is `170f1cb55daedf8e8d308a7bc845b2fa5b79d102`; final evidence commit is `5d6d12bab617f003d9721a2df024e78448f7c53f`. The exact ZIP, generated/frozen ELF/BIN copies and ZIP entries were compared. `post_fix_v2/single_candidates_identity.json` lists complete paths and hashes. These packages exclude auto, Baro and GroundMulti.', '',
]
for item in identity['candidates']:
    lines += [f"**{item['name']} original single Delay10**", '', f"Generation root: `{item['generation_root']}`.", f"Frozen root: `{item['frozen_root']}`.", f"ZIP: `{item['zip']['path']}`.", f"ZIP SHA256: `{item['zip']['sha256']}`."]
    for suffix in ['elf', 'bin']:
        value = item['artifacts'][suffix]
        lines += [f"{suffix.upper()}: `{value['frozen_path']}`; SHA256 `{value['sha256']}`."]
    lines += ['']
lines += [
    'New integrated legacy BINs are not the original v8 bytes. Complete emitted C/header/linker differences are recorded in `generated_delta_from_v8.patch/json`: configuration digest and project-semantics/generation-profile hashes change, besides approved memory annotations/headers/hooks and Host metadata tests. SF6 kernel/backend sources remain unchanged. Each new project therefore carries its own decoder and hashes. The new artifact ZIP is software-review evidence, not a replacement of the original single frozen candidates.', '',
    'F Prime-inspired Power10 text checks retain critical-contract review **NOT PROVEN**. SF6 remains 18592 B context (+10256 B versus its initial implementation), gains 0.2 untuned; replay uses bounded prior-IMU-boundary quantization up to 20ms, not fractional interpolation. Whole-firmware call graph/stack/MSP/ISR nesting, MCU WCET, minimum clock, navigation accuracy, hardware initial-alignment timeout and flight qualification remain NOT PROVEN/unmeasured. Source 255 UNKNOWN remains truthful for barometer provenance; separate reference/epoch/cold-backup work is excluded. Baro c65be2a and GroundMulti were not integrated.', '',
    'No TEST_4 or other user firmware/configuration/logs, frozen packages, visible desktop or user applications were modified. No serial/probe/reset/programming/OptionBytes/unlock/actuator command was executed. Generated roots are all under `.work/AutoMemory_Integrated_20261002_v2`, with exact configuration paths in `generation.json`.', '',
]
(DEST / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
manifest = json.loads((DEST / 'manifest.json').read_text(encoding='utf-8'))
manifest['minimum_mcu_clock'] = 'NOT MEASURED; no DWT/hardware evidence; no inferred MHz'
manifest['gui_visual_review'] = {'folder': 'GUI_Opened', 'viewed_images': 16, 'scope': 'actual offscreen normal project-open Build page; narrow checks and limitations in README, not all GUI perfect'}
manifest['files'] = {p.relative_to(DEST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DEST.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
(DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print('FINALIZED', len(manifest['files']), 'files')
