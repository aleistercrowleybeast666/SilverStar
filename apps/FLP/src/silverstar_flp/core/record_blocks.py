"""Columnar record blocks with immutable, lazily materialized payload rows.

Only trusted cache code constructs the row views. No object arrays, pickle,
imports from serialized data, or mutation of the input records are involved.
"""
from collections.abc import Mapping
from dataclasses import fields
import math
import struct
import sys
from types import MappingProxyType

import numpy as np

from silverstar_flp.core.dataset import DecodedRecord

RECORD_BLOCK_ROWS = 4096
RECORD_BLOCK_BYTES = 8 * 1024 * 1024
RECORD_BLOCK_ALLOC_BYTES = 16 * 1024 * 1024
_HEADER = tuple(f.name for f in fields(DecodedRecord) if f.name != "payload")


class _Columns:
    def __init__(self, count):
        self.count = count
        self.parts = {}
        self.widths = {}
        self.bytes = 0

    def Add(self, values, dtype, shape=(), kind="python_int"):
        dtype = np.dtype(dtype)
        width = math.prod(shape) if shape else 1
        size = self.count * width * dtype.itemsize
        offset = self.widths.get(dtype.str, 0)
        if offset + width > 4096 or self.bytes + 2 * size > RECORD_BLOCK_ALLOC_BYTES:
            raise ValueError("artifact_record_block_allocation_limit")
        self.bytes += 2 * size  # temporary columns plus the eventual packed matrix
        array = np.asarray(values, dtype=dtype).reshape(self.count, width)
        self.parts.setdefault(dtype.str, []).append(array)
        self.widths[dtype.str] = offset + width
        return {"kind": kind, "dtype": dtype.str, "offset": offset,
                "width": width, "shape": tuple(shape)}

    def Plan(self, values, depth=0):
        if depth > 64:
            raise ValueError("artifact_structure_limit")
        first = values[0]
        if first is None and all(value is None for value in values):
            return {"kind": "constant", "value": None}
        primitive = type(first) in (str, bool, int, bytes)
        same_float_bits = (type(first) is float and math.isfinite(first)
                           and all(type(value) is float and struct.pack("<d", value) ==
                                   struct.pack("<d", first) for value in values))
        if same_float_bits or primitive and all(type(value) is type(first) and value == first for value in values):
            return {"kind": "constant", "value": first}
        if any(value is None for value in values):
            sample = next((value for value in values if value is not None), None)
            return {"kind": "optional", "present": self.Add(
                [value is not None for value in values], "bool", kind="python_bool"),
                "value": self.Plan([sample if value is None else value for value in values], depth + 1)}
        if all(type(value) is bool for value in values):
            return self.Add(values, "bool", kind="python_bool")
        if all(type(value) is int for value in values):
            lower, upper = min(values), max(values)
            if 0 <= lower and upper < 2**64:
                return self.Add(values, "uint64")
            if -2**63 <= lower and upper < 2**63:
                return self.Add(values, "int64")
        if all(type(value) is float for value in values):
            return self.Add(values, "float64", kind="python_float")
        if isinstance(first, np.generic) and all(type(value) is type(first) for value in values):
            if first.dtype.kind in "biuf":
                return self.Add(values, first.dtype, kind="numpy_scalar")
        if isinstance(first, np.ndarray) and all(isinstance(value, np.ndarray)
                and value.dtype == first.dtype and value.shape == first.shape for value in values):
            if first.dtype.kind in "biuf" and first.ndim <= 3 and first.size:
                return self.Add(values, first.dtype, first.shape, "array")
        if all(type(value) is str for value in values):
            pool = tuple(dict.fromkeys(values))
            indexes = {value: index for index, value in enumerate(pool)}
            return {"kind": "strings", "pool": pool,
                    "codes": self.Add([indexes[value] for value in values], "uint32")}
        if all(type(value) is bytes for value in values):
            length = sum(len(value) for value in values)
            if self.bytes + 2 * length + 8 * (self.count + 1) > RECORD_BLOCK_ALLOC_BYTES:
                raise ValueError("artifact_record_block_allocation_limit")
            self.bytes += 2 * length + 8 * (self.count + 1)
            offsets = np.empty(self.count + 1, dtype=np.uint64)
            offsets[0] = 0
            for index, value in enumerate(values):
                offsets[index + 1] = int(offsets[index]) + len(value)
            return {"kind": "bytes", "offsets": offsets,
                    "data": np.frombuffer(b"".join(values), dtype=np.uint8)}
        if isinstance(first, Mapping) and all(isinstance(value, Mapping)
                and isinstance(value, MappingProxyType) ==
                isinstance(first, MappingProxyType) for value in values):
            if any(tuple(value) != tuple(first) for value in values):
                layouts = tuple(dict.fromkeys(tuple(value) for value in values))
                keys = tuple(dict.fromkeys(key for value in values for key in value))
                if len(keys) > 4096:
                    raise ValueError("artifact_record_block_allocation_limit")
                indexes = {layout: index for index, layout in enumerate(layouts)}
                children = {}
                for key in keys:
                    sample = next(value[key] for value in values if key in value)
                    children[key] = self.Plan([value[key] if key in value else sample for value in values], depth + 1)
                return {"kind": "mapping_layouts", "frozen": isinstance(first, MappingProxyType),
                        "fields": children, "layouts": layouts,
                        "codes": self.Add([indexes[tuple(value)] for value in values], "uint32")}
            return {"kind": "mapping", "frozen": isinstance(first, MappingProxyType),
                    "fields": {key: self.Plan([value[key] for value in values], depth + 1)
                               for key in first}}
        if type(first) in (tuple, list) and all(type(value) is type(first)
                and len(value) == len(first) for value in values):
            if len(first) > 4096:
                raise ValueError("artifact_record_columns_limit")
            return {"kind": "sequence", "tuple": type(first) is tuple,
                    "items": tuple(self.Plan([value[index] for value in values], depth + 1)
                                   for index in range(len(first)))}
        # Unusual heterogeneous decoder data retains its exact generic codec types.
        # The normal cumulative decoder object/node budgets still cover this fallback.
        return {"kind": "values", "items": tuple(values)}


def RecordBlock_Build(records):
    count = len(records)
    if not 0 < count <= RECORD_BLOCK_ROWS or not all(type(record) is DecodedRecord for record in records):
        raise ValueError("artifact_record_block_invalid")
    columns = _Columns(count)
    metadata = {name: columns.Plan([getattr(record, name) for record in records]) for name in _HEADER}
    payload = columns.Plan([record.payload for record in records])
    matrices = {dtype: np.concatenate(parts, axis=1) for dtype, parts in columns.parts.items()}
    return {"count": count, "metadata": metadata, "payload": payload, "matrices": matrices}


class _PayloadRow(Mapping):
    __slots__ = ("_table", "_plan", "_row")

    def __init__(self, table, plan, row):
        self._table, self._plan, self._row = table, plan, row

    def __iter__(self):
        return iter(self._table.Keys_Get(self._plan, self._row))

    def __len__(self):
        return len(self._table.Keys_Get(self._plan, self._row))

    def __getitem__(self, key):
        if self._plan["kind"] == "mapping_layouts" and key not in self._table.Keys_Get(self._plan, self._row):
            raise KeyError(key)
        return self._table.Get(self._plan["fields"][key], self._row)

    def __repr__(self):
        return repr(dict(self))


class _Table:
    def __init__(self, block):
        if (not isinstance(block, dict) or set(block) != {"count", "metadata", "payload", "matrices"}
                or type(block["count"]) is not int or not 0 < block["count"] <= RECORD_BLOCK_ROWS
                or not isinstance(block["metadata"], dict) or set(block["metadata"]) != set(_HEADER)
                or not isinstance(block["matrices"], dict)):
            raise ValueError("artifact_record_block_invalid")
        self.count, self.matrices = block["count"], block["matrices"]
        for dtype, matrix in self.matrices.items():
            if (not isinstance(matrix, np.ndarray) or matrix.dtype.str != dtype
                    or matrix.dtype.kind not in "biuf" or matrix.ndim != 2
                    or matrix.shape[0] != self.count or matrix.shape[1] > 4096
                    or matrix.flags.writeable):
                raise ValueError("artifact_record_matrix_invalid")
        if sum(matrix.nbytes for matrix in self.matrices.values()) > RECORD_BLOCK_ALLOC_BYTES:
            raise ValueError("artifact_record_block_allocation_limit")
        self.metadata, self.payload = block["metadata"], block["payload"]
        for plan in (*self.metadata.values(), self.payload):
            self.Validate(plan)
        if self.payload["kind"] not in ("mapping", "mapping_layouts") or self.payload["frozen"] is not True:
            raise ValueError("artifact_record_payload_invalid")

    def Validate(self, plan, depth=0):
        if not isinstance(plan, dict) or depth > 64:
            raise ValueError("artifact_record_plan_invalid")
        kind = plan.get("kind")
        if kind in ("python_int", "python_float", "python_bool", "numpy_scalar", "array"):
            if set(plan) != {"kind", "dtype", "offset", "width", "shape"}:
                raise ValueError("artifact_record_plan_invalid")
            matrix = self.matrices.get(plan["dtype"])
            offset, width, shape = plan["offset"], plan["width"], plan["shape"]
            if (matrix is None or type(offset) is not int or type(width) is not int
                    or not isinstance(shape, tuple) or len(shape) > 3
                    or any(type(n) is not int or not 0 <= n <= 4096 for n in shape)
                    or not 0 < width <= 4096 or not 0 <= offset <= matrix.shape[1] - width
                    or width != (math.prod(shape) if shape else 1)
                    or (kind != "array" and (shape or width != 1))
                    or kind == "python_int" and matrix.dtype.kind not in "iu"
                    or kind == "python_float" and matrix.dtype.kind != "f"
                    or kind == "python_bool" and matrix.dtype.kind != "b"):
                raise ValueError("artifact_record_column_invalid")
        elif kind == "constant":
            if set(plan) != {"kind", "value"} or type(plan["value"]) not in (type(None), str, bool, int, float, bytes):
                raise ValueError("artifact_record_constant_invalid")
        elif kind == "values":
            if set(plan) != {"kind", "items"} or not isinstance(plan["items"], tuple) or len(plan["items"]) != self.count:
                raise ValueError("artifact_record_values_invalid")
        elif kind in ("mapping", "mapping_layouts"):
            expected = {"kind", "frozen", "fields"} | ({"layouts", "codes"} if kind == "mapping_layouts" else set())
            if (set(plan) != expected or type(plan["frozen"]) is not bool
                    or not isinstance(plan["fields"], dict) or len(plan["fields"]) > 4096
                    or any(type(key) not in (str, int) for key in plan["fields"])):
                raise ValueError("artifact_record_mapping_invalid")
            for child in plan["fields"].values():
                self.Validate(child, depth + 1)
            if kind == "mapping_layouts":
                layouts = plan["layouts"]
                if (not isinstance(layouts, tuple) or not 0 < len(layouts) <= self.count
                        or any(not isinstance(layout, tuple) or any(type(key) not in (str, int) for key in layout)
                               or len(layout) != len(set(layout))
                               or any(key not in plan["fields"] for key in layout) for layout in layouts)):
                    raise ValueError("artifact_record_mapping_layout_invalid")
                self.Validate(plan["codes"], depth + 1)
                if plan["codes"]["kind"] != "python_int":
                    raise ValueError("artifact_record_mapping_layout_invalid")
                for row in range(self.count):
                    if not 0 <= self.Get(plan["codes"], row) < len(layouts):
                        raise ValueError("artifact_record_mapping_layout_invalid")
        elif kind == "sequence":
            if (set(plan) != {"kind", "tuple", "items"} or type(plan["tuple"]) is not bool
                    or not isinstance(plan["items"], tuple) or len(plan["items"]) > 4096):
                raise ValueError("artifact_record_sequence_invalid")
            for child in plan["items"]:
                self.Validate(child, depth + 1)
        elif kind == "optional":
            if set(plan) != {"kind", "present", "value"}:
                raise ValueError("artifact_record_optional_invalid")
            self.Validate(plan["present"], depth + 1)
            self.Validate(plan["value"], depth + 1)
            if plan["present"]["kind"] != "python_bool":
                raise ValueError("artifact_record_optional_invalid")
        elif kind == "strings":
            if (set(plan) != {"kind", "pool", "codes"} or not isinstance(plan["pool"], tuple)
                    or not 0 < len(plan["pool"]) <= self.count
                    or not all(type(value) is str for value in plan["pool"])):
                raise ValueError("artifact_record_strings_invalid")
            self.Validate(plan["codes"], depth + 1)
            if plan["codes"]["kind"] != "python_int":
                raise ValueError("artifact_record_strings_invalid")
            for row in range(self.count):
                if not 0 <= self.Get(plan["codes"], row) < len(plan["pool"]):
                    raise ValueError("artifact_record_strings_invalid")
        elif kind == "bytes":
            offsets, data = plan.get("offsets"), plan.get("data")
            if (set(plan) != {"kind", "offsets", "data"} or not isinstance(offsets, np.ndarray)
                    or offsets.dtype != np.dtype("uint64") or offsets.shape != (self.count + 1,)
                    or not isinstance(data, np.ndarray) or data.dtype != np.dtype("uint8") or data.ndim != 1
                    or offsets[0] != 0 or offsets[-1] != data.size
                    or np.any(offsets[1:] < offsets[:-1])
                    or offsets.nbytes + data.nbytes > RECORD_BLOCK_ALLOC_BYTES):
                raise ValueError("artifact_record_bytes_invalid")
        else:
            raise ValueError("artifact_record_plan_invalid")

    def Get(self, plan, row):
        kind = plan["kind"]
        if kind in ("python_int", "python_float", "python_bool", "numpy_scalar", "array"):
            matrix = self.matrices[plan["dtype"]]
            if kind == "array":
                return matrix[row, plan["offset"]:plan["offset"] + plan["width"]].reshape(plan["shape"])
            value = matrix[row, plan["offset"]]
            return value if kind == "numpy_scalar" else value.item()
        if kind == "constant":
            return plan["value"]
        if kind == "values":
            return plan["items"][row]
        if kind in ("mapping", "mapping_layouts"):
            view = _PayloadRow(self, plan, row)
            return MappingProxyType(view) if plan["frozen"] else dict(view)
        if kind == "sequence":
            values = [self.Get(child, row) for child in plan["items"]]
            return tuple(values) if plan["tuple"] else values
        if kind == "optional":
            return self.Get(plan["value"], row) if self.Get(plan["present"], row) else None
        if kind == "strings":
            return plan["pool"][self.Get(plan["codes"], row)]
        if kind == "bytes":
            start, end = int(plan["offsets"][row]), int(plan["offsets"][row + 1])
            return plan["data"][start:end].tobytes()
        raise ValueError("artifact_record_plan_invalid")

    def Keys_Get(self, plan, row):
        if plan["kind"] == "mapping_layouts":
            return plan["layouts"][self.Get(plan["codes"], row)]
        return plan["fields"].keys()


def RecordBlock_Read(block, charge, context, *, retain=True, file_size=None):
    table = _Table(block)
    # Count every retained row, immutable payload view/proxy, row index and new
    # metadata scalar against the SAME cumulative decoder budgets. Column payload
    # scalars are materialized only on access; their numeric buffers are already
    # charged by the ordinary array reader. Constants/fallback values are shared.
    variable = sum(plan["kind"] in ("python_int", "python_float", "python_bool", "numpy_scalar")
                   for plan in table.metadata.values())
    row_bytes = (sys.getsizeof(DecodedRecord.__new__(DecodedRecord))
                 + sys.getsizeof(_PayloadRow(table, table.payload, 0))
                 + sys.getsizeof(MappingProxyType({})) + sys.getsizeof(0)
                 + variable * sys.getsizeof(2**64 - 1) + 8)
    charge(table.count * (4 + variable) + 1, table.count * row_bytes + sys.getsizeof(table))
    records = []
    for row in range(table.count):
        if row % 256 == 0:
            context.Cancel_RaiseIfRequested()
        metadata = {name: table.Get(plan, row) for name, plan in table.metadata.items()}
        if (any(type(metadata[name]) is not int for name in _HEADER if name != "record_name")
                or type(metadata["record_name"]) is not str):
            raise ValueError("artifact_record_metadata_invalid")
        if (not 0 <= metadata["timestamp_us"] < 2**64
                or not 0 <= metadata["record_sequence"] < 2**32
                or file_size is not None and (not 0 <= metadata["file_offset"] < file_size
                    or not 0 <= metadata["payload_length"] <= file_size - metadata["file_offset"])):
            raise ValueError("parse_cache_record_bounds_invalid")
        record = DecodedRecord(**metadata, payload={})
        # Construction boundary: install the validated immutable view before any
        # record is published, avoiding DecodedRecord's eager dict(payload) copy.
        object.__setattr__(record, "payload", MappingProxyType(_PayloadRow(table, table.payload, row)))
        if retain:
            records.append(record)
    return records if retain else table.count
