"""Copy owned final candidates, seal each file, ZIP and independently read back."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT / '.work/platform-finish-20261116/boards'
DEST = ROOT / 'dist/pf1117-boards'


def Digest_Get(raw):
    return hashlib.sha256(raw).hexdigest()


def CopyTree_Verify(source, destination):
    source = source.resolve(strict=True)
    rows = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('No aliased delivery inputs: ' + str(path))
        if not path.is_file() or '__pycache__' in path.relative_to(source).parts or path.suffix == '.pyc':
            continue
        if not path.resolve(strict=True).is_relative_to(source):
            raise ValueError('Input escaped its owned root')
        target = destination / path.relative_to(source)
        if target.exists() or len(str(target).encode('utf-16-le')) // 2 >= 260:
            raise ValueError('Existing or overlong delivery path: ' + str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if Digest_Get(path.read_bytes()) != Digest_Get(target.read_bytes()):
            raise ValueError('Delivery copy mismatch')
        rows.append({'source': str(path), 'target': str(target), 'sha256': Digest_Get(target.read_bytes())})
    return rows


def Package_Create(directory, name, description):
    rows = {p.relative_to(directory).as_posix(): {'bytes': p.stat().st_size, 'sha256': Digest_Get(p.read_bytes())}
            for p in sorted(directory.rglob('*')) if p.is_file()}
    manifest = {'purpose': description, 'hardware_tested': False,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'files': rows, 'file_count': len(rows), 'bytes': sum(row['bytes'] for row in rows.values())}
    (directory / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    expected = {p.relative_to(directory).as_posix(): Digest_Get(p.read_bytes()) for p in directory.rglob('*') if p.is_file()}
    archive = DEST / name
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
        for relative in sorted(expected):
            stream.write(directory / relative, relative)
    with zipfile.ZipFile(archive) as stream:
        if len(stream.namelist()) != len(set(stream.namelist())) or set(stream.namelist()) != set(expected):
            raise ValueError('ZIP entry set differs from the staged file set')
        for name, digest in expected.items():
            if Digest_Get(stream.read(name)) != digest:
                raise ValueError('Independent ZIP readback mismatch: ' + name)
    return {'zip': str(archive), 'zip_bytes': archive.stat().st_size, 'zip_sha256': Digest_Get(archive.read_bytes()),
            'manifest': str(directory / 'MANIFEST.json'), 'manifest_sha256': Digest_Get((directory / 'MANIFEST.json').read_bytes()),
            'readback_files': len(expected), 'readback_all_sha256_equal': True}


def Main_Run():
    if DEST.exists():
        raise ValueError('Never overwrite a prior delivery directory')
    DEST.mkdir(parents=True)
    pair = DEST / 'SSFC_SSGS'
    pair.mkdir()
    copied = []
    for target in ('Flight_Controller', 'Ground_Station'):
        copied.extend(CopyTree_Verify(WORK / 'candidate-o' / target, pair / target))
    shutil.copy2(ROOT / 'apps/SCG/examples/SSFC1_0_SSGS1_0.ssproject', pair / 'SSFC1_0_SSGS1_0.ssproject')
    (pair / 'README_ZH.txt').write_text(
        'SSFC1.0 / SSGS1.0 软件候选；硬件未验证。\n'
        'SCG 打开 SSFC1_0_SSGS1_0.ssproject；两板用内置插件，无需 CubeMX 导入。\n'
        '所附完整生成工程已含 Release/Debug ELF、BIN、MAP、依赖、严格栈报告与分析构建。\n'
        '使用 Arm GNU 14.3.Rel1 和 GNU Make；在本目录执行：\n'
        'mingw32-make -C Flight_Controller CONFIG=Release all artifact-check architecture-check power10-check static-analysis stack-report\n'
        'mingw32-make -C Ground_Station CONFIG=Release all artifact-check architecture-check power10-check static-analysis host-tests stack-report\n'
        '将 CONFIG 改为 Debug 可检查另一配置。原验证工具链位于 D:/Arm GNU Toolchain/14.3 rel1/bin。\n'
        '严格证明封印完整源、编译器和编译物，改配置或工具链后需重审；不是通用任意工程通过许可。\n'
        'SSFC 为 H743ZIT6/LQFP144、25MHz HSE 假设；SSGS 为 C071FBP6/TSSOP20 GP、HSI48 假设。\n'
        'PC13 START 仅测试指示，不是点火驱动。安装/噪声/时序/RF/存储/实板均待测。\n'
        '保存的检查日志记录原测试位置；移动/解压后运行检查可产生当前本地报告。\n', encoding='utf8')
    f103 = DEST / 'F103_E19'
    f103.mkdir()
    copied.extend(CopyTree_Verify(ROOT / '.work/pf1117/ground-m3-d/Ground_Station', f103 / 'Ground_Station'))
    copied.extend(CopyTree_Verify(ROOT / '.work/pf1117/ground-m3-input-d', f103 / 'software-inputs'))
    shutil.copy2(WORK / 'm3-d-model.ssproject', f103 / 'software-inputs/E19_Software.ssproject')
    (f103 / 'README_ZH.txt').write_text(
        'F103C8T6 + E19-433M20S2 地面站软件参考；不是用户PCB或实板验证。\n'
        '完整生成 Ground_Station 工程、Release/Debug产物、原始synthetic CubeMX输入/快照随包保留。\n'
        'SCG可打开 software-inputs/E19_Software.ssproject；这份参考模型同时含飞控配置，但本包只交付地面站。\n'
        '当前20KiB RAM保留8192B MSP，已用12540B（含8196B保留及对齐）、剩7940B。\n'
        '无RTOS、无FPU；MSP上界Release3912/Debug3424B，余量4280/4768B，包含16级IRQ与NMI/HardFault。\n'
        '使用 Arm GNU14.3.Rel1/GNU Make，在本目录执行：\n'
        'mingw32-make -C Ground_Station CONFIG=Release all artifact-check architecture-check power10-check static-analysis host-tests stack-report\n'
        'CONFIG=Debug 检查另一配置；变更输入/编译器将拒绝旧严格证明。\n'
        'E19 17dBm/SPI软件配置及连线是明确假设；空口、安装、时序、硬件高水位均未实测。\n', encoding='utf8')
    results = [Package_Create(pair, 'SSFC1_0_SSGS1_0.zip', 'Final current SSFC/SSGS pair; exact software evidence, not hardware qualification'),
               Package_Create(f103, 'F103_E19_Ground.zip', 'Final F103 E19 Ground software reference and immutable synthetic inputs')]
    receipt = {'hardware_tested': False, 'excluded_only': ['Python __pycache__ directories and .pyc caches'],
               'source_copy_rows': copied, 'packages': results}
    (DEST / 'delivery-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'packages': results, 'copied_files': len(copied)}, indent=2))


if __name__ == '__main__':
    Main_Run()
