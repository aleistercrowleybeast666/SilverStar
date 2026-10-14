# Three isolated analyses and executables; one shared dependency COLLECT.
from pathlib import Path
import json
import os
import subprocess
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

repository = Path(SPECPATH).resolve().parents[1]
tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repository).decode("utf-8").split("\0")
resource_prefixes = (
    "apps/SCG/src/", "apps/SCG/plugins/", "apps/SCG/schemas/", "apps/SCG/tools/",
    "apps/FLP/src/", "apps/GSHC/processing/", "apps/GSHC/protocol/",
    "apps/GSHC/services/", "apps/GSHC/transport/", "apps/GSHC/ui/", "contracts/",
)
resource_files = [name for name in tracked if name and (
    name.startswith(resource_prefixes) or name in {
        "VERSION", "apps/SCG/main.py", "apps/FLP/main.py", "apps/GSHC/main.py",
        "apps/GSHC/app.py", "apps/GSHC/config.py",
    })]
resource_files = [name for name in resource_files if name not in {"apps/SCG/tools/compare_reference_project.py", "apps/SCG/tools/nrf24_validate.py"}]
resources = [(str(repository / name), str(Path(name).parent)) for name in resource_files]
analyses = []
executables = []
removed = {}
for app, package in [("SCG", "silverstar_fccg.app.application"), ("GSHC", "app"), ("FLP", "silverstar_flp.app.application")]:
    app_root = repository / "apps" / app
    hidden = [package, "OpenGL.platform.win32"] + collect_submodules("pyqtgraph.opengl") + collect_submodules("OpenGL")
    reuse = os.environ.get("SILVERSTAR_REUSE_ANALYSIS")
    if reuse:
        # Normal builds analyze. This opt-in requires completed input analyses
        # and a separately recorded audit of unchanged app/dependency inputs.
        import ast
        from types import SimpleNamespace
        import hashlib
        index = len(analyses)
        cached = Path(reuse) / ("Analysis-%02d.toc" % index)
        manifest = json.loads((Path(reuse) / "manifest.json").read_text())
        expected = next(r["sha256"] for r in manifest["files"] if r["path"] == cached.name)
        if hashlib.sha256(cached.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Analysis input hash mismatch")
        toc = ast.literal_eval(cached.read_text(encoding="utf-8"))
        a = SimpleNamespace(pure=toc[14], binaries=toc[15], datas=toc[18], scripts=toc[13])
    else:
        a = Analysis(
            [str(Path(SPECPATH) / ("entry_" + app + ".py"))],
            pathex=[str(app_root), str(app_root / "src"), str(repository / "apps/SCG/src")],
            binaries=[], datas=resources if app == "SCG" else [], hiddenimports=hidden,
            hookspath=[], runtime_hooks=[],
            hooksconfig={"matplotlib": {"backends": ["Agg", "QtAgg"]}},
            excludes=["tkinter", "pytest", "IPython", "PyQt5", "PyQt6"],
            noarchive=False, optimize=0,
        )
    # Ship first-party source byte-for-byte at its original nested location.
    # The analysis still discovers its external imports; only its own PYZ entries
    # are removed, so __file__ and original relative resource paths stay valid.
    first_party = [row for row in a.pure if Path(row[1]).is_relative_to(repository / "apps") and ".venv" not in Path(row[1]).parts]
    removed[app] = [row[0] for row in first_party]
    a.pure = [row for row in a.pure if row not in first_party]
    # QtGui's default hook collects optional PDF/virtual-keyboard plugins.
    # These applications do not use them; do not redistribute their GPL-only
    # modules or the QtQuick/QML dependency tree introduced solely by them.
    unused_qt = {"qpdf.dll", "qtvirtualkeyboardplugin.dll", "Qt6Pdf.dll",
        "Qt6VirtualKeyboard.dll", "Qt6Qml.dll", "Qt6Quick.dll", "Qt6QmlModels.dll",
        "Qt6QmlMeta.dll", "Qt6QmlWorkerScript.dll"}
    a.binaries = [row for row in a.binaries if Path(row[0]).name not in unused_qt]
    # Qt's Windows wheel imports OS ICU without version-suffixed symbols.
    # PATH may contain Poppler's incompatible ICU; never redistribute that DLL.
    a.binaries = [row for row in a.binaries if Path(row[0]).name.lower() not in
        {"icuuc.dll", "icudt78.dll"}]
    # Use one CRT family already provided by the exact PySide6 wheel, rather
    # than a PATH-resolved FreeCAD copy and several competing wheel copies.
    import importlib.util
    qt_root = Path(importlib.util.find_spec("PySide6").origin).parent
    crt_names = {p.name.lower() for p in qt_root.glob("*.dll")
        if p.name.lower().startswith(("msvcp140", "vcruntime140"))}
    a.binaries = [row for row in a.binaries if Path(row[0]).name.lower() not in crt_names]
    a.binaries += [(p.name, str(p), "BINARY") for p in qt_root.glob("*.dll")
        if p.name.lower() in crt_names]
    # Developer-only reference comparison contains original machine paths and
    # is not required by the normal application. Keep it in the source repo.
    a.datas = [row for row in a.datas if row[0].replace("\\", "/") not in {
        "apps/SCG/tools/compare_reference_project.py", "apps/SCG/tools/nrf24_validate.py"}]
    # PyOpenGL ships optional 32-bit DLL variants; a Win64 interpreter cannot
    # load them. Keep the unchanged 64-bit variants and their original notices.
    def incompatible_opengl(row):
        if not row[0].replace("\\", "/").startswith("OpenGL/DLLS/"):
            return False
        import struct
        with open(row[1], "rb") as stream:
            head = stream.read(64)
            if head[:2] != b"MZ": return False
            stream.seek(struct.unpack_from("<I", head, 60)[0])
            return stream.read(6)[4:] == b"\x4c\x01"
    a.binaries = [row for row in a.binaries if not incompatible_opengl(row)]
    pyz = PYZ(a.pure)
    version_text = (repository / "VERSION").read_text(encoding="ascii").strip()
    version = tuple(int(v) for v in version_text.split(".")) + (0,)
    resource = VSVersionInfo(ffi=FixedFileInfo(filevers=version, prodvers=version,
        mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
        kids=[StringFileInfo([StringTable("040904B0", [StringStruct("ProductName", "SilverStar"),
            StringStruct("FileDescription", "SilverStar " + app), StringStruct("FileVersion", version_text),
            StringStruct("ProductVersion", version_text), StringStruct("OriginalFilename", app + ".exe")])]),
            VarFileInfo([VarStruct("Translation", [1033,1200])])])
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=app, version=resource,
        debug=False, strip=False, upx=False, console=False,
        contents_directory="_internal", disable_windowed_traceback=False)
    analyses.append(a)
    executables.append(exe)
# Refuse a shared destination name if the analyses resolve different file bytes.
seen = {}
for a in analyses:
    for name, source, kind in [*a.binaries, *a.datas]:
        if name in seen and Path(source).is_file() and Path(seen[name]).is_file():
            import hashlib
            if hashlib.sha256(Path(source).read_bytes()).digest() != hashlib.sha256(Path(seen[name]).read_bytes()).digest():
                raise RuntimeError("Conflicting shared dependency: " + name)
        seen[name] = source
import shutil
if shutil.disk_usage(repository).free < 8 * 1024**3:
    raise RuntimeError("D free space below 8 GiB; collection stopped")
collection = COLLECT(*executables, *[a.binaries for a in analyses],
    *[a.datas for a in analyses], strip=False, upx=False, name="SilverStar")
Path(os.environ["SILVERSTAR_PACKAGE_EVIDENCE"]).joinpath("first-party-pyz-removal.json").write_text(
    json.dumps(removed, indent=2), encoding="utf-8")
