"""Seal the final fresh pair separately from preserved earlier proof epochs."""
import json
from pathlib import Path
import shutil

import package_boards

ROOT = Path(__file__).resolve().parents[4]
DEST = ROOT / 'dist/pf1117-boards-current'
WORK = ROOT / '.work/platform-finish-20261116/boards'


def Main_Run():
    if DEST.exists():
        raise ValueError('Never overwrite a previous delivery')
    for relative, count in (('candidate-p-Flight_Controller-final-validation/receipt.json', 12),
                             ('ssgs-current-validation/receipt.json', 14)):
        receipt = json.loads((WORK / relative).read_text(encoding='utf8'))
        if len(receipt['commands']) != count or not receipt['inputs_unchanged'] or any(
                row['exit_code'] for row in receipt['commands']):
            raise ValueError('Final actual gates incomplete: ' + relative)
    DEST.mkdir()
    pair = DEST / 'SSFC_SSGS'
    rows = package_boards.CopyTree_Verify(WORK / 'candidate-p', pair)
    shutil.copy2(ROOT / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject', pair / 'SSFC1_0_SSGS1_0.ssproject')
    (pair / 'README_ZH.txt').write_text(
        'SSFC1.0 / SSGS1.0 最终源码 fresh 生成软件候选；不是已验证实板。\n'
        '先将完整ZIP解压到短路径（例如 D:/SS10），在SCG打开根目录 SSFC1_0_SSGS1_0.ssproject。\n'
        '两个板型均内置；无需CubeMX导入。先核对板型/封装/晶振/引脚/传感器安装及算法假设。\n'
        '第三页选择生成两端，并明确设定自己的新输出目录；不要把旧工作区绝对路径当本机输出路径。\n'
        '源码SCG保存的生成authority与便携EXE不同；用新EXE生成后，才按该EXE当前配置执行构建/检查。\n'
        '生成、保存、计算/导出各有独立语义；改配置不得沿用旧栈证明。\n'
        '本包完整保留 fresh 生成项目、Release/Debug ELF/BIN/MAP/.su及严格栈报告、解码包。\n'
        '原记录来自源码commit 6fed5b639d0835de7874a74db25a63ab0da814ad，实际H7十二/C071十四门禁均退出0。\n'
        '编译器要求 Arm GNU14.3.Rel1，GNU Make及Host GCC；将工具目录和Python加入PATH。\n'
        '在解压根目录执行（Windows示例）：\n'
        'mingw32-make -C Flight_Controller CONFIG=Release all artifact-check architecture-check power10-check static-analysis stack-report\n'
        'mingw32-make -C Ground_Station CONFIG=Release all artifact-check architecture-check power10-check static-analysis host-tests stack-report\n'
        'CONFIG=Debug 检查另一配置；H7可显式增加 GCC_PATH="<Arm GNU14.3.Rel1的bin目录>"。\n'
        '原始命令在正式boards/runs证据中记录。原报告绑定原编译物和随包分析工具；移动后可运行检查生成本地报告。\n'
        'SSFC：H743ZIT6/LQFP144、25MHz HSE假设；SSGS：C071FBP6/TSSOP20 GP、HSI48假设。\n'
        'PC13 START仅测试指示，不是点火驱动；无硬件烧写/连接/执行器动作。\n'
        '硬件连线/电源/时序/栈高水位/RF/存储/校准/导航仍待实测，软件上界不是飞行资格。\n', encoding='utf8')
    package_boards.DEST = DEST
    package = package_boards.Package_Create(pair, 'SSFC1_0_SSGS1_0_Current.zip',
        'Final fresh source-authority pair, Flight index30 and Ground index4; no hardware qualification')
    receipt = {'hardware_tested': False, 'source_copy_rows': rows, 'packages': [package],
        'prior_epoch_preserved': 'dist/pf1117-boards/SSFC1_0_SSGS1_0.zip'}
    (DEST / 'delivery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps(package, indent=2))


if __name__ == '__main__':
    Main_Run()
