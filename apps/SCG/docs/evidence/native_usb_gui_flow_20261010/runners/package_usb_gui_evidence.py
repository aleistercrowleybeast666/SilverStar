from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess

task=Path(__file__).parent
repo=Path(r'D:\python_software\SilverStar\.work\ccdi')
code='63771a17e63052c238246dd4fe3fe6394de8ccec'
production='f91f82e4a0b4e83bb583c39b86a3d98f150cccf2'
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==code
status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip()
assert status in ['', '?? apps/SCG/docs/evidence/native_usb_gui_flow_20261010/'],status
changed=subprocess.check_output(['git','-C',str(repo),'diff','--name-only',production,code],text=True).splitlines()
assert changed==['apps/SCG/tests/test_usb_gui_flow.py'],changed
archive=repo/'apps/SCG/docs/evidence/native_usb_gui_flow_20261010'
if archive.exists():
    # Resume only our unfinished archive; every previously copied byte must
    # match its same source. Never delete an existing artifact tree.
    assert not archive.is_symlink() and not archive.is_junction()
    assert not (archive/'verification.json').exists()
    assert (archive/'.gitattributes').read_bytes()==b'* -text\n'
else:
    archive.mkdir(parents=True)
(archive/'.gitattributes').write_bytes(b'* -text\n')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(p,relative):
    p=Path(p);dest=archive/relative
    dest.parent.mkdir(parents=True,exist_ok=True)
    body=p.read_bytes()
    if dest.exists():
        assert dest.read_bytes()==body,('existing archive bytes differ',relative)
    else:dest.write_bytes(body)
def tree(root,relative):
    for p in sorted(Path(root).rglob('*')):
        if p.is_file():copy(p,relative+'/'+p.relative_to(root).as_posix())

records={'code_commit':code,'production_sources_identical_to':production,
 'created_utc':datetime.now(timezone.utc).isoformat(),
 'formal_release':False,'independent_usb_safety_review':'NO_PASSED_OUTCOME; stopped b66 review not retried or bypassed',
 'normal_tests':{},'builds':[],'history':{},'gates':{}}
for label,expected,count in [('ug08',code,12),('ue01',code,2),('ul17',production,2),('ugr02',production,99)]:
    record=json.loads((task/(label+'-command.json')).read_text(encoding='utf8'))
    assert record['source_commit']==expected and record['exit']==0,label
    log=(task/(label+'.log')).read_text(encoding='utf8')
    assert not re.search(r'\d+ (?:failed|error|skipped)',log),label
    assert int(re.findall(r'(\d+) passed',log)[-1])==count,label
    records['normal_tests'][label]={'passed':count,'skipped':0,'source_commit':expected,'scope':record['scope']}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'runs/'+p.name)
for p in sorted(Path(r'C:\Users\chdxm\AppData\Local\Temp\ul17').glob('test_normal*/lifecycle-receipt.json')):
    d=json.loads(p.read_text());assert len(d['runs'])==17 and all(r['exit']==0 for r in d['runs'])
    records.setdefault('lifecycle_runs',[]).append(d)
    tree(p.parent,'host/'+d['part'])
assert len(records['lifecycle_runs'])==2
for label in ['ug01','ug02','ug03','ug04','ug05','ug06','ug07','ul15','ul16','ugr01']:
    p=task/(label+'-command.json');d=json.loads(p.read_text())
    records['history'][label]={'exit':d['exit'],'source_commit':d['source_commit'],
                              'receipt_sha256':sha(p)}
    for suffix in ['.log','-command.json','-build-index.jsonl']:
        p=task/(label+suffix)
        if p.is_file():copy(p,'history/'+p.name)
for label in ['ugg01','ugg02']:
    gates=json.loads((task/(label+'-gates.json')).read_text())
    assert len(gates)==8 and all(g['exit']==0 for g in gates),label
    records['gates'][label]=gates
    copy(task/(label+'-gates.json'),('runs/' if label=='ugg02' else 'history/')+label+'-gates.json')
    for p in task.glob(label+'-*.log'):copy(p,('runs/' if label=='ugg02' else 'history/')+p.name)
rows=[json.loads(line) for line in (task/'ug08-build-index.jsonl').read_text().splitlines()]
assert {r['part'] for r in rows}=={'STM32F103C8T6','STM32C071FBP6'}
for row in rows:
    root=Path(row['output']);part=row['part'];project=Path(row['project_root'])
    receipt=json.loads((root/'receipt.json').read_text());backend=json.loads((root/'backend-receipt.json').read_text())
    pointer=json.loads((project/'.fccg/usb-candidate.json').read_text())
    snapshot=json.loads((root/'source-snapshot.json').read_text())
    assert receipt['source_commit']==code and receipt['auditable_dirty_diff']==''
    assert snapshot['source_commit']==code and snapshot['dirty_diff']==''
    assert receipt['status']=='NATIVE_SOURCE_CPP_GAS_ARM_LINK_AND_ANALYZER_EXECUTED'
    assert len(receipt['commands'])==receipt['planned_command_total'] and all(c['exit']==0 for c in receipt['commands'])
    assert receipt['warning_diagnostics']==[]
    assert any('-fanalyzer' in c['command'] for c in receipt['commands'])
    assert backend['model_sha256']==receipt['runtime_model_sha256']==pointer['model_sha256']
    assert backend['compile_receipt_sha256']==sha(root/'receipt.json')
    assert row['backend_receipt_sha256']==pointer['backend_receipt_sha256']==sha(root/'backend-receipt.json')
    assert pointer['output']==str(root) and pointer['result']=='CompiledCandidate' and pointer['formal_release'] is False
    runtime=project/'SilverStar.ssproject'
    assert sha(runtime)==sha(root/'candidate_config.ssproject')
    assert receipt['runtime_project']==str(runtime.resolve()) and receipt['runtime_project_sha256']==sha(runtime)
    assert backend['snapshot_root']==receipt['snapshot_root'] if part=='STM32C071FBP6' else True
    for p,digest in {**receipt['experimental_files_sha256'],**receipt['output_artifact_sha256']}.items():
        assert sha(root/p)==digest,(part,p)
    prefix='HardwareGenerated/STM32CubeMX/' if part=='STM32C071FBP6' else 'HardwareGenerated/NativeClassicCdc/'
    for p,digest in receipt['input_sha256'].items():assert sha(root/(prefix+p))==digest,(part,p)
    quality=json.loads((root/'.fccg/quality-results.json').read_text())
    assert {a for a in quality['results']}=={'architecture_check','artifact_check'}
    assert all(v['result']=='passed' for v in quality['results'].values())
    q_summary={a:{k:v[k] for k in ['duration','result','timestamp','command','input_sha256']} for a,v in quality['results'].items()}
    fact={'part':part,'output':str(root),'project_root':str(project),
        'model_sha256':receipt['runtime_model_sha256'],'runtime_project_sha256':sha(runtime),
        'snapshot_root':receipt['snapshot_root'],'source_snapshot_sha256':sha(root/'source-snapshot.json'),
        'backend_receipt_sha256':sha(root/'backend-receipt.json'),'compile_receipt_sha256':sha(root/'receipt.json'),
        'commands':len(receipt['commands']),'toolchain_version':receipt['toolchain_version'],
        'irq_header_sha256':receipt['facts']['irq_header_sha256'],
        'elf_sha256':{p:sha(root/p) for p in ['build/native.elf','build/analysis/native.elf']},
        'gui_quality':q_summary,'input_files':len(receipt['input_sha256']),
        'generated_files':len(receipt['experimental_files_sha256']),'recorded_artifacts':len(receipt['output_artifact_sha256'])}
    records['builds'].append(fact)
    tree(project,'final/'+part+'/saved_project')
    for f in root.rglob('*'):
        if not f.is_file():continue
        relative=f.relative_to(root).as_posix()
        keep=(relative.startswith(('Generated/','Common/','Ground/','Devices/','Platform/','HardwareGenerated/Reviewed','HardwareGenerated/C071ClassicCDC/','Middlewares/Reviewed','Tools/','.fccg/')) or
              relative in ['Makefile','receipt.json','backend-receipt.json','backend-owner.json','candidate_config.ssproject','commands.log','source-snapshot.json','Ground_Station.code-workspace'] or
              (relative.startswith('build/') and (f.suffix in ['.elf','.map','.su','.bin'] or '/host/' in relative)))
        if keep:copy(f,'final/'+part+'/'+relative)
entry_paths=list(Path(r'C:\Users\chdxm\AppData\Local\Temp\ue01').rglob('ordinary-user-entry.json'))
assert len(entry_paths)==2,entry_paths
for p in entry_paths:
    d=json.loads(p.read_text());assert d['backend_loaded_private_model'] is False
    tree(p.parent,'ordinary-entry/'+d['part']+'/saved_project')
    root=Path(d['output'])
    # Export records the exact model hash in its backend receipt; the existing
    # saved_project above retains the model. candidate_config is Build-only.
    for p in [root/'backend-receipt.json',root/'Makefile']:
        copy(p,'ordinary-entry/'+d['part']+'/rendered/'+p.name)
for p in ['usb-gui-visual-boundary.json','USB_GUI_CHECKPOINT_20261010.md','USB_GUI_WIRING_BLOCKED_20261010.md',
          'usb-gui-wiring-proposal.diff','usb-gui-wiring-proposal.json']:
    if (task/p).is_file():copy(task/p,'history/'+p)
for folder in ['usb-gui-visual','usb-gui-visual-settled']:
    tree(task/folder,'visual/'+folder)
records['visual_scope']={'render_commit':production,'final_production_ui_identical':True,
 'scope':'Same unbound reference model offscreen 1280x820 only; first unsettled font-state comparison retained',
 'settled_two_pages_pixel_identical':True}
review=Path(r'C:\Users\chdxm\Documents\Codex\2026-10-09\task-2\lifecycle-80db-c55-review')
for name in ['review.md','review-summary.json','audit.json','independent-public-return/evidence.json']:
    copy(review/name,'parent-ordinary-review/'+name)
records['parent_review_scope']='Existing 80db/c55 ordinary review and F103 P2 repro only; not a review of final GUI source or stopped b66 safety attempt'
for name in ['package_usb_gui_evidence.py','run_usb_gui_tests.py','run_existing_usb_user_entry.py','test_existing_usb_user_entry.py',
             'run_gui_preserved_regression.py','run_lifecycle_normal.py','run_usb_candidate_gates.py','backend_pytest.py',
             'verify_gui_visual_boundary.py','capture_gui_visual_compare.py','recapture_gui_visual_compare.py','inspect_visual_state.py']:
    copy(task/name,'runners/'+name)
for name in ['app/usb_ground_flow.py','app/usb_ground.py','app/native_ground.py','build/native_compile.py','ui/main_window.py','ui/pages/build.py','generator/native_control.py']:
    copy(repo/('apps/SCG/src/silverstar_fccg/'+name),'owning-source/'+name)
for name in ['test_usb_gui_flow.py','test_usb_lifecycle_normal.py']:
    copy(repo/('apps/SCG/tests/'+name),'owning-source/tests/'+name)
records['daily_head']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','rev-parse','HEAD'],text=True).strip()
records['daily_status']=subprocess.check_output(['git','-C',r'D:\python_software\SilverStar','status','--porcelain'],text=True).splitlines()
assert records['daily_head']=='56448bd35736221d7885a26704f2f953b0fe5055'
records['eight_validation_categories_per_target']=['ordinary existing GUI workflow','separate actual ordinary lifecycle Host','normal ARM compile/link','analyzer ARM compile/link','emitted architecture command','emitted ordinary Host command','emitted artifact/object-CPU/ELF/independent-IRQ command','unchanged emitted Power-of-Ten command']
records['gate_command_count']=8
records['gate_count_note']='Four generated gate commands per target (eight total), plus four recorded GUI/lifecycle/normal-link/analyzer-link validation categories per target; not sixteen emitted gate commands'
records['retention_scope']='Complete final receipts, source-snapshot JSON, commands, saved exact model/pointer/results, selected generated/derived/Tools sources, normal+analyzer ELF/maps/stack usage, Host fixtures/executables and historical logs. Vendor originals are byte-pinned by the complete input inventory and earlier archives; intermediate objects remain in original outputs. No large vendor tree duplicated.'
records['files_sha256']={p.relative_to(archive).as_posix():sha(p) for p in sorted(archive.rglob('*')) if p.is_file()}
(archive/'verification.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8',newline='\n')

report=f'''# 第一批 USB 普通产品接线与软件验证 — 2026-10-10

最终测试/构建提交 `{code}`；产品源代码与 `{production}` 完全相同，63771a1 仅改变真实 ARM 质量审计测试的有界等待。独立工作树 `D:\\python_software\\SilverStar\\.work\\ccdi`，分支 `feature/scg-classic-cdc-contract-20261009`。没有自行 merge/push，日用 HEAD 保持 `56448bd35736221d7885a26704f2f953b0fe5055`。

直接用户回复“允许”后，原 GUI 写入审批已通过；先前两次执行前拒绝已解决。此授权不覆盖 b66 独立 USB 安全审查。该审查仍 `NO_PASSED_OUTCOME`，未重试、未绕过、未标已审。以下均是普通功能、生成、构建和软件证据。

## 已有普通用户入口

原有 Ground Station Hardware 页的 PC 接口选项已有 `USB CDC Virtual Serial`。普通新建项目默认单 E28/SX1281、SX128x AIR 配置：选 USB，然后原有“导入 CubeMX 目录/IOC”按钮读取 exact native source，应用完整后端绑定模型；原有保存/打开保持模型；原有 Ground“生成”按钮进行 candidate Plan/Export；Build 页原有 Ground Build 按钮进行 candidate Build。源码在正常 MainWindow/FccgService 中调用，不依赖 SILVERSTAR_USB_BACKEND_ARM 之类测试开关。

`ue01` 从 `ProjectDraft_Create` 普通默认模型开始，删除 private model/admission 环境，实际操作已有 USB 下拉框、目录导入按钮、保存/重载和生成按钮，两款均成功。它没有另做 ARM 编译；`ug08` 则通过相同正常 MainWindow Build action signal/真实 worker 路径完成两款 normal/analyzer 编译与质量检查。文件选择对话框与 QMessageBox 在 offscreen 测试中被替换，业务 backend/compiler/worker 没有替换。未声称真实桌面鼠标或新建向导像素验收。

生成与编译是已有独立按钮操作，不能把配置、目录选择与两次操作称为一个无需配置的整包按钮。每次生成/Build 使用新的 disjoint sibling `usb-<id>`，模型记录在所选项目，目录和 receipts 从 UI 日志/已有打开目录/VSCode/产物操作可见。native HAL/CMSIS/startup/linker/clock/GPIO/IRQ/PCD/middleware 原件保持所有权，窄范围 derivatives 保留 patches 与原件/派生 hash。不会覆盖原生输入或用户项目 payload。

## 本轮软件可用性限制

| 条件/门禁 | 对已有按钮的具体影响 | 状态 |
|---|---|---|
| exact target/native profile | 仅 F103C8T6/72MHz、C071FBP6/48MHz 的已 pin 完整工程；F407/其他芯片、时钟、变动源集拒绝 | 明确首批范围，未删检查 |
| radio/资源/LED 配置 | 单 `radio0` E28/SX1281、SPI1 与各板固定 NSS/reset/busy/DIO1；无此候选未适配的活动 LED | 不静默改用户配置；不符拒绝 |
| independent SDK IRQ/header 与 C071 companion | 每次 import/Plan 验证 SDK bytes/enums；C071 使用 builtin byte-pinned companion。SDK 位置可通过明确 location env 设置，不能借此改变信任描述 | 缺失或 hash 不符时明确错误，不颁发能力 |
| 工具 | 编译须有配置/探测到的 ARM GCC；normal/analyzer/对象/ELF/IRQ/内存核对均实际运行。Host/PoT 还需对应 Host GCC/PowerShell | Build 不需要 Make；工具缺失阻断相应操作 |
| model/source/artifact identity | 保存模型、snapshot、backend/compiler receipts、所有记录源/产物 hash 必须一致 | 过期 ELF 被实际 GUI 拒绝，重新生成/Build |
| 正式一般生成/Generate All | 独立 candidate Ground 操作可用；正式 general generation guard 保留，Generate All 不把此候选与 Flight 静默组合 | 显示软件候选与 formal release BLOCKED |
| b66 独立安全审查 | 不阻止这条明确候选普通软件工作流；阻止把它报告为已安全审查/正式发布 | NO_PASSED_OUTCOME |
| manual critical-contract、whole-program stack/WCET | 工具通过不构成语义验收、完整栈或 STM32 WCET 证明 | NOT PROVEN，不 relabel PASS |
| PCD/PMA/IRQ 运行/物理 USB | Host 不执行原生 controller/IRQ interleaving；未进行板上行为/全部异步交错证明 | 本轮未测；硬件不是本轮软件完成前提 |

状态与 logs 明确保留 release notice。`static_analysis` 动作检查已有成功 analyzer receipt 和产物，不伪造新的独立 analyzer/review。Clean 仅删除已验证候选的 build 目录并撤销成功 pointer，保留源/日志/receipt。未以内存余量代替栈证明。

## 正常缺陷与超时定位

父 ordinary review 的 F103 P2：`USBD_LL_Reset`/`USBD_LL_DevDisconnected` 丢弃 class DeInit/CloseEP 失败。4926f77 在 owning generator 传播返回并保持原来的失败保留资源路径。ul17 对每款 actual core/class/interface/stream 执行 17 个正常场景（含 Reset/Disconnect 清理失败及重试、suspend/resume/reset/disconnect），共 34 次执行，2 pytest tests，不把 scenario 数写成 pytest 数。LL/PCD、Cortex、UID/allocator accounting 是明确 Host 替身。

ug07 GUI 结果保持为 11 passed/1 failed：C071 artifact quality audit 超过旧通用 10 秒测试 helper 的等待。ug08 产品源代码未变，只将这一真实 ARM 审计等待限定为 120 秒。最终 C071 architecture {next(b for b in records['builds'] if b['part']=='STM32C071FBP6')['gui_quality']['architecture_check']['duration']:.2f}s、artifact {next(b for b in records['builds'] if b['part']=='STM32C071FBP6')['gui_quality']['artifact_check']['duration']:.2f}s；真实命令退出、quality receipt 写 passed、worker 清空、GUI success 与 BLOCKED 同时断言通过，随后 stale ELF 拒绝断言通过。独立 ugg02 artifact 命令亦 exit 0。这支持正常审计预算不足，未观察卡死；不宣称所有未来工具进程有总超时证明。既有 runner 仍支持普通取消。

前期 ug03 状态文字被通用 completion 覆盖、ug06 资源表 generic gpio 类型分别已修，原断言保留。ug01/02 的 tuple/list 原始 Python 类型比较改用真实 JSON 序列化身份；ug04 测试 collection import 错误记录保留。旧失败不拼接成另一次全套 PASS。

## 最终执行结果

'''
for label,d in records['normal_tests'].items():
    report+=f"- `{label}`: {d['passed']} passed, 0 skipped，source `{d['source_commit']}`；{d['scope']}。\n"
for b in records['builds']:
    report+=f"- `{b['part']}`：{b['commands']} 实际命令均 exit 0，normal/analyzer link 成功，firmware/analyzer 零 diagnostics；normal ELF `{b['elf_sha256']['build/native.elf']}`，analyzer ELF `{b['elf_sha256']['build/analysis/native.elf']}`；完整 source-snapshot SHA256 `{b['source_snapshot_sha256']}`。\n"
report+='''
每款八项验证类别为：已有 GUI 流程、独立正常 lifecycle Host、normal ARM、analyzer ARM、生成架构、生成普通 Host、产物/实际对象 CPU 与独立 SDK IRQ/vector、原有 PoT。后四项是每款四条独立生成检查命令，`ugg02` 共八条全 exit 0；没有伪称每款八条 generated gate 命令或全仓库测试通过。所有实际对象和 ELF 的 CPU/ABI 及独立 SDK IRQ enum/vector 核对保留。

布局/控件/样式与原构造器保持：两个 UI 文件仅指定逻辑方法改变，另 24 个 UI 文件相同。相同普通未绑定参考模型经稳定 Qt font/geometry 状态后，Ground 与 Build offscreen1280x820 两张 PNG 像素完全相同；初次两像素字体状态差异证据仍保留。字体环境存在中文缺字，不能声称原生桌面全视觉验收。

现有 pytest unknown `cache_dir` 警告与 Host vendor unused-parameter 警告原样保存，区别于 firmware/analyzer 无诊断门禁。证据 manifest：`evidence/native_usb_gui_flow_20261010/verification.json`。归档包含完整 final source-snapshot、compiler/backend/model/result receipts、实际 commands/logs、两种 ELF/maps/.su、selected generated/derivatives/Tools、actual lifecycle Host fixtures/executable，以及失败/通过历史；未重复复制大 vendor 树，原件 hash/路径和早期 archives 仍作为 provenance。

F407 原候选和原计时报告保留，未新放行。日用仅三个已有 untracked inventory 文件；无 hardware/DAPLink/串口/flash/START、FINAL 修改、push 或 merge。此报告不是新的独立安全审查或正式通用固件交付；普通首批软件工作流完成后交父任务审查。
'''
path=repo/'apps/SCG/docs/NATIVE_USB_GUI_FLOW_20261010.md'
path.write_text(report,encoding='utf8',newline='\n');(task/path.name).write_text(report,encoding='utf8',newline='\n')
old=repo/'apps/SCG/docs/NATIVE_USB_LIFECYCLE_NORMAL_20261010.md'
old.write_text(old.read_text(encoding='utf8')+'\n\nLater scope note: the F103 ordinary Reset/Disconnect failure-return P2 and existing-widget GUI wiring gaps above were addressed in 4926f77/e782a33/f91f82e. Final normal software verification and exact build/source-snapshot identities are recorded in [NATIVE_USB_GUI_FLOW_20261010.md](NATIVE_USB_GUI_FLOW_20261010.md), tested code 63771a1. This retains the earlier report\'s original scope; b66 independent safety review remains NO_PASSED_OUTCOME.\n',encoding='utf8',newline='\n')
print(json.dumps({'code':code,'listed_files':len(records['files_sha256']),'manifest_sha256':sha(archive/'verification.json'),'report':str(path),'report_sha256':sha(path),'builds':records['builds']},indent=2))
