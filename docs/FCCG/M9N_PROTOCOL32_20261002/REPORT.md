# M9 protocol 32.01 independent candidate — 2026-10-02

Base: `170f1cb55daedf8e8d308a7bc845b2fa5b79d102`. Branch: `fix/m9n-protocol32-20261002`.
Worktree: `D:/python_software/SilverStar/.work/M9nIdentityHotfix_20261002`.
Only the owning M9N payload and M9N Host suite are changed. No Radio/Baro integration, hardware/COM/DAP access, flash, push, merge, tag, reset, clean, frozen candidate overwrite, sensor configuration edit, or shared-venv modification occurred.

## Proven failure and identity scope

The real captured frame is 168 bytes, UBX 0A/04 with 160-byte payload, checksum `40 41`, SHA-256 `fba6fd143015ed97f66b997acbfcd5e3a3d36922f600cf5fb131808d1b5633d8`. It reports `ROM CORE 4.04 (d964f4)`, HW `00190000`, `FWVER=SPG 4.04`, `PROTVER=32.01`, GPS/GLO/GAL/BDS and SBAS/QZSS, with **no MOD field**. The frame bytes and parent Capture.json are retained here, independently length/header/hash/checksum verified. Its capture involved debugger halt; it is identity-byte evidence, not a normal startup timing measurement or a packaging proof.

Old generated source rejects 32.01, and also requires MOD unconditionally. Full logs for three old-source counterexamples are preserved under `.work/m9_evidence*`; initial 998 checks/1 failure, complete official fields 1289 checks/8 failures, and additional real-frame injection 1289 checks/9 failures (the last run includes the already failing named-32 startup cases). The late explicit FW/HW conflict regressions also fail against generated v3 before those guards (4,820 checks/8 failures), then pass against final v4 (4,820 checks/0 failures). That complete counterexample is archived as `m9_fw_conflict_counterexample`. No claim of a model-suffix fault is made. The old Host fixture copied only 12 of the 13 `PROTVER=27.12` bytes; it now copies all 13 bytes.

The official [M9 SPG4.04 interface description](https://content.u-blox.com/sites/default/files/u-blox-M9-SPG-4.04_InterfaceDescription_UBX-21022436.pdf) applies to NEO-M9N and M9140 ROM/FLASH, associates SPG4.04 with protocol32.01, and treats MOD as optional. The [release note](https://content.u-blox.com/sites/default/files/GNSS-FW-SPG404_ReleaseNote_UBX-20036165.pdf) corroborates the firmware/protocol association.

## Restricted design

| Profile | Identity requirement | Write authorization |
|---|---|---|
| legacy27 | Exact MOD=NEO-M9N, numeric 27.00–27.99; if HW is supplied it must be00190000; explicit SPG4.04 FW contradicts27.xx and rejects | Existing named-model behavior retained |
| named32 | Exact MOD=NEO-M9N, exact 32.01, exact FWVER=SPG4.04; advertised nonempty HW must be 00190000 | Normal existing config read/apply/verify controller |
| restricted ROM32 | MOD absent, exact captured ROM CORE4.04 revision d964f4 + HW00190000 + FWVER SPG4.04 + protocol32.01 | Signature permits read-only discovery; all 23 individual RAM VALGET responses must prove expected key and encoded type/width before identity_verified or any VALSET |

Restricted profile3 means compatible M9 ROM SPG4.04, **specific NEO-M9N package unknown**. Explicit wrong MOD always rejects, even when the base signature matches. No other protocol32 minor or unknown major is accepted. Malformed numeric 27.* text is rejected; the historical supported numeric 27.xx version boundary is preserved, without adding any new major range.

Parsing stays within 40-byte base + at most32 fixed 30-byte extension fields and the existing 1024-byte RX payload. NUL termination is required within each field, zero-fill/empty/opaque terminated fields and arbitrary legal ordering are allowed, identical duplicates are accepted, conflicting duplicates reject. CRC gates dispatch as before. Invalid/missing fields reject with bounded native diagnostics. No timeout increase: outer5000ms and inner200+2200+250+2200ms unchanged.

Startup already reads all23 keys before differences can be written. The restricted driver additionally tracks a per-instance 23-bit successful-read mask, blocks native asynchronous and raw/synchronous VALSET while unverified, and invalidates capability authorization on a new probe or RX discontinuity. Individual VALGET response parsing continues to validate CRC/version/layer/position/key/type/count. Signal-key writes wait **after ACK** for the official500ms using nonblocking startup ticks; unchanged stage timeout45s accommodates this finite extra wait. Baud is still applied last, reconnect reparses identity, final23-key readback and new PVT remain required for READY.

`GnssNeoM9n_IdentityDiagnosticsGet` gives current probe outcome, last checksum-valid identity result, persistent last rejection, profile, numeric protocol version, field-presence flags, baud and capability mask. Existing probe enum, AIR/SSLOG wire formats and log layouts remain unchanged; outer startup may still report NotPresent, while this native getter/debugger snapshot exposes the reason. A signature-pending probe can identify the communication candidate but cannot write. Legacy27 FWVER remains optional; the known SPG4.04/27.xx conflict is now rejected. Legacy blocking Identify does not treat an unverified restricted signature as verified.

## Exact CFG audit

All23 IDs and types are present in the official32.01 document; no key removal, type relaxation, sensor target edit or readback bypass was needed. UART1 here is **receiver port UART1**, independent of the MCU resource UART2. Detailed machine-readable audit is `CFG_COMPATIBILITY.json`.

| Driver key | Official ID | Type/bytes | PDF page |
|---|---|---|---|
| `GNSS_CFG_UART1INPROT_UBX` | `0x10730001` | L/1 | 231 |
| `GNSS_CFG_UART1INPROT_NMEA` | `0x10730002` | L/1 | 231 |
| `GNSS_CFG_UART1INPROT_RTCM3X` | `0x10730004` | L/1 | 231 |
| `GNSS_CFG_UART1OUTPROT_UBX` | `0x10740001` | L/1 | 232 |
| `GNSS_CFG_UART1OUTPROT_NMEA` | `0x10740002` | L/1 | 232 |
| `GNSS_CFG_UART1_BAUDRATE` | `0x40520001` | U4/4 | 231 |
| `GNSS_CFG_RATE_MEAS` | `0x30210001` | U2/2 | 223 |
| `GNSS_CFG_RATE_NAV` | `0x30210002` | U2/2 | 223 |
| `GNSS_CFG_RATE_TIMEREF` | `0x20210003` | E1/1 | 223 |
| `GNSS_CFG_MSGOUT_NAV_PVT_UART1` | `0x20910007` | U1/1 | 211 |
| `GNSS_CFG_NAVSPG_DYNMODEL` | `0x20110021` | E1/1 | 216 |
| `GNSS_CFG_SIGNAL_GPS_ENA` | `0x1031001f` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_GPS_L1CA_ENA` | `0x10310001` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_SBAS_ENA` | `0x10310020` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_SBAS_L1CA_ENA` | `0x10310005` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_GAL_ENA` | `0x10310021` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_GAL_E1_ENA` | `0x10310007` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_BDS_ENA` | `0x10310022` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_BDS_B1_ENA` | `0x1031000d` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_QZSS_ENA` | `0x10310024` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_QZSS_L1CA_ENA` | `0x10310012` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_GLO_ENA` | `0x10310025` | L/1 | 226 |
| `GNSS_CFG_SIGNAL_GLO_L1_ENA` | `0x10310018` | L/1 | 227 |

Important config constraints remain ordinary failures: CFG-SIGNAL changes reset the GNSS subsystem and require ACK+500ms; at least one major constellation signal must remain enabled. Individual writes can be NAKed for an invalid intermediate constellation combination, rather than silently accepted. CFG-VALSET v0 accepts RAM/BBR/flash layer bits; normal startup retains its existing RAM-layer behavior and existing final readback. Startup protocol keys including RTCM3X input are documented, not unsupported M9 keys. Rate MEAS minimum25ms, NAV1–127, TIMEREF GPS1 and current dynamic model encodings are compatible. NAV-PVT shape remains92bytes.

The first generated candidate failed the unchanged102400B main-SRAM artifact budget at102496B. Complete failure logs are preserved. Fixed MON-VER strings are now parsed in one bounded local object; only compact reason/profile/version/presence/capability metadata is retained per instance. No buffer/cache/queue budget, stack allocation or artifact threshold was reduced or weakened.

## Validation status

Final candidate is generated independently from the owning source using `FccgService.ReferenceProject_Create`/normal reconcile/save for the repository reference KF6 Flight + F407 SS0.5 configuration. It is a **software reference candidate**, not a promise that its configuration equals the parent's already-burned KF6_v8 candidate. Parent must review the core diff and regenerate/integrate in the authorized RF/Baro order before any board use.

Python is read-only `D:/python_software/SilverStar/.venv/Scripts/python.exe`, CPython3.14.0 based on the recorded Python314 installation; no packages or environment files were changed. Host GCC MSYS2 16.1.0; ARM GCC14.3.1 Arm GNU14.3.Rel1; Make uses `-j2` and `SHELL=cmd.exe`.

Final v4 Release ARM compilation/link, full Host, architecture, PoT text, real ARM -fanalyzer, artifact, stack/memory gates all exit0. Host:72 executables,4,400,517 checks,0 failures; M9N C suite4,820 checks,0 failures;7 positive compile cases and17 expected compile rejections. FLASH318828B, main SRAM102368B (physical spare28704B; reviewed102400B budget spare32B), CCM55432B (spare10104B), no heap symbols. The exact base Release artifact uses102328B main SRAM, so the final slice adds40B of main SRAM. Device stack estimate remains2128B of2560B (estimated margin432B); this is the generated tool scope, not a complete ISR/library/physical stack proof. Parent must rerun the tight reviewed SRAM budget after integration.

Debug ARM compilation reaches link but fails on pre-existing KF6 reference missing `SystemNavigationBackend_Predict`, `_SnapshotGet`, `_Reset` and related backend definitions. The exact170f1cb generated baseline was independently ARM-built and reproduced the same Debug linker failure; this is an outstanding reference-project blocker, not repaired outside the M9N slice. No Debug ELF/BIN, artifact pass or all-configurations pass is claimed.

`FINAL_MANIFEST.json` records final gate commands/exits/full log hashes, changed-source hashes matching generated sources byte-for-byte, Release ELF/BIN/HEX/MAP hashes, baseline ARM evidence and all archived logs. Deterministic gzip archives preserve complete logs under `logs/`; `CORE.diff` and `KEY_FUNCTIONS.c.txt` give the reviewable core diff and exact key function source. Every failed/partial attempt remains available. Tool PASS establishes its recorded scope; generated PoT explicitly retains critical-contract NOT PROVEN. Stack/RAM summaries do not prove target WCET, all ISR/library paths, real UART timing, GNSS accuracy, flight safety or hardware qualification.

Manual changed-path review: all introduced loops have static bounds (30 bytes,32 fields,2 version profiles,6 read groups,23 distinct keys); no heap/recursion/ISR parsing/callback registry was added. External malformed frames retain ordinary rejection. Read/write authorization is per instance; no partial key mask grants success. Parent review and real startup verification remain outstanding.

Reproduction: run the recorded Python executable on `run_fresh_gates.py <new_suffix>`; it refuses existing candidate/output directories and uses all emitted gates with `-j2`. It exits nonzero if any gate fails, including the known base Debug-link failure. Final raw Release artifacts remain below `apps/FCCG/tests/artifacts/m9_candidate_v4/build/FCCG/SilverStar_F407/Release/`; v1/v2/v3 directories and failure logs were preserved. v2 was generated but not gated; no pass is attributed to it.
