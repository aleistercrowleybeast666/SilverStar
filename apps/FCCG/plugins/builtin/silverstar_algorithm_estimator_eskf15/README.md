# ESKF15

Selected-only right-local ENU algorithm, revision 1, with quality policy revision 3.
The authoritative human and machine contracts are `docs/NAVIGATION_CONTRACT.md` and
`docs/contracts/navigation_v1.json` at the FCCG repository root.

`navigation_eskf.c` owns the 15D error-state mathematics, Joseph update and SO(3) covariance
reset. `navigation_eskf_replay.c` owns bounded delayed body-input replay.
`navigation_eskf_backend.c` implements Core's public `system_navigation_backend.h`, applies
actual generated parameters, GNSS/Baro admission, quality supervision and optional logging.

Nominal state is `[p(3),v(3),q_wxyz(4),bg(3),ba(3)]`, with error `[dp,dv,dtheta,dbg,dba]`.
The quaternion maps body to ENU and correction multiplies on the right. Inputs are two
calibrated body half means in rad/s and m/s², carrying actual interval, source and correction
generation. State, covariance and working buffers belong to the caller; no dynamic allocation
or private KF6 header is used. Public results distinguish invalid data, numerical failure,
model mismatch, NIS rejection and soft weighting.

The manifest is the parameter authority. Missing generated symbols fail compilation; the
header does not supply a second fallback default set. The decoder records all resolved
parameters. Required ESKF logging has its own initial state/full P, body-input and operation
records; periodic full P is an optional four-part snapshot. Logging-disabled builds retain
the same computation through an internal measurement context independent of SSLOG structs.

Generate a fresh project to obtain changed project-owned source; normal Apply preserves it.
Software gates and hardware maturity are recorded in root `VALIDATION.md`; plugin availability
does not imply hardware validation. GNSS lever arm and measurement delays are configured
experimental inputs requiring separate bench validation for the selected physical installation.
