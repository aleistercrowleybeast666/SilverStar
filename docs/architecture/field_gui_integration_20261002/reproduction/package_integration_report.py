from pathlib import Path
import json,hashlib,shutil,subprocess
repo=Path(r'D:\python_software\SilverStar\.work\FieldGuiIntegration_20261002')
out=repo/'docs/architecture/field_gui_integration_20261002'
local=Path(__file__).parent
build=json.loads((out/'results_build.json').read_text(encoding='utf-8'))
assert len(build)==27,len(build)
assert not any(r['exit'] for r in build),[r['name'] for r in build if r['exit']]
generation=json.loads((out/'generation_summary.json').read_text(encoding='utf-8'))
comparison=json.loads((out/'source_vs_frozen.json').read_text(encoding='utf-8'))
audit=json.loads((out/'merge_audit.json').read_text(encoding='utf-8'))
frozen=Path(r'D:\python_software\SilverStar\.work\FieldIntegration_20261002\.work\FieldFreeze_20261002')
freeze=json.loads((frozen/'freeze_manifest.json').read_text(encoding='utf-8'))
shutil.copyfile(frozen/'freeze_manifest.json',out/'frozen_field_manifest_reference.json')
artifacts=[]
for name,record in generation['projects'].items():
    root=Path(record['project_root'])
    for target in ('Flight_Controller','Ground_Station'):
        folder=root/target/('build/FCCG/SilverStar_F407/Release' if target=='Flight_Controller' else 'build')
        if target=='Flight_Controller' and name=='new_auto':folder=folder/'auto'
        for p in sorted(folder.glob('*')):
            if p.is_file() and p.suffix in ('.elf','.bin','.hex','.map'):
                sha=hashlib.sha256(p.read_bytes()).hexdigest()
                reference=next((r for r in freeze['artifacts'] if r['target']==target and Path(r['frozen_path']).suffix==p.suffix),None)
                artifacts.append({'configuration':name,'target':target,'path':str(p),'bytes':p.stat().st_size,'sha256':sha,'frozen_sha256':reference['sha256'] if reference else None,'same_bytes_as_frozen':sha==reference['sha256'] if reference else None})
(out/'artifact_comparison.json').write_text(json.dumps(artifacts,indent=2)+'\n',encoding='utf-8')
for n in ('integration_verify.py','integration_entry_capture.py','integration_merge_audit.py','compare_integration_sources.py','prepare_integration_captures.py','package_integration_report.py'):
    shutil.copyfile(local/n,out/'reproduction'/n)
source_hashes={str(p.relative_to(repo)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for subtree in ('apps','tools','contracts') for p in (repo/subtree).rglob('*') if p.is_file() and p.suffix in ('.py','.json','.c','.h','.ld','.s','.mk') and not any(part in ('.work','.fccg','__pycache__','.venv','installed') for part in p.relative_to(repo).parts)}
(out/'source_hashes.json').write_text(json.dumps(source_hashes,indent=2)+'\n',encoding='utf-8')
for prefix in ('existing_legacy','new_auto'):
    for target in ('Flight_Controller','Ground_Station'):
        project=Path(generation['projects'][prefix]['project_root'])/target
        resource_folder=out/'artifacts'/prefix/target
        resource_folder.mkdir(parents=True,exist_ok=True)
        for p in project.rglob('*.json'):
            if p.name in ('stack-budget.json','layout-report.json','auto-memory-layout.json','ground_source_graph.json','ground_target_metadata.json') or 'memory_layout' in p.parts:
                dest=resource_folder/p.relative_to(project)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(p,dest)
        for p in project.rglob('*'):
            if p.is_file() and 'memory_layout' in p.parts and p.suffix in ('.ld','.log'):
                dest=resource_folder/p.relative_to(project)
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(p,dest)
lines=['# 综合 GUI 与冻结现场增量验收','',f'生产合并：{generation["source_commit"]}；双亲 d4aa83a（GUI）与 160cebbd（现场证据），共同祖先 170f1cb。版本 0.1.1。','',
'综合 worktree：`D:\\python_software\\SilverStar\\.work\\FieldGuiIntegration_20261002`；分支 `fix/field-gui-integration-20261002`。根目录只有 SCG.py、GSHC.py、FLP.py 三个 Python 启动程序。三个入口均通过实际 root runpy、原应用初始化与 Qt 事件循环显示主窗口；串口 open 测试守卫零尝试。入口截图在 entry_capture/。这不是原生鼠标操作验收。','',
'自动合并无文本冲突；逐项审阅了六个自动合并文件。GSHC 保留取消导航二次 START 否决与原主线滚动布局；渲染器保留 Auto 与现场 RF 分发。RF/M9N/Ground 插件与现场分支 Git 字节一致。没有合入独立 Baro 或多无线分支，没有额外修改 controller、硬件或现场冻结文件。merge_audit.json 记录双亲、排除分支和各受保护 worktree 的 HEAD/clean。','',
'## 配置与像素','',
'既有现场根 ssproject 的副本通过 GUI 打开，保存到独立新项目后重开：整个 Dictionary_Get 一致，Ground 配置一致，legacy 不变。新草稿 default Auto，选择 SS0.5/GS_SS1、SX1281/USART1 后保存重开也一致。均生成 Flight_Controller 与 Ground_Station；gui_errors 为空。显式 legacy、eskf_window_sram、auto 和缺字段迁移由回归覆盖。','',
'从实际 Ground inventory 显示 USART1 · PLATFORM_UART_1；无 inventory 时显示原因。完整 F103 CubeMX 输入导入后真实控件显示 MCU，保存按钮启用；保存到隔离本地板卡库后可再次选择。重复选同一 UART PC 接口保留 USART1 绑定。Ground 缺资源生成 tooltip 修复在 d4aa83a，未改变按钮启用条件或后端校验。','',
'已实际查看 FLP 1920×1020 和 1250×875 像素图：未保存、长中文名与 dirty 星号均在单行头部，语言/主题不重叠；另有英文深色、SCG Auto、无 inventory、真实 UART 和 Ground 导入/保存截图。Windows DPR 1.25；geometry.json 记录逻辑尺寸与像素尺寸。reproduction/ 内保留脚本和 PNG。','',
'## 执行范围与结果','',
'| 完整执行组 | 结果 | 记录 |','| --- | --- | --- |',
'| SCG 配置/恢复/GUI workflow/F103/UART/生成约束/文档入口 | 37 passed | tests_r4/SCG_regression.log |',
'| Auto 保存/旧策略/GUI/生成审计载入子集 | 7 passed, 17 deselected | tests_r3/Auto_memory_policy.log |',
'| FLP header 与工程身份 | 6 passed | tests_r3/FLP_header_regression.log |',
'| GSHC optional START/ACK/传感器/校准/布局 | 273 passed, 3 subtests passed, 30 warnings | tests_r3/GSHC_optional_start_and_layout.log |',
'| 两配置×两板 ARM Release/Host/architecture/PoT/analyzer/artifact，另两次 Flight resources 与一次配对 RF | 27 实际命令均 exit 0 | results_build.json 与完整日志 |','',
'这些是分别执行的组，不宣称全仓库全 suite 或全 GUI 无问题。GSHC 原生 Qt 多窗口回归有 OpenGL invalid-value 渲染警告；实际入口截图正常，但警告未修复。Ground ARM nano libc 未实现 syscall 链接警告保留。PoT 文本门禁明确 critical-contract NOT_PROVEN；任务/ISR 栈与无线时序、STM32 WCET、导航准确性和外场/飞行资格没有据此证明。','',
'首轮缺少临时目录、第二轮临时目录越过应用 WorkspacePolicy、第三轮 Windows 深路径板卡包 board.ioc 失败均完整保留；仅修正运行器路径，不修改生产或断言。相同失败用例短路径独立通过，再完整重跑原 SCG 组 37 passed。截图包装器曾误用静态 exec；错误仅在测试包装器，修复后重跑三个入口。没有把失败执行记为通过。','',
'## 与已烧冻结候选的区别','',
'对只读冻结 SourceFirmware zip 核对完整 SHA-256 后，直接读取 Generated 条目逐字节比较，不归一化换行，不把仅 ELF 的冻结目录当源码。比较包括 C/H/汇编/linker/make/Python/PowerShell，排除 build 产物；完整文件级 SHA 与 diff 见 source_vs_frozen.json 和两个 *_vs_frozen_source.patch。','']
for name,targets in comparison.items():
    for target,r in targets.items():lines.append(f'- {name} / {target}：{r["equal_count"]} 个源码相同，{len(r["differences"])} 个不同或新增（新共 {r["new_source_count"]}）。')
lines += ['',
'旧配置 Flight 差异清单：'+ '、'.join(r['path'] for r in comparison['existing_legacy']['Flight_Controller']['differences'])+'。Ground 仅 Platform/Inc/platform_memory.h。这些包含 Auto 分组宏、linker/Makefile、生成内存审计/检查工具和两个 Host 测试，以及配置/decoder 摘要变化；现场 optional GNSS/RF/M9N 逻辑保留。新 Auto 正常配置另外改变生成配置，完整补丁已列出。','',
'生成源码和 Flight ELF/BIN 与已烧候选不同：本次生成需要其自己精确匹配的 .ssdecoder/Descriptor，不能用它替代旧日志的冻结 decoder。artifact_comparison.json 逐项标明 raw hash 是否相同；若 Ground 某产物确实同 hash，仅该项成立，不能概括两板同 hash。冻结归档、原 ELF/BIN 和输入项目未变；本轮没有烧录或硬件连接。','',
'## 集成与剩余边界','',
'可以作为父线程审核后的综合分支候选。未切换主 workspace；主 5c451551 与冻结现场 160cebbd 始终 clean。父线程确认前用户原根目录仍是原版本；可直接从综合 worktree 的三个根入口打开本候选。没有 push/tag/Release/merge main；未移动用户 TEST0–4、日志、许可证或 metadata。','',
'还未测：原生鼠标端到端、真实串口/DAP/烧录、所有自定义板卡生成矩阵、所有 Auto 架构组合、硬件外场资格。GSHC OpenGL 警告及深目录 Windows 板卡包路径限制仍需单独处理。本机 Library 材料化仍受官方 helper 的 os.setxattr Windows 缺失限制；父线程已正式查看原附件，本 executor 只查看新生成的实际 Qt 图，没有冒称自己看过原附件。','']
(out/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
(out/'tool_versions.json').write_text(json.dumps({'python':'3.14.0','arm_gcc':'14.3.1 20250623 / Arm GNU 14.3.Rel1','host_gcc':'16.1.0 Rev5 MSYS2','make':'4.4.1','make_parallel_limit':2,'QT_QPA_PLATFORM':'windows','shared_venv':'D:/python_software/SilverStar/.venv (read-only, no installation)'},indent=2)+'\n',encoding='utf-8')
hashes={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file() and p.name!='evidence_hashes.json' and p.suffix!='.ini' and '__pycache__' not in p.parts}
(out/'evidence_hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
print('Packaged report,',len(build),'gate results,',len(hashes),'evidence files.')
