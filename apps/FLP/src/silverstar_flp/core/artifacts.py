"""Data-only, bounded, immutable project artifacts. No pickle or executable types."""
from __future__ import annotations

import hashlib
import gzip
import json
import math
import os
import re
import shutil
import stat
import sys
import uuid
import zlib
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import numpy as np

from silverstar_flp.core.context import TaskContext

ARTIFACT_VERSION = 3
MAX_MANIFEST_BYTES = 256 * 1024 * 1024
MAX_ARRAY_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
MAX_ARRAYS = 4096
MAX_NODES = 8_000_000
MAX_SAMPLES = 20_000_000
MAX_COLUMNS = 4096
MAX_LIVE_BYTES = 1024 * 1024 * 1024
MAX_OBJECTS = 2_000_000
MAX_RECORD_BLOCKS = 4096
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_IO_CHUNK_BYTES = 1024 * 1024


class _ProgressStream:
    """Keep NumPy's NPY format, but bound gzip work and cancellation latency."""
    def __init__(self, stream, context, total, code, *, offset=None):
        self.stream, self.context, self.total, self.code = stream, context, total, code
        self.done = 0
        self.offset = offset

    def _Report(self, count):
        self.done += count
        done = self.done if self.offset is None else self.offset + self.done
        total = self.total if self.offset is None else 0
        self.context.Progress_Report(min(1, self.done / max(1, self.total)),
            f"{self.code}|{done}|{total}")

    def write(self, data):
        view = memoryview(data).cast('B')
        if self.done == 0 and self.code == "progress.artifact.array_write":
            # np.save writes the complete NPY header before the array payload.
            self.total += len(view)
        for start in range(0, len(view), _IO_CHUNK_BYTES):
            self.context.Cancel_RaiseIfRequested()
            chunk = view[start:start + _IO_CHUNK_BYTES]
            count = self.stream.write(chunk)
            if count != len(chunk):
                raise OSError("artifact_short_write")
            self._Report(count)
        return len(view)

    def read(self, size=-1):
        self.context.Cancel_RaiseIfRequested()
        chunk = self.stream.read(_IO_CHUNK_BYTES if size < 0 else min(size, _IO_CHUNK_BYTES))
        self._Report(len(chunk))
        return chunk

    def __getattr__(self, name):
        return getattr(self.stream, name)


def FileHash_Get(path: Path, context: TaskContext | None = None, *, quantified=False) -> str:
    info = _File_Require(Path(path), context=context)
    digest = hashlib.sha256()
    done = 0
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            if context is not None:
                context.Cancel_RaiseIfRequested()
            digest.update(chunk)
            done += len(chunk)
            if context is not None:
                context.Progress_Report(done / max(1, info.st_size) if quantified else 0,
                    f"progress.artifact.hash|{done}|{info.st_size}")
    return digest.hexdigest()


def _File_Require(path: Path, *, limit: int | None = None, context=None):
    if context is not None:
        context.Cancel_RaiseIfRequested()
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("artifact_file_not_regular")
    if limit is not None and info.st_size > limit:
        raise ValueError("artifact_file_too_large")
    return info


def IdentityHash_Get(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def EngineIdentity_Get() -> str:
    """Hash executable math and input contracts, independent of Git/UI changes."""
    root = Path(__file__).resolve().parents[1]
    files = sorted(path for path in (root / "plugins" / "algorithms").rglob("*")
                   if path.suffix in (".py", ".c", ".h", ".json"))
    files += sorted((root / "analysis").rglob("*.py"))
    files += sorted((root / "decoder_profiles").glob("*.py"))
    files += [root / "plugins/api/algorithm.py"]
    files += [root / "core" / name for name in (
        "math.py", "mission.py", "context.py", "runtime.py", "semantic_columns.py",
        "dataset.py", "diagnostics.py", "semantic_context.py", "replay_execution.py")]
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


def _Json_Load(path: Path, context: TaskContext | None = None, *, byte_limit=None,
               expected_bytes=None, return_size=False) -> object:
    limit = MAX_MANIFEST_BYTES if byte_limit is None else min(byte_limit, MAX_MANIFEST_BYTES)
    _File_Require(path, limit=limit, context=context)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("artifact_duplicate_key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("artifact_json_constant_invalid:" + value)
    opener = gzip.open if path.suffix == ".gz" else open
    chunks, size = [], 0
    try:
        with opener(path, "rb") as source:
            while chunk := source.read(1024 * 1024):
                if context is not None:
                    context.Cancel_RaiseIfRequested()
                size += len(chunk)
                if size > limit:
                    raise ValueError("artifact_manifest_too_large")
                chunks.append(chunk)
                if context is not None:
                    context.Progress_Report(0, f"progress.artifact.json_read|{size}|{expected_bytes or 0}")
    except (zlib.error, EOFError) as exc:
        raise ValueError("artifact_compression_corrupt") from exc
    try:
        if expected_bytes is not None and size != expected_bytes:
            raise ValueError("artifact_record_block_size_invalid")
        if context is not None:
            context.Progress_Report(0, f"progress.artifact.json_decode|{size}|0")
        result = json.loads(b"".join(chunks), object_pairs_hook=pairs, parse_constant=invalid)
        if context is not None:
            context.Cancel_RaiseIfRequested()
        return (result, size) if return_size else result
    except RecursionError as exc:
        raise ValueError("artifact_structure_limit") from exc


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
            or relative.parts[2] not in ("manifest.json", "manifest.json.gz")):
        raise ValueError("artifact_path_invalid")
    parent = Path(project_path).resolve().parent
    candidate = parent
    for part in relative.parts:
        candidate = candidate / part
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("artifact_path_link_invalid")
    resolved = (parent / relative).resolve()
    if not resolved.is_relative_to(parent) or resolved == parent:
        raise ValueError("artifact_path_escape")
    return resolved


def _Array_Immutable(array):
    """Read-only views qualify only when every ndarray base is also read-only."""
    for _depth in range(8):
        if type(array) is bytes:
            return True
        if not isinstance(array, np.ndarray) or array.flags.writeable:
            return False
        if array.base is None:
            return True
        array = array.base
    return False


class _Encoder:
    def __init__(self, directory: Path, context: TaskContext):
        self.directory = directory
        self.context = context
        self.arrays = {}
        self.objects = {}
        self.nodes = 0
        self.total = 0
        self.existing_arrays = {}
        self.record_files = {}
        self.record_rows = 0
        self.record_json_bytes = 0
        self.in_audit_block = False
        self.in_record_plan = False
        self.array_bytes_written = 0
        # Dataset/channel arrays are immutable. Reuse an exact owned read-only
        # object within this write, avoiding repeated compression/fsync of aliases.
        # Keep the object alive so a later block cannot reuse its Python id.
        self.immutable_arrays = {}
        generations = list(directory.parent.iterdir())
        if len(generations) > 4096:
            raise ValueError("artifact_generation_limit")
        for previous in generations:
            self.context.Progress_Report(0, f"progress.artifact.inventory|{len(self.existing_arrays)}|0")
            if previous == directory or not re.fullmatch(r"generation-[0-9a-f]{32}", previous.name):
                continue
            info = previous.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400):
                continue
            for candidate in previous.iterdir():
                if re.fullmatch(r"[0-9a-f]{64}\.npy\.gz", candidate.name):
                    self.existing_arrays.setdefault(candidate.name, candidate)

    def _Items_Encode(self, values, depth, *, mapping_entries=False):
        """Completed fields/items, not elapsed time or estimated remaining work."""
        from silverstar_flp.core.task_progress import TaskProgress
        progress = TaskProgress(self.context)
        parent_context = self.context
        encoded = []
        count = len(values)
        for index, value in enumerate(values):
            self.context = progress.Context_Build(index / count, (index + 1) / count)
            try:
                encoded.append([self.Encode(value[0], depth), self.Encode(value[1], depth)]
                               if mapping_entries else self.Encode(value, depth))
            finally:
                self.context = parent_context
            progress.Progress_Report((index + 1) / count,
                                     f"progress.artifact.objects|{index + 1}|{count}")
        return encoded

    def Encode(self, value, depth=0):
        self.nodes += 1
        if self.nodes % 4096 == 0:
            self.context.Progress_Report(0, f"progress.artifact.objects|{self.nodes}|0")
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
            if (value.dtype.kind not in "biuf" or value.ndim > 4 or value.nbytes > MAX_ARRAY_BYTES
                    or any(n > MAX_COLUMNS for n in value.shape[1:])):
                raise ValueError("artifact_array_invalid")
            reusable = _Array_Immutable(value)
            cached = self.immutable_arrays.get(id(value)) if reusable else None
            if cached is not None and cached[0] is value:
                self.context.Cancel_RaiseIfRequested()
                return {"array": cached[1]}
            temporary = self.directory / "array.tmp"
            if shutil.disk_usage(self.directory).free < value.nbytes + 32 * 1024 * 1024:
                raise ValueError("artifact_disk_space_insufficient")
            with temporary.open("wb") as target:
                with gzip.GzipFile(filename="", mode="wb", fileobj=target,
                                   compresslevel=3, mtime=0) as compressed:
                    stream = _ProgressStream(compressed, self.context, value.nbytes,
                                             "progress.artifact.array_write", offset=self.array_bytes_written)
                    np.save(stream, value, allow_pickle=False)
                    raw_bytes = compressed.tell()
                    self.array_bytes_written += raw_bytes
                self.context.Progress_Report(0, "progress.artifact.sync")
                target.flush()
                os.fsync(target.fileno())
            sha = FileHash_Get(temporary, self.context)
            name = sha + ".npy.gz"
            if name not in self.arrays:
                size = temporary.stat().st_size
                self.total += size
                if len(self.arrays) >= MAX_ARRAYS or self.total > MAX_TOTAL_BYTES:
                    raise ValueError("artifact_size_limit")
                self.arrays[name] = {"sha256": sha, "bytes": size,
                                     "dtype": value.dtype.str, "shape": list(value.shape),
                                     "raw_bytes": raw_bytes, "compression": "gzip"}
                previous = self.existing_arrays.get(name)
                if previous is not None and FileHash_Get(previous, self.context) == sha:
                    try:
                        os.link(previous, self.directory / name)
                    except OSError:
                        os.replace(temporary, self.directory / name)
                    else:
                        temporary.unlink()
                else:
                    os.replace(temporary, self.directory / name)
            else:
                temporary.unlink()
            if reusable and len(self.immutable_arrays) < MAX_ARRAYS:
                self.immutable_arrays[id(value)] = (value, name)
            return {"array": name}
        if is_dataclass(value) and type(value).__name__ in _Types_Get():
            key = id(value)
            if key in self.objects:
                return {"ref": self.objects[key]}
            index = len(self.objects)
            self.objects[key] = index
            members = fields(value)
            if depth <= 2 and not self.in_record_plan and not self.in_audit_block:
                encoded = self._Items_Encode(tuple(getattr(value, f.name) for f in members), depth + 1)
                encoded_fields = {f.name: item for f, item in zip(members, encoded)}
            else:
                encoded_fields = {f.name: self.Encode(getattr(value, f.name), depth + 1) for f in members}
            return {"type": type(value).__name__, "id": index, "fields": encoded_fields}
        if isinstance(value, Mapping):
            key = "frozen_map" if isinstance(value, MappingProxyType) else "map"
            if depth <= 2 and not self.in_record_plan and not self.in_audit_block:
                return {key: self._Items_Encode(value.items(), depth + 1, mapping_entries=True)}
            return {key: [[self.Encode(k, depth + 1), self.Encode(v, depth + 1)]
                          for k, v in value.items()]}
        if isinstance(value, (tuple, list)):
            from silverstar_flp.core.dataset import DecodedRecord
            from silverstar_flp.core.record_blocks import RECORD_BLOCK_ROWS
            if (not self.in_audit_block and type(value) is tuple and value
                    and all(type(item) is DecodedRecord for item in value)):
                return self.RecordBlocks_Write(value)
            from silverstar_flp.core.audit_blocks import AUDIT_BLOCK_MIN_ROWS
            if (not self.in_audit_block and not self.in_record_plan
                    and len(value) >= AUDIT_BLOCK_MIN_ROWS
                    and all(isinstance(item, Mapping) and isinstance(item, MappingProxyType)
                            == isinstance(value[0], MappingProxyType)
                            and all(type(key) in (str, int) for key in item) for item in value)):
                return self.AuditBlocks_Write(value)
            encoded_items = (self._Items_Encode(value, depth + 1)
                if depth <= 2 and not self.in_record_plan and not self.in_audit_block
                else [self.Encode(item, depth + 1) for item in value])
            return {"tuple" if isinstance(value, tuple) else "list": encoded_items}
        raise ValueError("artifact_type_unsupported:" + type(value).__name__)

    def RecordBlocks_Write(self, records):
        from silverstar_flp.core.record_blocks import RecordBlock_Build, RECORD_BLOCK_ROWS, RECORD_BLOCK_BYTES
        self.record_rows += len(records)
        if self.record_rows > MAX_OBJECTS:
            raise ValueError("artifact_record_count_limit")
        references = []
        start = 0
        while start < len(records):
            self.context.Cancel_RaiseIfRequested()
            if len(references) >= MAX_RECORD_BLOCKS or len(self.record_files) >= MAX_RECORD_BLOCKS:
                raise ValueError("artifact_record_block_count_limit")
            rows = records[start:start + RECORD_BLOCK_ROWS]
            while True:
                self.context.Cancel_RaiseIfRequested()
                try:
                    block = RecordBlock_Build(rows)
                    break
                except ValueError as exc:
                    if str(exc) != "artifact_record_block_allocation_limit" or len(rows) == 1:
                        raise
                    # Reduce the row window BEFORE publishing arrays/files. This
                    # retains wide/raw decoder records within the same fixed bound.
                    rows = rows[:max(1, len(rows) // 2)]
            self.in_record_plan = True
            try:
                encoded = self.Encode(block)
            finally:
                self.in_record_plan = False
            temporary = self.directory / "records.tmp"
            raw_bytes = _Json_Write(temporary, encoded, self.context, RECORD_BLOCK_BYTES)
            self.record_json_bytes += raw_bytes
            if self.record_json_bytes > MAX_MANIFEST_BYTES:
                raise ValueError("artifact_manifest_too_large")
            sha = FileHash_Get(temporary, self.context)
            name = sha + ".records.json.gz"
            spec = {"name": name, "sha256": sha, "bytes": temporary.stat().st_size,
                    "raw_bytes": raw_bytes, "count": len(rows)}
            if name not in self.record_files:
                self.total += spec["bytes"]
                if self.total > MAX_TOTAL_BYTES:
                    raise ValueError("artifact_size_limit")
                os.replace(temporary, self.directory / name)
                self.record_files[name] = spec
            else:
                temporary.unlink()
            references.append(spec)
            start += len(rows)
            self.context.Progress_Report(start / len(records), f"progress.artifact.records|{start}|{len(records)}")
        return {"record_blocks": references}

    def AuditBlocks_Write(self, rows):
        from silverstar_flp.core.audit_blocks import AuditBlock_Build
        from silverstar_flp.core.record_blocks import RECORD_BLOCK_ROWS, RECORD_BLOCK_BYTES
        references, start = [], 0
        self.record_rows += len(rows)
        if self.record_rows > MAX_OBJECTS:
            raise ValueError("artifact_record_count_limit")
        while start < len(rows):
            self.context.Cancel_RaiseIfRequested()
            if len(references) >= MAX_RECORD_BLOCKS or len(self.record_files) >= MAX_RECORD_BLOCKS:
                raise ValueError("artifact_record_block_count_limit")
            window = rows[start:start + RECORD_BLOCK_ROWS]
            while True:
                try:
                    block = AuditBlock_Build(window)
                    break
                except ValueError as exc:
                    if str(exc) != "artifact_record_block_allocation_limit" or len(window) == 1:
                        raise
                    window = window[:max(1, len(window) // 2)]
            self.in_audit_block = True
            try:
                encoded = self.Encode(block)
            finally:
                self.in_audit_block = False
            temporary = self.directory / "audit.tmp"
            raw_bytes = _Json_Write(temporary, encoded, self.context, RECORD_BLOCK_BYTES)
            self.record_json_bytes += raw_bytes
            if self.record_json_bytes > MAX_MANIFEST_BYTES:
                raise ValueError("artifact_manifest_too_large")
            sha = FileHash_Get(temporary, self.context)
            name = sha + ".audit.json.gz"
            spec = {"name": name, "sha256": sha, "bytes": temporary.stat().st_size,
                    "raw_bytes": raw_bytes, "count": len(window)}
            if name not in self.record_files:
                self.total += spec["bytes"]
                if self.total > MAX_TOTAL_BYTES:
                    raise ValueError("artifact_size_limit")
                os.replace(temporary, self.directory / name)
                self.record_files[name] = spec
            else:
                temporary.unlink()
            references.append(spec)
            start += len(window)
            self.context.Progress_Report(start / len(rows), f"progress.artifact.records|{start}|{len(rows)}")
        return {"audit_blocks": references, "tuple": isinstance(rows, tuple)}


def _Json_Write(path, value, context, limit):
    with path.open("wb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, compresslevel=3, mtime=0) as compressed:
            size, buffer = 0, bytearray()
            for chunk in json.JSONEncoder(allow_nan=False, separators=(",", ":"), ensure_ascii=False).iterencode(value):
                encoded_chunk = chunk.encode("utf-8")
                size += len(encoded_chunk)
                if size > limit:
                    raise ValueError("artifact_manifest_too_large")
                buffer.extend(encoded_chunk)
                if len(buffer) >= 65536:
                    context.Cancel_RaiseIfRequested()
                    compressed.write(buffer)
                    buffer.clear()
                    context.Progress_Report(0, f"progress.artifact.json_write|{size}|0")
            context.Cancel_RaiseIfRequested()
            compressed.write(buffer)
            context.Progress_Report(0, f"progress.artifact.json_write|{size}|0")
        context.Progress_Report(0, "progress.artifact.sync")
        target.flush()
        os.fsync(target.fileno())
    return size


class _ArrayDescription:
    def __init__(self, name, spec):
        self.name, self.shape, self.dtype = name, tuple(spec["shape"]), np.dtype(spec["dtype"])
        self.ndim, self.nbytes = len(self.shape), math.prod(self.shape) * self.dtype.itemsize


class _VerifiedRecords:
    def __init__(self, count):
        self.count = count


class _VerifiedWriteReference(dict):
    """One-use, in-process receipt for a streamed and fully verified write.

    It is never reconstructed from JSON. Consuming it releases the input pointer;
    project references remain ordinary serializable mapping data afterwards.
    This lets the unchanged dataset semantic validator inspect its original
    immutable input without decoding a second full copy or altering parser IDs.
    """
    def __init__(self, reference, payload, project_path, identity, context, files):
        super().__init__(reference)
        self.payload = payload
        self.project_path = Path(project_path).resolve()
        self.identity_hash = IdentityHash_Get(identity)
        self.reference_hash = IdentityHash_Get(reference)
        self.context = context
        self.files = tuple(files)


class _Decoder:
    def __init__(self, directory, arrays, context, *, allow_records=False, allow_audits=False,
                 verify_only=False, json_bytes=0):
        self.directory, self.arrays, self.context = directory, arrays, context
        self.objects = {}
        self.loaded_arrays = {}
        self.nodes = 0
        self.total = 0
        self.live_bytes = 0
        self.object_count = 0
        self.allow_records, self.verify_only = allow_records, verify_only
        self.allow_audits = allow_audits
        self.record_files, self.record_rows = {}, 0
        self.record_json_bytes = json_bytes
        self.in_record_block = False
        self.block_arrays = {}
        self.record_file_size = None
        self.array_bytes_done = 0
        if not isinstance(arrays, dict) or len(arrays) > MAX_ARRAYS:
            raise ValueError("artifact_array_table_invalid")
        for name, spec in arrays.items():
            if not isinstance(spec, dict) or name != str(spec.get("sha256")) + (
                    ".npy.gz" if spec.get("compression") == "gzip" else ".npy"):
                raise ValueError("artifact_array_path_invalid")
            if not _HASH.fullmatch(spec["sha256"]):
                raise ValueError("artifact_array_hash_invalid")
            size = spec.get("bytes")
            raw_size = spec.get("raw_bytes", size)
            shape = spec.get("shape")
            dtype = np.dtype(spec.get("dtype"))
            if (type(size) is not int or not 0 < size <= MAX_ARRAY_BYTES + 65536
                    or type(raw_size) is not int or not 0 < raw_size <= MAX_ARRAY_BYTES + 65536
                    or spec.get("compression") not in (None, "gzip")
                    or dtype.kind not in "biuf" or not isinstance(shape, list)
                    or len(shape) > 4 or any(type(n) is not int or not 0 <= n <= MAX_SAMPLES
                                           for n in shape)
                    or any(n > MAX_COLUMNS for n in shape[1:])
                    or math.prod(shape) * dtype.itemsize > MAX_ARRAY_BYTES):
                raise ValueError("artifact_array_limits_invalid")
            self.total += raw_size
        if self.total > MAX_TOTAL_BYTES:
            raise ValueError("artifact_size_limit")

    def Charge(self, objects, live_bytes):
        self.object_count += objects
        self.live_bytes += live_bytes
        if self.object_count > MAX_OBJECTS:
            raise ValueError("artifact_object_limit")
        if self.live_bytes > MAX_LIVE_BYTES:
            raise ValueError("artifact_live_memory_limit")

    def RecordBlocks_Read(self, references):
        from silverstar_flp.core.record_blocks import RecordBlock_Read, RECORD_BLOCK_BYTES, RECORD_BLOCK_ROWS
        if (not self.allow_records or self.in_record_block or not isinstance(references, list)
                or not 0 < len(references) <= MAX_RECORD_BLOCKS):
            raise ValueError("artifact_record_blocks_invalid")
        records, count = [], 0
        for spec in references:
            self.context.Cancel_RaiseIfRequested()
            if (not isinstance(spec, dict) or set(spec) != {"name", "sha256", "bytes", "raw_bytes", "count"}
                    or not isinstance(spec["sha256"], str) or not _HASH.fullmatch(spec["sha256"])
                    or spec["name"] != spec["sha256"] + ".records.json.gz"
                    or any(type(spec[key]) is not int for key in ("bytes", "raw_bytes", "count"))
                    or not 0 < spec["bytes"] <= RECORD_BLOCK_BYTES
                    or not 0 < spec["raw_bytes"] <= RECORD_BLOCK_BYTES
                    or not 0 < spec["count"] <= RECORD_BLOCK_ROWS):
                raise ValueError("artifact_record_block_reference_invalid")
            self.record_rows += spec["count"]
            self.record_json_bytes += spec["raw_bytes"]
            if self.record_rows > MAX_OBJECTS or self.record_json_bytes > MAX_MANIFEST_BYTES:
                raise ValueError("artifact_record_budget_limit")
            if self.total + self.record_json_bytes > MAX_TOTAL_BYTES:
                raise ValueError("artifact_size_limit")
            if len(self.record_files) >= MAX_RECORD_BLOCKS and spec["name"] not in self.record_files:
                raise ValueError("artifact_record_block_count_limit")
            if spec["name"] in self.record_files and self.record_files[spec["name"]] != spec:
                raise ValueError("artifact_record_block_reference_invalid")
            self.record_files[spec["name"]] = spec
            path = self.directory / spec["name"]
            info = _File_Require(path, limit=RECORD_BLOCK_BYTES, context=self.context)
            if info.st_size != spec["bytes"] or FileHash_Get(path, self.context) != spec["sha256"]:
                raise ValueError("artifact_record_block_corrupt")
            encoded = _Json_Load(path, self.context, byte_limit=RECORD_BLOCK_BYTES, expected_bytes=spec["raw_bytes"])
            self.in_record_block = True
            try:
                block = self.Decode(encoded)
                if not isinstance(block, dict) or block.get("count") != spec["count"]:
                    raise ValueError("artifact_record_block_count_invalid")
                restored = RecordBlock_Read(block, self.Charge, self.context,
                    retain=not self.verify_only, file_size=self.record_file_size)
                if not self.verify_only:
                    records.extend(restored)
                count += spec["count"]
            finally:
                self.in_record_block = False
                self.block_arrays.clear()
        return _VerifiedRecords(count) if self.verify_only else tuple(records)

    def AuditBlocks_Read(self, references, is_tuple):
        from silverstar_flp.core.audit_blocks import AuditBlock_Read
        from silverstar_flp.core.record_blocks import RECORD_BLOCK_BYTES, RECORD_BLOCK_ROWS
        if (not self.allow_audits or self.in_record_block or type(is_tuple) is not bool
                or not isinstance(references, list) or not 0 < len(references) <= MAX_RECORD_BLOCKS):
            raise ValueError("artifact_audit_blocks_invalid")
        rows, count = [], 0
        for spec in references:
            self.context.Cancel_RaiseIfRequested()
            if (not isinstance(spec, dict) or set(spec) != {"name", "sha256", "bytes", "raw_bytes", "count"}
                    or not isinstance(spec["sha256"], str) or not _HASH.fullmatch(spec["sha256"])
                    or spec["name"] != spec["sha256"] + ".audit.json.gz"
                    or any(type(spec[key]) is not int for key in ("bytes", "raw_bytes", "count"))
                    or not 0 < spec["bytes"] <= RECORD_BLOCK_BYTES
                    or not 0 < spec["raw_bytes"] <= RECORD_BLOCK_BYTES
                    or not 0 < spec["count"] <= RECORD_BLOCK_ROWS):
                raise ValueError("artifact_audit_block_reference_invalid")
            self.record_rows += spec["count"]
            self.record_json_bytes += spec["raw_bytes"]
            if self.record_rows > MAX_OBJECTS or self.record_json_bytes > MAX_MANIFEST_BYTES:
                raise ValueError("artifact_record_budget_limit")
            if self.total + self.record_json_bytes > MAX_TOTAL_BYTES:
                raise ValueError("artifact_size_limit")
            if len(self.record_files) >= MAX_RECORD_BLOCKS and spec["name"] not in self.record_files:
                raise ValueError("artifact_record_block_count_limit")
            if spec["name"] in self.record_files and self.record_files[spec["name"]] != spec:
                raise ValueError("artifact_audit_block_reference_invalid")
            self.record_files[spec["name"]] = spec
            path = self.directory / spec["name"]
            if _File_Require(path, limit=RECORD_BLOCK_BYTES).st_size != spec["bytes"] or FileHash_Get(path, self.context) != spec["sha256"]:
                raise ValueError("artifact_audit_block_corrupt")
            encoded = _Json_Load(path, self.context, byte_limit=RECORD_BLOCK_BYTES,
                                 expected_bytes=spec["raw_bytes"])
            self.in_record_block = True
            try:
                block = self.Decode(encoded)
                if not isinstance(block, dict) or block.get("count") != spec["count"]:
                    raise ValueError("artifact_audit_block_count_invalid")
                restored = AuditBlock_Read(block, self.Charge, self.context, retain=not self.verify_only)
                if not self.verify_only:
                    rows.extend(restored)
                count += spec["count"]
            finally:
                self.in_record_block = False
                self.block_arrays.clear()
        if self.verify_only:
            return _VerifiedRecords(count)
        return tuple(rows) if is_tuple else rows

    def Decode(self, value, depth=0):
        self.nodes += 1
        self.object_count += 1
        if self.object_count > MAX_OBJECTS:
            raise ValueError("artifact_object_limit")
        if self.nodes % 4096 == 0:
            self.context.Progress_Report(self.array_bytes_done / max(1, self.total),
                f"progress.artifact.objects|{self.nodes}|0")
        if self.nodes > MAX_NODES or depth > 64:
            raise ValueError("artifact_structure_limit")
        if value is None or type(value) in (str, bool, int, float):
            self.live_bytes += sys.getsizeof(value)
            if self.live_bytes > MAX_LIVE_BYTES:
                raise ValueError("artifact_live_memory_limit")
            return value
        if not isinstance(value, dict):
            raise ValueError("artifact_node_invalid")
        if set(value) == {"array"}:
            name = value["array"]
            if name not in self.arrays:
                raise ValueError("artifact_array_missing")
            target_arrays = self.block_arrays if self.verify_only and self.in_record_block else self.loaded_arrays
            if name not in target_arrays:
                spec = self.arrays[name]
                from silverstar_flp.core.task_progress import TaskProgress
                array_progress = TaskProgress(self.context)
                start = min(1, self.array_bytes_done / max(1, self.total))
                end = min(1, (self.array_bytes_done + spec.get("raw_bytes", spec["bytes"])) / max(1, self.total))
                hash_context = array_progress.Context_Build(start, start + (end-start)*0.3)
                read_context = array_progress.Context_Build(start + (end-start)*0.3, end)
                unresolved_path = self.directory / name
                info = _File_Require(unresolved_path, limit=MAX_ARRAY_BYTES + 65536,
                                     context=self.context)
                path = unresolved_path.resolve()
                if not path.is_relative_to(self.directory.resolve()):
                    raise ValueError("artifact_array_path_escape")
                if info.st_size != spec["bytes"] or FileHash_Get(path, hash_context, quantified=True) != spec["sha256"]:
                    raise ValueError("artifact_array_corrupt")
                # Inspect the header before allocating; shape may not be trusted from NPY bytes.
                opener = gzip.open if spec.get("compression") == "gzip" else open
                with opener(path, "rb") as source:
                    version = np.lib.format.read_magic(source)
                    if version == (1, 0):
                        shape, order, dtype = np.lib.format.read_array_header_1_0(source)
                    elif version == (2, 0):
                        shape, order, dtype = np.lib.format.read_array_header_2_0(source)
                    else:
                        raise ValueError("artifact_npy_version_invalid")
                    if (list(shape) != spec["shape"] or dtype.str != spec["dtype"]
                            or dtype.kind not in "biuf" or
                            source.tell() + math.prod(shape) * dtype.itemsize !=
                            spec.get("raw_bytes", spec["bytes"])):
                        raise ValueError("artifact_array_header_invalid")
                    source.seek(0)
                    stream = _ProgressStream(source, read_context, spec.get("raw_bytes", spec["bytes"]),
                                             "progress.artifact.array_read")
                    if name not in self.loaded_arrays:
                        self.Charge(0, math.prod(shape) * dtype.itemsize)
                    if self.verify_only and not self.in_record_block:
                        # Validate every expanded byte without allocating the complete
                        # numerical array. The full reader still uses np.load below.
                        while stream.read(65536):
                            self.context.Cancel_RaiseIfRequested()
                        if source.tell() != spec.get("raw_bytes", spec["bytes"]):
                            raise ValueError("artifact_array_trailing_bytes")
                        array = _ArrayDescription(name, spec)
                    else:
                        if self.verify_only:
                            from silverstar_flp.core.record_blocks import RECORD_BLOCK_ALLOC_BYTES
                            working_bytes = sum(item.nbytes for item in self.block_arrays.values())
                            if working_bytes + math.prod(shape) * dtype.itemsize > RECORD_BLOCK_ALLOC_BYTES:
                                raise ValueError("artifact_record_block_allocation_limit")
                        array = np.load(stream, allow_pickle=False)
                        if source.read(1):
                            raise ValueError("artifact_array_trailing_bytes")
                        array.setflags(write=False)
                target_arrays[name] = array
                if name not in self.loaded_arrays or target_arrays is self.loaded_arrays:
                    self.array_bytes_done += spec.get("raw_bytes", spec["bytes"])
                if self.verify_only and self.in_record_block:
                    self.loaded_arrays.setdefault(name, _ArrayDescription(name, spec))
            return target_arrays[name]
        if set(value) == {"record_blocks"}:
            return self.RecordBlocks_Read(value["record_blocks"])
        if set(value) == {"audit_blocks", "tuple"}:
            return self.AuditBlocks_Read(value["audit_blocks"], value["tuple"])
        if set(value) == {"ref"}:
            return self.objects[value["ref"]]
        if set(value) == {"type", "id", "fields"}:
            cls = _Types_Get().get(value["type"])
            if cls is None or not is_dataclass(cls) or set(value["fields"]) != {f.name for f in fields(cls)}:
                raise ValueError("artifact_class_invalid")
            index = value["id"]
            if type(index) is not int or index < 0 or index in self.objects:
                raise ValueError("artifact_object_identity_invalid")
            if cls.__name__ == "FlightDataset":
                size = value["fields"]["file_size"]
                if type(size) is not int or size < 0:
                    raise ValueError("parse_cache_dataset_invalid")
                self.record_file_size = size
            decoded = {key: self.Decode(item, depth + 1) for key, item in value["fields"].items()}
            if cls.__name__ == "TimeSeries":
                array_types = (np.ndarray, _ArrayDescription) if self.verify_only else (np.ndarray,)
                if (not isinstance(decoded["timestamp_us"], array_types)
                        or decoded["timestamp_us"].dtype != np.dtype("uint64")
                        or not isinstance(decoded["valid"], array_types)
                        or decoded["valid"].dtype != np.dtype("bool")
                        or not isinstance(decoded["values"], array_types)
                        or decoded["values"].dtype.kind not in "biuf"
                        or decoded["values"].ndim not in (1, 2)):
                    raise ValueError("artifact_series_contract_invalid")
                if (decoded["timestamp_us"].ndim != 1 or decoded["valid"].ndim != 1
                        or decoded["timestamp_us"].shape != decoded["valid"].shape
                        or decoded["values"].shape[0] != decoded["valid"].shape[0]
                        or decoded["columns"] and decoded["values"].ndim == 2
                        and len(decoded["columns"]) != decoded["values"].shape[1]):
                    raise ValueError("artifact_series_contract_invalid")
                if decoded["values"].ndim == 2 and decoded["values"].shape[1] > MAX_COLUMNS:
                    raise ValueError("artifact_series_columns_limit")
                if decoded["values"].ndim == 2 and not decoded["columns"]:
                    width = decoded["values"].shape[1]
                    self.object_count += width
                    self.nodes += width
                    self.live_bytes += sum(sys.getsizeof(f"[{index}]") for index in range(width))
                    if self.object_count > MAX_OBJECTS or self.nodes > MAX_NODES:
                        raise ValueError("artifact_object_limit")
                self.live_bytes += sum(decoded[name].nbytes for name in ("timestamp_us", "values", "valid"))
                if self.live_bytes > MAX_LIVE_BYTES:
                    raise ValueError("artifact_live_memory_limit")
                if self.verify_only:
                    _Timestamp_Verify(self.directory, decoded["timestamp_us"], self.arrays, self.context)
            if self.verify_only and cls.__name__ in ("FlightDataset", "TimeSeries", "AlgorithmResult"):
                result = {"validated_type": cls.__name__, "fields": decoded}
            else:
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
            raw = value["value"]
            if not (type(raw) in (bool, int, float) or
                    isinstance(raw, dict) and set(raw) == {"float"}):
                raise ValueError("artifact_scalar_invalid")
            decoded_scalar = self.Decode(raw, depth + 1)
            if type(decoded_scalar) not in (bool, int, float):
                raise ValueError("artifact_scalar_invalid")
            return dtype.type(decoded_scalar)
        if set(value) in ({"map"}, {"frozen_map"}):
            result = {}
            mapping_kind = next(iter(value))
            for key, item in value[mapping_kind]:
                key = self.Decode(key, depth + 1)
                if type(key) not in (str, int) or key in result:
                    raise ValueError("artifact_mapping_key_invalid")
                result[key] = self.Decode(item, depth + 1)
            return MappingProxyType(result) if mapping_kind == "frozen_map" else result
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
    from silverstar_flp.core.task_progress import TaskProgress
    progress = TaskProgress(context)
    progress.Progress_Report(0.0, "progress.artifact.prepare")
    context.Cancel_RaiseIfRequested()
    parent = Path(project_path).resolve().parent
    root = parent / (Path(project_path).name + ".artifacts")
    if root.exists() or root.is_symlink():
        info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError("artifact_path_link_invalid")
    if not root.resolve().is_relative_to(parent):
        raise ValueError("artifact_path_escape")
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < 32 * 1024 * 1024:
        raise ValueError("artifact_disk_space_insufficient")
    directory = root / ("generation-" + uuid.uuid4().hex)
    directory.mkdir()
    # Interrupted generations are deliberately never referenced or auto-deleted.
    serialize_context = progress.Context_Build(0.05, 0.60)
    encoder = _Encoder(directory, serialize_context)
    progress.Progress_Report(0.05, "progress.artifact.serialize")
    encoded = encoder.Encode(payload)
    manifest = {"version": ARTIFACT_VERSION, "identity": identity,
                "arrays": encoder.arrays, "payload": encoded}
    path = directory / "manifest.json.gz"
    progress.Progress_Report(0.62, "progress.artifact.manifest_write")
    manifest_context = progress.Context_Build(0.62, 0.62)
    manifest_raw_bytes = _Json_Write(path, manifest, manifest_context, MAX_MANIFEST_BYTES - encoder.record_json_bytes)
    reference = {"path": path.relative_to(parent).as_posix(),
                 "sha256": FileHash_Get(path, progress.Context_Build(0.65, 0.73), quantified=True),
                 "bytes": encoder.total + path.stat().st_size,
                 "uncompressed_bytes": manifest_raw_bytes +
                     sum(spec["raw_bytes"] for spec in encoder.arrays.values()) + encoder.record_json_bytes}
    progress.Progress_Report(0.75, "progress.artifact.verify")
    Artifact_Verify(project_path, reference, identity, progress.Context_Build(0.75, 0.97))
    context.Cancel_RaiseIfRequested()
    progress.Progress_Report(0.98, "progress.artifact.checked")
    from silverstar_flp.core.dataset import FlightDataset
    if type(payload) is FlightDataset:
        files = [(path, reference["sha256"], path.stat().st_size)]
        files += [(directory / name, spec["sha256"], spec["bytes"]) for name, spec in encoder.arrays.items()]
        files += [(directory / name, spec["sha256"], spec["bytes"]) for name, spec in encoder.record_files.items()]
        return _VerifiedWriteReference(reference, payload, project_path, identity, context, files)
    return reference


def Artifact_Read(project_path: Path, reference: Mapping, identity: dict | None = None,
                  context: TaskContext | None = None):
    if type(reference) is _VerifiedWriteReference and reference.payload is not None:
        payload, reference.payload = reference.payload, None
        receipt_context, files = reference.context, reference.files
        reference.context, reference.files = None, ()
        receipt_context.Cancel_RaiseIfRequested()
        if context is not None:
            context.Cancel_RaiseIfRequested()
        if (Path(project_path).resolve() != reference.project_path
                or IdentityHash_Get(identity) != reference.identity_hash
                or IdentityHash_Get(dict(reference)) != reference.reference_hash
                or context is not None and context is not receipt_context):
            raise ValueError("artifact_verification_receipt_invalid")
        ArtifactPath_Resolve(project_path, reference)
        # Recheck every persisted file before consuming the receipt. A modified,
        # missing, linked or corrupt file cannot be hidden by an in-process receipt.
        for path, sha, size in files:
            info = _File_Require(path, context=receipt_context)
            if info.st_size != size or FileHash_Get(path, receipt_context) != sha:
                raise ValueError("artifact_verification_receipt_corrupt")
        # The receipt was created only after Artifact_Verify read every persisted
        # byte and checked the same cumulative reader budgets. It cannot enter
        # an external/cache-open path; its input pointer is already cleared here.
        return payload
    return _Artifact_Load(project_path, reference, identity, context, verify_only=False)


def Artifact_Verify(project_path: Path, reference: Mapping, identity: dict | None = None,
                    context: TaskContext | None = None):
    """Read and validate all files with cumulative admission budgets, without
    retaining a duplicate full FlightDataset/AlgorithmResult during saving."""
    _Artifact_Load(project_path, reference, identity, context, verify_only=True)


def _Artifact_Load(project_path, reference, identity, context, *, verify_only):
    context = context or TaskContext()
    from silverstar_flp.core.task_progress import TaskProgress
    progress = TaskProgress(context)
    progress.Progress_Report(0.0, "progress.artifact.manifest_read")
    context.Cancel_RaiseIfRequested()
    path = ArtifactPath_Resolve(project_path, reference)
    _File_Require(path, limit=MAX_MANIFEST_BYTES, context=context)
    if FileHash_Get(path, progress.Context_Build(0.0, 0.08), quantified=True) != reference["sha256"]:
        raise ValueError("artifact_manifest_corrupt")
    manifest, json_bytes = _Json_Load(path, progress.Context_Build(0.08, 0.08), return_size=True)
    if (not isinstance(manifest, dict) or set(manifest) != {"version", "identity", "arrays", "payload"}
            or type(manifest.get("version")) is not int or manifest["version"] not in (1, 2, ARTIFACT_VERSION)):
        raise ValueError("artifact_version_unsupported")
    if identity is not None and manifest.get("identity") != identity:
        raise ValueError("artifact_identity_mismatch")
    progress.Progress_Report(0.20, "progress.artifact.verify" if verify_only else "progress.artifact.read")
    decoder = _Decoder(path.parent, manifest["arrays"], progress.Context_Build(0.20, 0.95), allow_records=manifest["version"] >= 2,
                       allow_audits=manifest["version"] >= 3,
                       verify_only=verify_only, json_bytes=json_bytes)
    try:
        result = decoder.Decode(manifest["payload"])
    except (zlib.error, EOFError, OverflowError, RecursionError) as exc:
        raise ValueError("artifact_payload_corrupt") from exc
    if set(decoder.loaded_arrays) != set(decoder.arrays):
        raise ValueError("artifact_unreferenced_arrays")
    progress.Progress_Report(0.98, "progress.artifact.checked")
    return result


def _Timestamp_Verify(directory, array, arrays, context):
    if isinstance(array, np.ndarray):
        if array.size > 1 and np.any(array[1:] < array[:-1]):
            raise ValueError("time-series timestamps must be monotonic")
        return
    spec = arrays[array.name]
    path = directory / array.name
    _File_Require(path, context=context)
    opener = gzip.open if spec.get("compression") == "gzip" else open
    with opener(path, "rb") as source:
        version = np.lib.format.read_magic(source)
        if version not in ((1, 0), (2, 0)):
            raise ValueError("artifact_npy_version_invalid")
        reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
        shape, order, dtype = reader(source)
        if tuple(shape) != array.shape or dtype != np.dtype("uint64"):
            raise ValueError("artifact_array_header_invalid")
        remaining, previous = math.prod(shape), None
        while remaining:
            context.Cancel_RaiseIfRequested()
            count = min(8192, remaining)
            raw = source.read(count * dtype.itemsize)
            if len(raw) != count * dtype.itemsize:
                raise ValueError("artifact_array_trailing_bytes")
            timestamps = np.frombuffer(raw, dtype=dtype)
            if (previous is not None and timestamps[0] < previous
                    or timestamps.size > 1 and np.any(timestamps[1:] < timestamps[:-1])):
                raise ValueError("time-series timestamps must be monotonic")
            previous, remaining = timestamps[-1], remaining - count
            context.Progress_Report(0,
                f"progress.artifact.timestamps|{math.prod(shape)-remaining}|{math.prod(shape)}")
        if source.read(1):
            raise ValueError("artifact_array_trailing_bytes")


def RecordFiles_Get(payload):
    """Declared files for conservative manual generation cleanup; full artifact
    verification remains mandatory before any deletion."""
    found, nodes = set(), 0
    def visit(value, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > 64:
            raise ValueError("artifact_structure_limit")
        if isinstance(value, dict):
            if set(value) == {"record_blocks"} or set(value) == {"audit_blocks", "tuple"}:
                audit = "audit_blocks" in value
                specs = value["audit_blocks" if audit else "record_blocks"]
                if not isinstance(specs, list) or len(specs) > MAX_RECORD_BLOCKS:
                    raise ValueError("artifact_record_blocks_invalid")
                for spec in specs:
                    name = spec.get("name") if isinstance(spec, dict) else None
                    suffix = "audit" if audit else "records"
                    if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}\." + suffix + r"\.json\.gz", name):
                        raise ValueError("artifact_record_block_reference_invalid")
                    found.add(name)
            else:
                for child in value.values():
                    visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)
    visit(payload)
    return found
