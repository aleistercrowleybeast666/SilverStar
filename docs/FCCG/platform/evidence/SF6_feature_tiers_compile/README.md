# Four-tier F1 compile evidence

Report: [actual results and blockers](../../details/SF6_FEATURE_TIERS_COMPILE_CHECKPOINT.md).

`feature_tiers_compile_checkpoint.zip`: 10,548,763 bytes, 812 entries.
SHA-256: `b192afd4c6f30c20cb9216f289f91008b45c1e78cf40d1b69e22901fdb2977c8`.
Source checkpoint: `a6b881a65c2b6f848e33b0c2a89b612b1ea70f79`.
Every contained entry is hashed in `MANIFEST.json`; the ZIP and all entry hashes
were verified after writing. Generated project trees and a repository clone are
not included. Exact compile revisions and failed checks are preserved.

Private Library file: `libfile_cbe01e7886288191b232a02f4802c473`, version 1.
Upload file: `file_000000004f608230973d2d91f4f367c3`. Replacement succeeded.
Version 0 remains historical evidence: 10,532,726 bytes, SHA-256
`2f62aa71fa833f41000b9c77dbf0303d75f7262225f4d25d6a90b3ea08d1a550`.
Version 1 changes three historical receipt log references and report wording,
and adds one stable light/English screenshot with its small state receipt/harness.
Original failure logs, exits, artifact bytes and product source are unchanged.
All modified and added entry hashes are verified in the corrected manifest.
Local xattr registration is unsupported by this Windows Python environment;
it does not reverse the confirmed Library upload.

Patch reconstruction uses `source/final_from_kf6.patch` from the named KF6 base,
then `ret6_arm_from_final.patch` or `rft6_arm_from_final.patch` from the bundled
final source checkpoint to the exact corresponding ARM source revision.
The bundle also includes the saved generated models, headers, owning memory
provider, source-file hashes and link-listed source identity checks.

`a6b881a65c2b6f848e33b0c2a89b612b1ea70f79` to the initial delivery HEAD
`75a13544bee54ce418f8e3971787a4389264554b` adds only this evidence index and ZIP.
The 1,831 tracked SCG paths have identical modes/types/Git blob hashes; both SCG
tree IDs are `87e22705cab74a38923acca6f38a08261b2e2c03`.
The subsequent correction changes documentation/evidence only. The manifest's
product source checkpoint remains the original `a6b881a` identity.

These are compile artifacts. Full Host and stack gates failed, critical-contract
review is NOT PROVEN, both targets miss 20% RAM spare, and hardware was NOT RUN.
The B checkpoint remains fail-closed; readmission is not accepted.
