# Four-tier F1 compile evidence

Report: [actual results and blockers](../../details/SF6_FEATURE_TIERS_COMPILE_CHECKPOINT.md).

`feature_tiers_compile_checkpoint.zip`: 10,532,726 bytes, 809 entries.
SHA-256: `2f62aa71fa833f41000b9c77dbf0303d75f7262225f4d25d6a90b3ea08d1a550`.
Source checkpoint: `a6b881a65c2b6f848e33b0c2a89b612b1ea70f79`.
Every contained entry is hashed in `MANIFEST.json`; the ZIP and all entry hashes
were verified after writing. Generated project trees and a repository clone are
not included. Exact compile revisions and failed checks are preserved.

Private Library file: `libfile_cbe01e7886288191b232a02f4802c473`, version 0.
Upload file: `file_0000000096bc8230bdd8239e4d010401`. Upload succeeded.
Local xattr registration is unsupported by this Windows Python environment;
it does not reverse the confirmed Library upload.

Patch reconstruction uses `source/final_from_kf6.patch` from the named KF6 base,
then `ret6_arm_from_final.patch` or `rft6_arm_from_final.patch` from the bundled
final source checkpoint to the exact corresponding ARM source revision.
The bundle also includes the saved generated models, headers, owning memory
provider, source-file hashes and link-listed source identity checks.

These are compile artifacts. Full Host and stack gates failed, critical-contract
review is NOT PROVEN, both targets miss 20% RAM spare, and hardware was NOT RUN.
The B checkpoint remains fail-closed; readmission is not accepted.
