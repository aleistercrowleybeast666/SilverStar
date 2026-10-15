# Navigation stack input binding evidence — 2026-10-15

The v18 owner checker retains all task budgets, library/callback restrictions,
unknown-input rejection and dynamic/recursive-frame failures. It adds exact
reviewed navigation/timing/memory source identities and binds each source to the
complete ordered compiler-input content tuple. The source review is in
`docs/public/SCG/NAVIGATION_STACK_INPUT_REVIEW_20261015.md`.

`inputs.zip` is the original retained collection; it contains one identical
duplicate entry. `inputs_v2.zip` contains 94 unique entries after byte equality
was verified. Both manifests and archive hashes are preserved. The tests consume
the unique fixture, not arbitrary local generated sources.

The initial tests failed on genuinely unreviewed changed inputs. A new negative
test then exposed that independently approved old source/header versions could
be mixed. The final checker binds complete tuples and rejects that case along
with missing headers and altered CPU placement. The negative tests were not
weakened. Final test and actual emitted-gate receipts are archived in
`algorithm_timing_closeout_20261015/evidence.zip`.

PASS is limited to linked task roots and reviewed library/callback paths for
the exact compiler/configuration/ELF. It is not a main/MSP/ISR nesting proof,
an MCU timing result or hardware stack qualification. Critical-contract manual
acceptance and those broader bounds remain NOT PROVEN.
