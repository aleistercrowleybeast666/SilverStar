# SCG freeze contract repair, 2026-10-10

Base: `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`. Worktree:
`C:/Users/chdxm/Documents/Codex/2026-10-10/task/r`; branch:
`fix/scg-freeze-contract-20261010`. This batch is independently authorized after
the six-failure freeze checkpoint. Daily SCG, GSHC/FLP, FINAL firmware, flight
mathematics and UI layout remain outside the edit scope. No hardware or publication.

## Contracts and ownership

- A legacy F103 model bound by the explicit-facts Native API is still recognized
  as private, so it cannot fall through to formal generation. The unified API
  requires its pinned facts authority. A different authority produces
  `F103_UNIFIED_REIMPORT_REQUIRED` before output creation. GUI controls are
  disabled at model display, show the same actionable message, and do not start
  a worker or SaveAs for this refused model. Reimport the original native F103
  CubeMX directory through Ground Station Hardware, save, then generate/build.
  Reimport validates the original sources and creates its own immutable snapshot;
  neither old model identities nor pinned hash values are relabeled in place.
- Unified positive regression fixtures now use the actual unified importer.
  The original full-model equality and real Export/Build assertions remain.
  Additional legacy negative and real GUI save/reload/reimport cases preserve
  rejection before work and demonstrate a supported recovery path.
- Pytest configuration exposes the SCG application root as well as `src`, so the
  actual `tools` package can be imported from a monorepo invocation. The document
  replay test gives its temporary destination the destination-root WorkspacePolicy;
  the actual path guard and byte-idempotence/heading assertions are unchanged.
- Generated Flight stack-checker authority remains the existing core-plugin
  payload. The stale reference overlay is synchronized byte-for-byte to it.
  No new accepted source identity, rejected case or stack limit is introduced.
- Physical device facts remain unchanged. Catalog validates mutually exclusive
  exact platform implementation domains from existing mandatory dependencies and
  platform match rules. Broad/missing domains and overlapping target parts are
  rejected before catalog publication. Tests retain uniqueness for each proven
  target, mixed-interface source uniqueness, and meaningful collision negatives.

## Validation evidence

The original six failures, twelve skips, all commands and logs remain in the
prior checkpoint `SCG_FREEZE_VERIFICATION_20261010.json` and classification report
in the calling task directory. Initial repair trial `srpre01` retains eleven
passes and one new GUI test-setup failure (settings placed outside its service
workspace); the fixture is corrected to the service workspace without weakening
the policy. Final complete module/generation/build evidence will be recorded
after executing the repaired commit.

Passing software checks do not complete critical-contract acceptance or
whole-program stack/WCET/hardware qualification. Power of Ten remains the
F Prime-inspired project adaptation with critical-contract review NOT PROVEN.
Formal USB release remains BLOCKED; b66 independent review is NO_PASSED_OUTCOME,
has not been retried, and must not be treated as passed.
