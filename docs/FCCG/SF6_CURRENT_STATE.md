# SF6 current-state revision 2

SF6 plugin 0.2.0 and SF6_STATE.algorithm_revision 2 identify a different
fusion algorithm from the historical revision 1. Revision 2 retains INS
attitude propagation and ENU velocity/position prediction. An admitted
measurement applies `state += gain * (observation - state)` to the latest
prediction state, with six independent gains in vE, vN, vU, pE, pN, pU order.
GNSS horizontal/vertical position, horizontal/vertical velocity and barometer
relative altitude remain separate groups. Both altitude sources use pU gain.
Position updates do not inject velocity corrections.

The core stores one current sample and per-group timestamp/sequence admission
state. It has no prediction history, event queue, rewind or replay. Prediction
and update publish local candidates only after finite arithmetic succeeds.
Invalid external observations return ordinary errors; corrupt stored
invariants use the existing assertion fail-stop. The owning EstimatorTask
remains the sole writer. Iterations are bounded by six axes or five groups.

Trusted MCU sample epochs remain authoritative for age and source ordering.
Receive-only sources use their receive epoch. Future, pre-initialization,
older-than-500ms, duplicate and reordered per-group inputs are rejected.
Sequence wrap follows the existing half-range rule. Backend physical quality,
source identity and valid-group masks remain in effect. The successful
measurement boundary recorded in revision 2 is the current evaluation epoch.

No latency compensation occurs. During motion a delayed observation pulls the
current state toward an earlier physical state. For approximately constant
velocity or acceleration, the additional single-update correction error is
approximately `gain * velocity * delay` for position, or
`gain * acceleration * delay` for velocity, respectively. This is a modeling
estimate, not a flight accuracy measurement. Arrival order is intentional;
revision 1's measurement-time sorting is no longer claimed.

Only the six gains are exposed as SF6 parameters. The three revision-1 fixed
delay parameters have been removed from its manifest and UI. Existing saved
SF6 configurations containing those fields fail validation until the user
explicitly removes them. Generic KF6/ESKF delay configuration remains owned
by those algorithms and does not affect SF6 revision 2.

The selected plugin supplies declarative decoder semantics identifying
revision 2. New profile identities differ from revision 1. FLP keeps the
legacy filter and dispatches recorded/What-if replay by the exact decoder's
revision, component version and state-record revision; conflicts and unknown
revisions are rejected. Explicit Offline mode selects revision 2 and labels
the semantic change when attached to a historical dataset. Historical logs
and exact decoder packages are immutable.

The stationary valid-measurement test demonstrates convergence and a finite
dropout/recovery case with bounded inputs. Finite checks prevent publishing
NaN/infinity; they do not prove that every physical trajectory remains close
to truth. Missing observations permit inertial drift, gain zero disables
that axis's correction, and plausible but incorrect measurements can bias
the solution. The initial gains of 0.2 are engineering defaults.

At the preserved F407 field configuration and Release -O2, context allocation
shrinks from 18,592 to 192 bytes, freeing exactly 18,400 SRAM bytes. With TF,
AIR and Ground configuration preserved and maintenance disabled, the measured
F407 ELF uses 242,488 Flash bytes, 79,208 SRAM bytes and 33,496 CCM bytes
(112,704 total RAM bytes). These figures include linked static task stacks;
stack worst-known call-chain estimates are separate and must not be added
again. The same 192-byte context ABI is confirmed by Cortex-M3 soft-float
compilation; complete F103 fit, execution time and hardware behavior remain
unmeasured. The present SDIO/FatFs plugin requires F407, so an unchanged full
F103 Flight configuration is not currently supported.
