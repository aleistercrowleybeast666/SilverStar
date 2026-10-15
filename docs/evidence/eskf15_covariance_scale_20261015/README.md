# ESKF15 covariance congruence API evidence — 2026-10-15

This additive API computes every entry of P' = D P D-transpose and commits only
after original/candidate symmetry, finite-value, SPD and variance-cap checks.
The nominal state, time and identities remain unchanged. Every non-APPLIED
result preserves the complete state bytes. This is a bounded utility, not an
enabled GNSS recovery policy or a pure performance optimization.

The preserved baseline shows eight repeated NIS rejections with unchanged
state/P. A missing new API was not counted as a pre-fix defect. Independent
float64 dense-matrix products, all 225 entries, correlations, cap boundaries,
aliases, NaN/Inf, asymmetric/indefinite/singular input and candidate faults are
covered at real GCC O0 and O2: 196 tests passed. The task-end rerun also passed
196 tests. Existing predict/update/replay differential traces are unchanged.
Real GCC -fanalyzer object compilation and Cortex-M4F object compilation passed;
their exact commands, versions, sources, artifacts and outputs are in the ZIP.
The source hashes were checked against both prior compilation receipts before
sealing. Current generated firmware/analyzer validation is separately retained
in algorithm_memory_closeout_20261015 and the algorithm closeout task directory.

Selective scaling preserves SPD and correlation in exact arithmetic; it does
not generally prove P'-P positive semidefinite. Only uniform scaling gives that
order guarantee. No cap clamping, diagonal-only replacement, NIS bypass, new
origin, model-mismatch recovery or firmware recovery default is introduced.

The exact source snapshot and complete retained failures/results are hashed in
manifest.json. Tool PASS is limited to the stated scope. Critical-contract
manual acceptance, whole-program call graph, MSP/ISR stack, MCU timing and
flight/hardware qualification remain NOT PROVEN. No hardware was accessed.
