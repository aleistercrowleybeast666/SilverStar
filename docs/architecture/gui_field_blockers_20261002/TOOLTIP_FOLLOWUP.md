# Ground generation tooltip follow-up

Parent review requested a minimal correction after commit 41333b7. An enabled
custom Ground draft with no imported inventory was actionable, but its tooltip
incorrectly said READY while GroundTargetIssues_Get returned errors.

The tooltip now uses three states: disabled; enabled with issues (repair the
configuration and pass validation); enabled without issues (READY). Both zh_CN
and en_US have translated text. Generate-button enablement and backend checks
are unchanged. No controller or firmware code changed.

The new native Windows Qt widget regression failed before the production change
because the tooltip was 地面站：READY (tooltip_before.log). After the correction,
test_field_blockers.py plus test_ground_board_recovery.py passed: **7 passed in
41.77s** (tooltip_after.log). The new test checks both languages, the inventory
missing state, a valid board/radio/UART state, and the disabled state.

This is Qt widget/API verification, not native mouse acceptance. Earlier ARM
build evidence remains tied to production commit 08a113d; the tooltip-only
follow-up did not rerun firmware builds. Existing production excerpts in
PARENT_REVIEW.md refer to the pre-follow-up code; this note supersedes its
generate-button tooltip expression only.

Integration remains pending the parent final field commit. Keep the 5c451551
GUI baseline; do not cherry-pick onto the older FieldIntegration baseline or
merge a currently running field worktree. Version remains 0.1.1.
