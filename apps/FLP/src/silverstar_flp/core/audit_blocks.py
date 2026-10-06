"""Bounded columnar audit rows, retaining sequence types and exact typed values.

The retained dictionaries are read-only views. Nested returned values are bounded
temporary materializations, not a second retained audit copy. This is a data-only
storage facility; it does not infer or alter diagnostic/business semantics.
"""
from collections.abc import Mapping
import sys
from types import MappingProxyType

import numpy as np

from silverstar_flp.core.record_blocks import (
    _Columns, _Table, RECORD_BLOCK_ROWS, RECORD_BLOCK_ALLOC_BYTES,
)

AUDIT_BLOCK_MIN_ROWS = 256
MAX_AUDIT_ROW_OBJECTS = 4096
MAX_AUDIT_ROW_BYTES = 1024 * 1024


class _AuditColumns(_Columns):
    def Plan(self, values, depth=0):
        if any(isinstance(value, Mapping) and any(type(key) not in (str, int) for key in value)
               for value in values):
            return {"kind": "values", "items": tuple(values)}
        return super().Plan(values, depth)


def AuditBlock_Build(rows):
    if (not 0 < len(rows) <= RECORD_BLOCK_ROWS
            or not all(isinstance(row, Mapping) for row in rows)):
        raise ValueError("artifact_audit_rows_invalid")
    columns = _AuditColumns(len(rows))
    plan = columns.Plan(rows)
    if plan["kind"] not in ("mapping", "mapping_layouts"):
        raise ValueError("artifact_audit_layout_unsupported")
    matrices = {dtype: np.concatenate(parts, axis=1) for dtype, parts in columns.parts.items()}
    return {"count": len(rows), "payload": plan, "matrices": matrices}


class _AuditRow(dict):
    """Dictionary read interface, with explicit rejection of mutation of saved audit data."""
    __slots__ = ("_table", "_row")

    def __init__(self, table, row):
        self._table, self._row = table, row
        # CPython's JSON encoder checks native dict emptiness before invoking the
        # overridden items() interface. Keep real key slots (shared keys/None),
        # rather than an empty hidden dict that would silently serialize as {}.
        for key in table.Keys_Get(table.payload, row):
            dict.__setitem__(self, key, None)

    def __iter__(self):
        return iter(self._table.Keys_Get(self._table.payload, self._row))

    def __len__(self):
        return len(self._table.Keys_Get(self._table.payload, self._row))

    def __contains__(self, key):
        return key in self._table.Keys_Get(self._table.payload, self._row)

    def __getitem__(self, key):
        if key not in self:
            raise KeyError(key)
        return self._table.Get(self._table.payload["fields"][key], self._row)

    def get(self, key, default=None):
        return self[key] if key in self else default

    def keys(self):
        return Mapping.keys(self)

    def items(self):
        return Mapping.items(self)

    def values(self):
        return Mapping.values(self)

    def copy(self):
        return dict(self.items())

    def __repr__(self):
        return repr(self.copy())

    def __eq__(self, other):
        return self.copy() == other

    def __ne__(self, other):
        return not self == other

    def __or__(self, other):
        return self.copy() | other

    def __ror__(self, other):
        return other | self.copy()

    def _Mutation_Reject(self, *args, **kwargs):
        raise TypeError("saved_audit_row_read_only")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _Mutation_Reject


class _AuditTable(_Table):
    def __init__(self, block):
        if (not isinstance(block, dict) or set(block) != {"count", "payload", "matrices"}
                or type(block["count"]) is not int or not 0 < block["count"] <= RECORD_BLOCK_ROWS
                or not isinstance(block["matrices"], dict)):
            raise ValueError("artifact_audit_block_invalid")
        self.count, self.matrices, self.payload = block["count"], block["matrices"], block["payload"]
        for dtype, matrix in self.matrices.items():
            if (not isinstance(matrix, np.ndarray) or matrix.dtype.str != dtype
                    or matrix.dtype.kind not in "biuf" or matrix.ndim != 2
                    or matrix.shape[0] != self.count or matrix.shape[1] > 4096
                    or matrix.flags.writeable):
                raise ValueError("artifact_audit_matrix_invalid")
        if sum(matrix.nbytes for matrix in self.matrices.values()) > RECORD_BLOCK_ALLOC_BYTES:
            raise ValueError("artifact_record_block_allocation_limit")
        self.Validate(self.payload)
        if self.payload["kind"] not in ("mapping", "mapping_layouts"):
            raise ValueError("artifact_audit_layout_unsupported")
        objects, size = self._RowBudget_Get(self.payload)
        if objects > MAX_AUDIT_ROW_OBJECTS or size > MAX_AUDIT_ROW_BYTES:
            raise ValueError("artifact_audit_row_allocation_limit")
        self.row_objects, self.row_bytes = objects, size

    def _RowBudget_Get(self, plan):
        # Worst-case bounded temporary Get() expansion, including container slots,
        # scalar objects and array views. Actual matrices/fallbacks are separately
        # admitted by the cumulative ordinary decoder budgets.
        kind = plan["kind"]
        if kind in ("mapping", "mapping_layouts"):
            children = tuple(self._RowBudget_Get(child) for child in plan["fields"].values())
            return (1 + sum(n for n, _ in children),
                    sys.getsizeof({}) + 64 * len(children) + sum(b for _, b in children))
        if kind == "sequence":
            children = tuple(self._RowBudget_Get(child) for child in plan["items"])
            return (1 + sum(n for n, _ in children),
                    sys.getsizeof([]) + 8 * len(children) + sum(b for _, b in children))
        if kind == "optional":
            return self._RowBudget_Get(plan["value"])
        if kind == "array":
            return 1, 256  # read-only view, its numerical buffer is already retained/charged
        if kind == "bytes":
            lengths = plan["offsets"][1:] - plan["offsets"][:-1]
            return 1, sys.getsizeof(b'') + int(lengths.max(initial=0))
        if kind in ("constant", "strings", "values"):
            return 0, 0  # shared objects already admitted by Decode()
        return 1, max(sys.getsizeof(2**64 - 1), sys.getsizeof(np.float64(0)))


def AuditBlock_Read(block, charge, context, *, retain=True):
    table = _AuditTable(block)
    frozen = table.payload["frozen"]
    # Charge the largest possible native key table, including changing layouts.
    key_table_bytes = sys.getsizeof(dict.fromkeys(table.payload["fields"])) - sys.getsizeof({})
    row_size = sys.getsizeof(_AuditRow.__new__(_AuditRow)) + key_table_bytes + sys.getsizeof(0) + 8
    if frozen:
        row_size += sys.getsizeof(MappingProxyType({}))
    # Charge retained row views/indices/sequence slots AND one complete worst-case
    # access materialization for this table, even in streaming verifier mode.
    charge(table.count * (2 + int(frozen)) + 2 + table.row_objects,
           table.count * row_size + sys.getsizeof(table) + table.row_bytes)
    if not retain:
        return table.count
    rows = []
    for row in range(table.count):
        if row % 256 == 0:
            context.Cancel_RaiseIfRequested()
        view = _AuditRow(table, row)
        rows.append(MappingProxyType(view) if frozen else view)
    return rows
