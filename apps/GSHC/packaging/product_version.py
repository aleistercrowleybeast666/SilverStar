"""Windows resource identity derived from the suite VERSION authority."""
from pathlib import Path


def ProductVersionResource_Create():
    from PyInstaller.utils.win32 import versioninfo

    root = Path(__file__).resolve().parents[3]
    version = (root / "VERSION").read_text(encoding="ascii").strip()
    parts = tuple(int(value) for value in version.split("."))
    if len(parts) != 3:
        raise ValueError("Product version requires major.minor.patch")
    template = Path(__file__).with_name("version_info.txt").read_text(encoding="utf-8")
    text = template.replace("@PRODUCT_VERSION_TUPLE@", repr((*parts, 0)))
    text = text.replace("@PRODUCT_VERSION@", version)
    # Only the trusted, repository-owned resource template is evaluated, using
    # the same VSVersionInfo format consumed by PyInstaller's resource loader.
    return eval(text, {**vars(versioninfo), "__builtins__": {}})
