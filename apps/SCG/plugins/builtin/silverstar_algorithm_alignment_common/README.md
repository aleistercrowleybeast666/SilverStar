# Alignment Common

Declarative SilverStar_FCCG builtin algorithm plugin.

The original reference baseline was main at
cc0b377ded690556d037a412a55f87fe334c42d0. SilverStar owns and extends this
payload; the manifest declares sources for fresh generated firmware.

## Weighted direction alignment (0.1.3)

VectorConstraints_Solve retains its API, result enum, 2--6 constraint bound,
and scalar-first q_nb = [w,x,y,z]. It maps body column vectors into the
navigation frame: v_n ~= C_nb v_b. The caller's ENU/body-axis conventions,
gravity sign, magnetic horizontal projection and azimuth definitions are
unchanged. It does not add Earth-rate alignment or alter sensor capabilities.

The user supplied pages 241--242 of *Strapdown Inertial Navigation Algorithms
and Integrated Navigation Principles* (Chinese title:
《捷联惯导算法与组合导航原理》), equations 8.1.8--8.1.16, use reference frame r:
A = sum(w_i v_i^r (v_i^b)^T), A = U D V^T,
C_b^r = U diag(1,1,det(U V^T)) V^T.
The parent task visually checked both original JPEGs and supplied the verified
transcription on 2026-10-17. This local task did not view the JPEGs: Windows
Library materialization failed at extended-attribute persistence.

The existing API supplies direction constraints, including a unit gravity
direction and horizontal reference/magnetic directions. Each body and reference
vector is therefore still independently normalized. The solved objective is

    min over C in SO(3): 0.5 * sum(w_i * ||unit(v_n_i) - C unit(v_b_i)||^2).

This is the page's SVD solution applied to the existing direction API, not its
raw-magnitude objective. Weights still mean per-direction confidence; no hidden
vector-length or pairwise sine/product weighting remains. A common positive
weight scale has no effect; weights are scaled by their maximum, then their sum.
No pairwise TRIAD candidates, quaternion averaging or outer attitude iteration
remain in this solver. The external-quaternion temporal averaging code is a
separate component and is unchanged.

## Bounds and ordinary failures

- Inputs: finite vectors with finite Euclidean norm >= 1e-6, and finite weights
  0 < w <= 1e6. As before, overflowing squared input norms are invalid.
- Geometry: retain the existing sin(10 degrees) = 0.17364818 threshold in BOTH
  frames. At least one eligible pair is required; diagnostics count eligible
  pairs (at most 15) and report their minimum sine. This is a conservative
  project acceptance policy, not a threshold specified by the book.
- A is built from unit directions and weights summing to one. If its largest
  absolute entry is below 1e-6, reject cancellation-dominated data. Otherwise
  scale A by that entry to bound its elements by one.
- A fixed 3x3 one-sided Jacobi SVD uses at most 16 sweeps and three column
  rotations per sweep. A whole unchanged sweep must confirm correlation
  <= 1e-6 relative to column norms; columns of squared norm <= 1e-14 may be
  ignored as numerical zero. Failure to converge returns Degenerate.
- Sort singular values descending with both sets of singular vectors. Require
  sigma_2 > 1e-5 sigma_1. For negative det(U V^T), require
  sigma_2 - sigma_3 > 1e-5 sigma_1; otherwise return Inconsistent because the
  optimum is ambiguous or too poorly separated at float precision.
- Completing the first two left and right singular directions with cross
  products implements the determinant correction in the minimum singular
  direction, including rank two. Check their orthogonality before removing
  roundoff; then check C C^T and det(C)=+1 with 2e-5 tolerance.
- Preserve the weighted angular RMS > 0.35 rad rejection rule. This is a
  post-fit acceptance gate; the optimized objective uses chordal distances.
  There is no new outlier rejection. A low-weight vector can have a large
  individual angular error while the weighted RMS passes; max_mismatch_rad
  remains available to the caller.

All ordinary failures zero a non-null output; no candidate is published until
all checks succeed. Public null/count/value errors return InvalidArgument.
Internal impossible index/count/nonfinite-work-state violations use the
existing assertion fail-stop contract. Production has no new conditional
compilation, callback, allocator, recursive call, or mutable file-scope state.

The work arrays are fixed: six VectorConstraint objects (168 bytes), one SVD
workspace (84 bytes), one solution (32 bytes on this ABI), and a 3x3 matrix
(36 bytes), plus bounded scalar/helper frames. These object sizes are not a
whole-task stack proof. Target stack includes compiler frames, math-library
calls, scheduler/ISR context, and other callers.

## Reproducible verification

apps/SCG/tests/host_alignment/test_vector_constraints.c covers analytic weighted
noise, counts 2--6, exact and near-180-degree rotations, weight/magnitude scaling,
reflection correction and ambiguity, collinearity/near-collinearity, zero and
nonfinite inputs, numerical rank, unchanged inputs, failure output, determinant
and orthogonality. The Python entry test_round4_vector_constraints.py builds and
runs it, performs real GCC -fanalyzer compilation and Cortex-M4 ARM object
compilation, and injects a one-sweep budget into a disposable Host copy to verify
nonconvergence rejection. No injected source is shipped to target firmware.

Task evidence lives in .work/0.1.3-initial-alignment-20261017 with commands,
source hashes, failures and final receipts. Fresh generated firmware gates
remain authoritative for their recorded scopes. The SVD implementation is
bounded, but MCU execution time, whole-program stack margin and hardware/flight
qualification remain unproven without their separate evidence. A text gate PASS
does not complete the project's critical-contract review or establish original
Power of Ten compliance.