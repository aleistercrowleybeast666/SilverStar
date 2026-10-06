"""Data-only, bounded, immutable project artifacts. No pickle or executable types."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

import numpy as np

from silverstar_flp.core.context import TaskContext

ARTIFACT_VERSION = 1
MAX_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_ARRAY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_ARRAYS = 4096
MAX_NODES = 8_000_000
MAX_SAMPLES = 20_000_000
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def FileHash_Get(path: Path, context: TaskContext | None = None) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            if context is not None:
                context.Cancel_RaiseIfRequested()
            digest.update(chunk)
    return digest.hexdigest()


def IdentityHash_Get(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def EngineIdentity_Get() -> str:
    """Hash executable math and input contracts, independent of Git/UI changes."""
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "plugins" / "algorithms").rglob("*.py"))
    files += sorted((root / "decoder_profiles").glob("*.py"))
    files += [root / "plugins/api/algorithm.py"]
    files += sorted((root / "core").glob("*.py"))
    files = [path for path in files if path.stem not in (
        "i18n", "path_preferences", "project", "artifacts", "parse_cache")]
    return IdentityHash_Get({str(path.relative_to(root)): FileHash_Get(path) for path in files})


@lru_cache(maxsize=1)
def _Types_Get() -> dict[str, type]:
    from silverstar_flp.core.dataset import DecodedRecord, FlightDataset, TimeSeries
    from silverstar_flp.core.diagnostics import (
        Diagnostic, DiagnosticSeverity, DamagedSpan, ParserDiagnostics,
        DataQualitySummary, DataQualityStatus,
    )
    from silverstar_flp.core.semantic_context import (
        DecoderPackageIdentity, CalibrationSnapshot, DatasetSemanticContext,
    )
    from silverstar_flp.plugins.api.algorithm import AlgorithmResult, ReplayFidelity, ReplayMode
    types = (DecodedRecord, FlightDataset, TimeSeries, Diagnostic, DiagnosticSeverity,
             DamagedSpan, ParserDiagnostics, DataQualitySummary, DataQualityStatus,
             DecoderPackageIdentity, CalibrationSnapshot, DatasetSemanticContext,
             AlgorithmResult, ReplayFidelity, ReplayMode)
    return {item.__name__: item for item in types}


def _Json_Load(path: Path) -> object:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("artifact_manifest_too_large")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("artifact_duplicate_key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("artifact_json_constant_invalid:" + value)
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=invalid)


def ArtifactPath_Resolve(project_path: Path, reference: Mapping) -> Path:
    name = reference.get("path")
    sha = reference.get("sha256")
    if (not isinstance(name, str) or not isinstance(sha, str) or not _HASH.fullmatch(sha)
            or "\\" in name or ":" in name or "\x00" in name):
        raise ValueError("artifact_reference_invalid")
    relative = Path(name)
    if relative.is_absolute() or any(part in ("..", ".") for part in relative.parts):
        raise ValueError("artifact_path_invalid")
    if (len(relative.parts) != 3 or relative.parts[0] != Path(project_path).name + ".artifacts"
            or not re.fullmatch(r"generation-[0-9a-f]{32}", relative.parts[1])
            or relative.parts[2] != "manifest.json"):
        raise ValueError("artifact_path_invalid")
    parent = Path(project_path).resolve().parent
    resolved = (parent / relative).resolve()
    if not resolved.is_relative_to(parent) or resolved == parent:
        raise ValueError("artifact_path_escape")
    return resolved


class _Encoder:
    def __init__(self, directory: Path, context: TaskContext):
        self.directory = directory
        self.context = context
        self.arrays = {}
        self.objects = {}
        self.nodes = 0
        self.total = 0

    def Encode(self, value, depth=0):
        self.nodes += 1
        if self.nodes % 4096 == 0:
            self.context.Cancel_RaiseIfRequested()
        if depth > 64 or self.nodes > MAX_NODES:
            raise ValueError("artifact_structure_limit")
        if isinstance(value, Enum):
            return {"enum": type(value).__name__, "value": value.value}
        if value is None or type(value) in (str, bool, int):
            return value
        if isinstance(value, np.generic):
            # Preserve scalar storage type, including values in audit diagnostics.
            return {"scalar": value.dtype.str, "value": self.Encode(value.item(), depth + 1)}
        if type(value) is float:
            return value if math.isfinite(value) else {"float": repr(value)}
        if isinstance(value, Path):
            return {"path": str(value)}
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        if isinstance(value, np.ndarray):
            if value.dtype.kind not in "biuf" or value.ndim > 4 or value.nbytes > MAX_ARRAY_BYTES:
                raise ValueError("artifact_array_invalid")
            temporary = self.directory / "array.tmp"
            with temporary.open("wb") as target:
                np.save(target, value, allow_pickle=False)
                target.flush()
                os.fsync(target.fileno())
            sha = FileHash_Get(temporary, self.context)
            name = sha + ".npy"
            if name not in self.arrays:
                size = temporary.stat().st_size
                self.total += size
                if len(self.arrays) >= MAX_ARRAYS or self.total > MAX_TOTAL_BYTES:
                    raise ValueError("artifact_size_limit")
                self.arrays[name] = {"sha256": sha, "bytes": size,
                                     "dtype": value.dtype.str, "shape": list(value.shape)}
                os.replace(temporary, self.directory / name)
            else:
                temporary.unlink()
            return {"array": name}
        if is_dataclass(value) and type(value).__name__ in _Types_Get():
            key = id(value)
            if key in self.objects:
                return {"ref": self.objects[key]}
            index = len(self.objects)
            self.objects[key] = index
            return {"type": type(value).__name__, "id": index,
                    "fields": {f.name: self.Encode(getattr(value, f.name), depth + 1)
                               for f in fields(value)}}
        if isinstance(value, Mapping):
            return {"map": [[self.Encode(k, depth + 1), self.Encode(v, depth + 1)]
                            for k, v in value.items()]}
        if isinstance(value, (tuple, list)):
            return {"tuple" if isinstance(value, tuple) else "list":
                    [self.Encode(item, depth + 1) for item in value]}
        raise ValueError("artifact_type_unsupported:" + type(value).__name__)


class _Decoder:
    def __init__(self, directory, arrays, context):
        self.directory, self.arrays, self.context = directory, arrays, context
        self.objects = {}
        self.loaded_arrays = {}
        self.nodes = 0
        self.total = 0
        if not isinstance(arrays, dict) or len(arrays) > MAX_ARRAYS:
            raise ValueError("artifact_array_table_invalid")
        for name, spec in arrays.items():
            if not isinstance(spec, dict) or name != str(spec.get("sha256")) + ".npy":
                raise ValueError("artifact_array_path_invalid")
            if not _HASH.fullmatch(spec["sha256"]):
                raise ValueError("artifact_array_hash_invalid")
            size = spec.get("bytes")
            shape = spec.get("shape")
            dtype = np.dtype(spec.get("dtype"))
            if (type(size) is not int or not 0 < size <= MAX_ARRAY_BYTES + 65536
                    or dtype.kind not in "biuf" or not isinstance(shape, list)
                    or len(shape) > 4 or any(type(n) is not int or not 0 <= n <= MAX_SAMPLES
                                           for n in shape)
                    or math.prod(shape) * dtype.itemsize > MAX_ARRAY_BYTES):
                raise ValueError("artifact_array_limits_invalid")
            self.total += size
        if self.total > MAX_TOTAL_BYTES:
            raise ValueError("artifact_size_limit")

    def Decode(self, value, depth=0):
        self.nodes += 1
        if self.nodes % 4096 == 0:
            self.context.Cancel_RaiseIfRequested()
        if self.nodes > MAX_NODES or depth > 64:
            raise ValueError("artifact_structure_limit")
        if value is None or type(value) in (str, bool, int, float):
            return value
        if not isinstance(value, dict):
            raise ValueError("artifact_node_invalid")
        if set(value) == {"array"}:
            name = value["array"]
            if name not in self.arrays:
                raise ValueError("artifact_array_missing")
            if name not in self.loaded_arrays:
                spec = self.arrays[name]
                path = (self.directory / name).resolve()
                if not path.is_relative_to(self.directory.resolve()):
                    raise ValueError("artifact_array_path_escape")
                if path.stat().st_size != spec["bytes"] or FileHash_Get(path, self.context) != spec["sha256"]:
                    raise ValueError("artifact_array_corrupt")
                # Inspect the header before allocating; shape may not be trusted from NPY bytes.
                with path.open("rb") as source:
                    version = np.lib.format.read_magic(source)
                    if version == (1, 0):
                        shape, order, dtype = np.lib.format.read_array_header_1_0(source)
                    elif version == (2, 0):
                        shape, order, dtype = np.lib.format.read_array_header_2_0(source)
                    else:
                        raise ValueError("artifact_npy_version_invalid")
                    if (list(shape) != spec["shape"] or dtype.str != spec["dtype"]
                            or dtype.kind not in "biuf" or
                            source.tell() + math.prod(shape) * dtype.itemsize != spec["bytes"]):
                        raise ValueError("artifact_array_header_invalid")
                array = np.load(path, allow_pickle=False)
                array.setflags(write=False)
                self.loaded_arrays[name] = array
            return self.loaded_arrays[name]
        if set(value) == {"ref"}:
            return self.objects[value["ref"]]
        if set(value) == {"type", "id", "fields"}:
            cls = _Types_Get().get(value["type"])
            if cls is None or not is_dataclass(cls) or set(value["fields"]) != {f.name for f in fields(cls)}:
                raise ValueError("artifact_class_invalid")
            index = value["id"]
            if type(index) is not int or index < 0 or index in self.objects:
                raise ValueError("artifact_object_identity_invalid")
            decoded = {key: self.Decode(item, depth + 1) for key, item in value["fields"].items()}
            if cls.__name__ == "TimeSeries":
                if (not isinstance(decoded["timestamp_us"], np.ndarray)
                        or decoded["timestamp_us"].dtype != np.dtype("uint64")
                        or not isinstance(decoded["valid"], np.ndarray)
                        or decoded["valid"].dtype != np.dtype("bool")
                        or not isinstance(decoded["values"], np.ndarray)
                        or decoded["values"].dtype.kind not in "biuf"
                        or decoded["values"].ndim not in (1, 2)):
                    raise ValueError("artifact_series_contract_invalid")
            result = cls(**decoded)
            self.objects[index] = result
            return result
        if set(value) == {"enum", "value"}:
            cls = _Types_Get().get(value["enum"])
            if cls is None or not issubclass(cls, Enum):
                raise ValueError("artifact_enum_invalid")
            return cls(value["value"])
        if set(value) == {"scalar", "value"}:
            dtype = np.dtype(value["scalar"])
            if dtype.kind not in "biuf":
                raise ValueError("artifact_scalar_invalid")
            return dtype.type(self.Decode(value["value"], depth + 1))
        if set(value) == {"map"}:
            result = {}
            for key, item in value["map"]:
                key = self.Decode(key, depth + 1)
                if type(key) not in (str, int) or key in result:
                    raise ValueError("artifact_mapping_key_invalid")
                result[key] = self.Decode(item, depth + 1)
            return result
        if set(value) in ({"tuple"}, {"list"}):
            key = next(iter(value))
            items = [self.Decode(item, depth + 1) for item in value[key]]
            return tuple(items) if key == "tuple" else items
        if set(value) == {"float"} and value["float"] in ("nan", "inf", "-inf"):
            return float(value["float"])
        if set(value) == {"path"}:
            return Path(value["path"])
        if set(value) == {"bytes"}:
            return bytes.fromhex(value["bytes"])
        raise ValueError("artifact_node_invalid")


def Artifact_Write(project_path: Path, payload: object, identity: dict,
                   context: TaskContext | None = None) -> dict:
    context = context or TaskContext()
    context.Cancel_RaiseIfRequested()
    parent = Path(project_path).resolve().parent
    root = parent / (Path(project_path).name + ".artifacts")
    if not root.resolve().is_relative_to(parent):
        raise ValueError("artifact_path_escape")
    root.mkdir(parents=True, exist_ok=True)
    directory = root / ("generation-" + uuid.uuid4().hex)
    directory.mkdir()
    # Interrupted generations are deliberately never referenced or auto-deleted.
    encoder = _Encoder(directory, context)
    encoded = encoder.Encode(payload)
    manifest = {"version": ARTIFACT_VERSION, "identity": identity,
                "arrays": encoder.arrays, "payload": encoded}
    path = directory / "manifest.json"
    with path.open("w", encoding="utf-8", newline="\n") as target:
        json.dump(manifest, target, allow_nan=False, separators=(",", ":"), ensure_ascii=False)
        target.flush()
        os.fsync(target.fileno())
    reference = {"path": path.relative_to(parent).as_posix(),
                 "sha256": FileHash_Get(path, context),
                 "bytes": encoder.total + path.stat().st_size}
    Artifact_Read(project_path, reference, identity, context)
    context.Cancel_RaiseIfRequested()
    return reference


def Artifact_Read(project_path: Path, reference: Mapping, identity: dict | None = None,
                  context: TaskContext | None = None):
    context = context or TaskContext()
    path = ArtifactPath_Resolve(project_path, reference)
    if path.stat().st_size > MAX_MANIFEST_BYTES or FileHash_Get(path, context) != reference["sha256"]:
        raise ValueError("artifact_manifest_corrupt")
    manifest = _Json_Load(path)
    if (not isinstance(manifest, dict) or set(manifest) != {"version", "identity", "arrays", "payload"}
            or manifest.get("version") != ARTIFACT_VERSION):
        raise ValueError("artifact_version_unsupported")
    if identity is not None and manifest.get("identity") != identity:
        raise ValueError("artifact_identity_mismatch")
    decoder = _Decoder(path.parent, manifest["arrays"], context)
    result = decoder.Decode(manifest["payload"])
    if set(decoder.loaded_arrays) != set(decoder.arrays):
        raise ValueError("artifact_unreferenced_arrays")
    return result
