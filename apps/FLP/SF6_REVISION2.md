# SF6 current-state replay compatibility

SF6 firmware component `silverstar.algorithm.estimator.sf6` version `0.2.0`
declares `metadata_declarations.sf6.revision = 2` in its exact decoder and logs
`SF6_STATE.algorithm_revision = 2`. Revision 2 applies each admitted group to
the current predicted state using its corresponding fixed gain. It keeps INS
prediction and independent group masks, finite-value checks, epoch and maximum
500 ms source-age checks, strictly increasing per-group source and receive
epochs, and modulo-uint32 sequence ordering. Failed updates publish neither
state nor sequence changes. Successful update boundaries equal the latest
prediction timestamp. There is no history, event queue or backward replay.

Trusted MCU sample timestamps are used for age and ordering only; otherwise
the source epoch is the receive time. Revision 2 has six gain parameters and
shared INS gravity. The three fixed-lag delay knobs are absent and any supplied
delay parameter is rejected, including zero. Old saved FCCG parameter keys
must be explicitly removed by the user before regeneration.

Revision 1 retains the original `Sf6Filter` and legacy plugin, including its
256-boundary / 600 ms history, 256-event capacity, and delay defaults. Historical
recorded-configuration and What-if replay select it from exact decoder revision
and component-version evidence. Audited early profiles lacking a revision are
accepted as revision 1 only when their complete legacy gain/delay contract
identifies that implementation. Unknown versions/revisions, missing identities,
mixed logged revisions and decoder/log revision mismatches are rejected.
`LogOpenCoordinator` validates the identity before publishing a production
dataset; neither the container nor Descriptor matching rules are relaxed.

Offline mode explicitly selects revision 2, including on a historical dataset,
and records a warning and both dataset and algorithm revisions. Existing
revision 1 recorded/What-if saved configurations retain their original version
and schema identity. A saved configuration whose version disagrees with the
selected dataset/mode is rejected rather than reinterpreted. The GUI changes
the parameter form when revision/mode changes; new forms expose no delay knobs.

Delayed measurements are not transported forward. Under approximately constant
velocity, an old position observation has an age-dependent displacement of
roughly velocity times delay; a gain-weighted correction can therefore pull the
current position backward. Velocity observations during acceleration have the
analogous acceleration-times-delay effect. This is a modeling limitation, not a
timing measurement or flight-accuracy guarantee. Both revisions remain
`APPROXIMATE`: host replay does not reproduce complete backend queue scheduling.
No covariance, confidence, NIS or historical replay statistics are fabricated
for revision 2.

Tests retain a frozen revision 1 C oracle from source commit `cc424443` under
`tests/fixtures/sf6_revision1` with SHA-256 provenance. Revision 2 numerical
tests compile the current owning FCCG C payload with strict warnings and
float32 operation ordering, compare state/results/boundaries, and exercise
age/epoch, duplicate/order/wrap, overflow and transactional failure behavior.
Synthetic logs and host numerical parity are not hardware or flight evidence.
