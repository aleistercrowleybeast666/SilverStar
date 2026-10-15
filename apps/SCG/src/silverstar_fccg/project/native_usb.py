"""Data-only native USB references. Saved metadata never grants admission."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath


@dataclass(frozen=True, slots=True)
class NativeUsbReference:
    native_root: str
    source_sha256: str
    output_root: str = ""
    kit_sha256: str = ""
    graph_sha256: str = ""
    receipt_file: str = ""
    receipt_sha256: str = ""
    version: int = 1

    def Dictionary_Get(self) -> dict:
        return asdict(self)


def NativeUsbReference_Parse(value: object) -> NativeUsbReference:
    if not isinstance(value, dict) or set(value) != set(NativeUsbReference.__dataclass_fields__):
        raise ValueError("native_usb reference fields are invalid")
    if type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("native_usb reference version is unsupported")
    for field in ("native_root", "output_root"):
        path = value[field]
        if not isinstance(path, str) or len(path) > 4096 or any(c in path for c in "\0\r\n"):
            raise ValueError("native_usb path is invalid")
        if path and not (Path(path).is_absolute() or PureWindowsPath(path).is_absolute()):
            raise ValueError("native_usb paths must be absolute")
    for field in ("source_sha256", "kit_sha256", "graph_sha256", "receipt_sha256"):
        digest = value[field]
        if not isinstance(digest, str) or (digest and not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("native_usb digest is invalid")
    receipt = value["receipt_file"]
    if not isinstance(receipt, str) or (receipt and not re.fullmatch(
            r"(?:compile|analysis)-[0-9a-f]{32}/validation-receipt\.json", receipt)):
        raise ValueError("native_usb receipt path is invalid")
    if bool(receipt) != bool(value["receipt_sha256"]):
        raise ValueError("native_usb receipt reference is incomplete")
    if not value["native_root"] or not value["source_sha256"]:
        raise ValueError("native_usb requires an inspected native source")
    if bool(value["output_root"]) != bool(value["kit_sha256"] and value["graph_sha256"]):
        raise ValueError("native_usb output reference is incomplete")
    if not value["output_root"] and any(value[k] for k in ("kit_sha256", "graph_sha256", "receipt_sha256")):
        raise ValueError("native_usb evidence requires its output reference")
    return NativeUsbReference(**value)
