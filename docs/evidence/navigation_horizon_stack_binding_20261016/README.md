# Mode2 stack binding review / 2026-10-16

The current source/object and exact compiler-input review is described in
`docs/public/SCG/NAVIGATION_HORIZON_STACK_INPUT_REVIEW_20261016.md`.
`validation.json` records both freshly and normally generated ARM links and
original emitted stack/P10/architecture/artifact actions, all exit0. The exact
owner checker/test sources, commands, complete logs, GCC frame reports and
linked stack-budget reports are in `validation.zip`; actual artifact hashes
refer to retained versioned task projects.56 relevant negative/policy tests pass.

The source/ordered-header tuple gate remains strict. There are no new stack,
callback, library, recursion, dynamic-frame or source-exclusion exceptions.
Zero indirect sites in changed actual objects is only a configured-object fact;
linked callback restrictions still execute. Main/MSP/ISR nesting, WCET,
hardware stack margin and critical-contract acceptance remain NOT PROVEN.

`inputs.zip` retains the initial two identical duplicate compiler-header entries.
They were byte-compared before unique `inputs_unique.zip` was created. Both are
retained and hashed. Tests consume the unique fixture, not arbitrary projects.
Two initial negative cases accidentally recreated an already approved complete
bus tuple; those failures are retained. The corrected negative first establishes
that its individually approved old/new inputs form an unregistered tuple, then
requires rejection. No production predicate was weakened to fix a test.

This closes the input-hash blocker for these two mode2 configurations. Active
ESKF recovery and final all-mode/full Host closure are subsequent work, not
claimed by this batch. No hardware, wireless edit, push/tag/release or cleanup.
