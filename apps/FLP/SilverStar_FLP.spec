# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
import runpy
from PyInstaller.utils.win32 import versioninfo

repository = Path(SPECPATH).resolve().parents[1]
release = runpy.run_path(str(repository / "tools/silverstar_version.py"))["ReleaseIdentity_Load"](repository)
resource = versioninfo.VSVersionInfo(ffi=versioninfo.FixedFileInfo(filevers=release.windows, prodvers=release.windows),
    kids=[versioninfo.StringFileInfo([versioninfo.StringTable("040904B0", [
        versioninfo.StringStruct("ProductName", "SilverStar FLP"),
        versioninfo.StringStruct("FileVersion", release.full),
        versioninfo.StringStruct("ProductVersion", release.full)])])])

datas = collect_data_files("silverstar_flp") + collect_data_files("matplotlib")
datas += [(str(repository / name), str(Path(name).parent)) for name in ("VERSION", "versions.json", "tools/silverstar_version.py")]
hiddenimports = (
    collect_submodules("pyqtgraph.opengl")
    + collect_submodules("OpenGL")
    + collect_submodules("PIL")
)

analysis = Analysis(
    ["main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)
executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SilverStar_FLP",
    version=resource,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
distribution = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="SilverStar_FLP",
)
