"""Windows resource identity derived from the suite VERSION authority."""
from pathlib import Path
import runpy


def ProductVersionResource_Create():
    from PyInstaller.utils.win32 import versioninfo

    root = Path(__file__).resolve().parents[3]
    release = runpy.run_path(str(root / "tools/silverstar_version.py"))["ReleaseIdentity_Load"](root)
    version = release.full
    parts = release.windows
    template = Path(__file__).with_name("version_info.txt").read_text(encoding="utf-8")
    text = template.replace("@PRODUCT_VERSION_TUPLE@", repr(parts))
    text = text.replace("@PRODUCT_VERSION@", version)
    # Only the trusted, repository-owned resource template is evaluated, using
    # the same VSVersionInfo format consumed by PyInstaller's resource loader.
    return eval(text, {**vars(versioninfo), "__builtins__": {}})
