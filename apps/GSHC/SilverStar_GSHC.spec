# -*- mode: python ; coding: utf-8 -*-
import runpy
from pathlib import Path

product_resource = runpy.run_path(str(Path(SPECPATH) / "packaging/product_version.py"))["ProductVersionResource_Create"]()
shared = Path(SPECPATH).resolve().parent / 'SCG/src'
datas = [(str(shared / 'silverstar_diagnostics/stm32_targets.json'), 'silverstar_diagnostics'),
         (str(Path(SPECPATH).resolve().parents[1] / 'contracts/swd_diagnostics_v1.json'), 'silverstar_diagnostics')]
repository = Path(SPECPATH).resolve().parents[1]
datas += [(str(repository / name), str(Path(name).parent)) for name in ("VERSION", "versions.json", "tools/silverstar_version.py")]
binaries = []
hiddenimports = [
    "OpenGL.platform.win32",
    "pyqtgraph.opengl",
]


a = Analysis(
    ["main.py"],
    pathex=[str(shared)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": "Agg"}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SilverStar_GSHC",
    version=product_resource,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SilverStar_GSHC",
)
