# Ryu source provenance

Upstream: https://github.com/ulfjack/ryu/tree/4c0618b0e44f7ef027ebae05d2cc7812048f7c8f

Both upstream licenses are retained. `ryu_provenance.json` in this task's evidence
records each downloaded file's original SHA256. No upstream file is hidden from
the source inventory. The target links only the buffered, allocation-free path;
the unused allocating convenience function is not linked.

Local warning/contract changes, without suppressing diagnostics:

- `d2s.c`: cast the known nonnegative character index to uint32 before mixed
  index arithmetic; cast a maximum 18-character increment to int explicitly.
  Preserve the upstream allocating convenience function in the inventory and
  return NULL when its allocation fails. The real analyzer found its unchecked
  malloc result even though the target link discards that entire function.
- `d2s_intrinsics.h`: assert the valid double conversion shift interval before
  converting `j-64` to uint32 in the two portable/intrinsic branches. Existing
  assertions stay enabled. The host validation forces `RYU_ONLY_64_BIT_OPS` to
  exercise the same portable arithmetic used by Cortex-M4.

Ryu has value-bounded digit-removal loops and one unused allocation convenience
API; it is third-party code, not first-party Power-of-Ten compliance evidence.
The complete linked call graph and actual frames are reported separately.
Production integration must bind the established SilverStar terminal assertion
facility; the isolated ELF's terminal harness is never an MCU recovery path.
