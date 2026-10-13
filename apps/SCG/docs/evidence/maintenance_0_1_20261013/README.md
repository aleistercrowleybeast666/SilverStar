# Maintenance 0.1 evidence

`evidence.zip` is the exact local dirty-source snapshot based on
`e1c40c5b91935cb19ed39999038bff181ba6b60d`, with commands, source/input hashes,
complete successful and failed logs, ARM/analyzer ELF/map/stack artifacts,
generated configuration and decoder, tool versions and mocked GUI screenshots.
`manifest.json` inside the ZIP hashes every retained entry; `sha256.txt` hashes
the complete archive. Extraction is not required to inspect the manifest.

Final runs: arm02, analyzer02, gates04, host05, gshc_tests04, scg_tests08.
Host: 80 executables / 4,446,532 checks / zero failures plus storage-integrity
normal/fault runs. GSHC: 74 passed / 12 subtests. SCG: 93 passed / 4 conditional
skips. Gates: actual emitted combined invocation, exit 0. These are scoped
results, not a whole-repository or hardware acceptance claim.

Critical-contract and whole-program stack acceptance remain NOT PROVEN. No ports,
probes, hardware, FINAL/UNDERLINE projects, frozen releases, push or tags were used
or changed. USB expansion remains deferred. No cleanup is authorized by this
inventory. See [the review record](../../../../../docs/public/SCG/MAINTENANCE_0_1_20261013.md).
