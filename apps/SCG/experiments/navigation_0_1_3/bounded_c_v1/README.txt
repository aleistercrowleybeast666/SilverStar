Bounded C navigation candidate v1, 2026-10-22.
Real ESKF20 / invariant InEKF15 / invariant InEKF20 mathematical kernels, double precision.
This directory is not a registered production estimator or SystemNavigationBackend.
See navigation_session.h for the equal-half IMU, integer clock and canonical noise contract.
Co-timed observations only. Delayed observations are explicitly rejected. No hot dimension switch.
Allocate session and exclusive workspace statically; no work object on task stack.
Basic offline tests and ARM compilation/link evidence do not qualify WCET, fp32, whole stack or hardware.
Auditable source/build/review/evidence retained at:
C:\Users\chdxm\Documents\Codex\2026-10-22\task-9\silverstar_nav_boundary_v2
c_models: O0/O2 each 41 groups (33 independent and 8 prototype parity).
core_review/post_fix: independent Schur/Pdot and repaired-domain/alias checks.
c_session/verification_v2: 36 pair/admission/parity checks on byte-identical source.
c_session/arm_link_nano_v2: zero-warning link-only artifact; no board startup/HAL/RTOS.
MAGNETIC_CONTRACT.txt and C_LINK_SCOPE.txt explain provenance and remaining integration work.

Integration addendum: the registered owner is now silverstar_algorithm_augmented_common.
Three estimator manifests select this common backend with separate model IDs.
This experiments directory remains a reference copy. See the owner payload for runtime wiring.
The fixed-support sparse-flow and strict enum changes are included after independent checks.
Only software-validation builds are currently permitted; target timing remains unqualified.
H7 preparation is paused. No hardware was operated.
