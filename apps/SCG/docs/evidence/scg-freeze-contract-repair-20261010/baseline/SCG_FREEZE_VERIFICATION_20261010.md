# SCG freeze verification — held

Daily HEAD: `2b3d4ae8889f1fb0924ee18631c6a346e5822b98`; SCG tree: `e03ca99998df2d9d75ad3e817d25d83daba2bd8a`.

Verification completed; no owned test process remains running. Original full regressions retain six failures and twelve skips, so this run does not register a freeze. No product source, test or gate changes were made.

| Group | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| fzb01 | 46 | 2 | 0 | 2 |
| fzg01 | 138 | 0 | 0 | 0 |
| fzu01 | 150 | 0 | 0 | 0 |
| fzf01 | 198 | 4 | 0 | 10 |
| fzgui01 | 12 | 0 | 0 | 0 |
| fza01 | 16 | 0 | 0 | 0 |

F103 failures: known generic/pinned complete-model equality mismatch, plus the real unified backend test rejecting generic-model Export before compilation (`Native Ground binding differs from trusted facts/profile`). Neither failure was waived or xfailed.

Fresh native gates: 8 recorded; legacy generated gates: 12 recorded. Exact commands, exits, source/configuration identities, logs, failures/skips and hashes are in the companion JSON.

All eight native and twelve legacy emitted gates returned zero. Both normal and analyzer compilation/linking executed. The four PoT runs retain critical-contract review NOT PROVEN. Native candidates have no recorded warnings; legacy Ground links retain newlib syscall warnings. Separate tools-path diagnostic: one original importer case passed, the documentation case still failed because it gives a source-root policy an external Temp destination. Correct destination-policy replay diagnostic preserved idempotence and heading counts; original tests remain unchanged.

See SCG_SIX_FAILURE_CLASSIFICATION_20261010.md for per-case minimal reproduction, expected/actual behavior, fixed pre-merge baseline proof and supported-flow reachability. F103 legacy generic models are GUI-bound but refused by unified pinned authority; supported fresh unified GUI import/save/reload/build passed. Stack-report payload/overlay disagreement predates the merge and survives LF normalization; it is not the e135 native-radio EOL fix.

The explicit module list and command receipts define the scope; this is not an all-repository suite result.

- No source/tests/gates altered in this verification turn; no hardware, publish, push, tag or user-file writes.
- Complete cases of explicitly listed ordinary modules only; not all 226 historical SCG test files.
- Formal generation/release remains blocked. USB b66 independent safety review has NO_PASSED_OUTCOME; not retried or claimed reviewed.
- PoT is the existing F Prime-inspired project adaptation. Critical contracts, whole-program stack/WCET, hardware and flight qualification remain NOT PROVEN.
- Private Native ARM tests in fzb01 skipped because their separate opt-in flag was not enabled; these skips are not passes.

Tracked diff: EMPTY. Existing user inventory files are hashed in JSON; no user files were changed.
Isolated candidate HEAD: `5b99438ba4005ea02935e9734307e749e2e758e7`; status: clean.
Only owned execution sessions were tracked; no claim of an OS-wide process audit.
