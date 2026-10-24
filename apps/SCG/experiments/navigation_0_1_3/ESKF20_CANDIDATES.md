# ESKF20 state ledger — selected physical model implemented as a host experiment

The isolated implementation is `eskf20_reference.py`, with the complete frozen
contract and source qualifications in [ESKF20_MODEL.md](ESKF20_MODEL.md).
No plugin, public ID assignment or production state/P layout is created.
The [book-gamma definition audit](GAMMA_BOOK_AUDIT_20261018.md) distinguishes the
book's small total installation misalignment from the filter's residual around
its nominal matrix. IMU-to-vehicle orientation remains the user's mechanical
installation convention; it is not another online state.
The authoritative existing 15 error coordinates remain `[dp₃,dv₃,dtheta₃,dbg₃,dba₃]`.
The nominal quaternion's fourth element is not another error degree of freedom.

## User selection relayed by the parent task on 2026-10-17

The additional quantities are **magnetometer-to-IMU installation deviation (3),
magnetic inclination (1), and magnetic declination (1)**, in that appended order.
This supersedes the open choice among the historical investigation items below.
The parent supplied verified author-book sections and conventions on 2026-10-17
and authorized the isolated float64 reference. The user's two images concern
coarse alignment in another edition and are not this model's magnetic evidence.

The linked contract resolves frames, signs, injection/reset, exact magnetic-angle
derivatives, constant additional-state dynamics, explicit input priors and full
20x20 covariance. All initial values remain explicit caller inputs. Still NOT
PROVEN: actual motion/sensor identifiability, calibration provenance needed for a
future production input, real initialization/priors, disturbance robustness,
firmware implementation and hardware validation. Existing calibrated body-frame
magnetic data cannot simply be connected because installation may already be
applied. No production selector, decoder or firmware path is enabled.

## Earlier investigation alternatives (historical, not selected)

| Candidate investigation | Possible coordinates; not selected | Required decision/evidence |
| --- | --- | --- |
| Barometer offset/environment | One height-equivalent offset is one possible model; units/reference pending | Height or pressure model? Independent height reference, temperature evidence, observability against vertical position and accelerometer bias |
| Antenna lever-arm error | Up to three body-frame metre coordinates | Actual installation geometry, rotation excitation, fixed calibration versus online estimation |
| Sensor clock offset/drift | Offset in seconds; drift is a separate coordinate | Which clock/sensor, PPS/sample/receive evidence, model and separation from transport delay |
| Magnetic field/bias/scale | Dimension depends on heading versus vector model and chosen calibration quantities | Raw calibrated vector, installation/reference field, disturbance model, identifiability |

The table records the earlier investigation, not the current selected combination.
No defaults, guessed priors or arbitrary padding are supplied. Each selected state
must record physical quantity, units, frame, nominal
representation, error freedom, continuous/discrete dynamics, driving noise,
initialization/prior, measurement sensitivity, injection/reset, cross covariance,
missing-input/recovery rules and actual observability evidence. Name the final
filter by its real error dimension after those decisions.

Existing planning authority:
[minimal interface plan](../../../../docs/public/SCG/NAVIGATION_MODEL_INTERFACE_PLAN_20261015.md)
and [future models](../../../../docs/public/SCG/FUTURE_NAVIGATION_MODELS_20261015.md).
The adjacent nine-dimensional InEKF remains a separate bias-free invariant model.
