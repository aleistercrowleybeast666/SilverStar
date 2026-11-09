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

2026-11-10 归档位置更新：以下大文件已迁出当前工作树，历史内容及原 SHA-256 不变；可从固定提交下载，或按 [冷归档清单](https://github.com/aleistercrowleybeast666/SilverStar/blob/feature/usb-transport-0.1.3-20261013/docs/evidence/gui_convergence_20261110/cold_archive_manifest.json)恢复。

- [evidence.zip](https://github.com/aleistercrowleybeast666/SilverStar/blob/e143188dbad9ca0a70dfdc27f52b4226a370cfe8/apps/SCG/docs/evidence/maintenance_0_1_20261013/evidence.zip)
