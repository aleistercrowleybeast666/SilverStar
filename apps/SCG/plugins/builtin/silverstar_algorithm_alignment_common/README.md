# Alignment Common

Declarative SilverStar_FCCG builtin `algorithm` plugin.

The original reference baseline was `main` at
`cc0b377ded690556d037a412a55f87fe334c42d0`. SilverStar now owns and
extends this payload. The plugin manifest declares sources for generated
firmware; FCCG does not execute the payload on the host.

## Round 4 vector constraints solver

`VectorConstraints_Solve` accepts two to six normalized body/navigation
direction pairs with positive user weights. Exactly two valid, noncollinear
directions use TRIAD. With more directions, every noncollinear pair supplies
a TRIAD candidate; its weight is the user-weight product multiplied by the
squared sine of both body and navigation separation angles. A bounded
quaternion-dyad eigen iteration computes a sign-invariant rotation mean on
SO(3), rather than averaging quaternion components. The solver reports valid
pair count, minimum pair sine, RMS and maximum angular mismatch. Near
collinearity and inconsistent vectors are rejected.

This is a software-validated numerical core. Project schema, source capture,
strategy binding and the Navigation Configuration page still need to select
and feed it before it becomes a user-facing alignment method.

The existing external-quaternion window now accumulates a 4×4 quaternion
dyad and extracts its dominant eigenvector with a fixed 24-step iteration.
This gives a sign-invariant rotation average for JY901B samples. The current
six-axis path still needs a separately configured authoritative yaw source.
