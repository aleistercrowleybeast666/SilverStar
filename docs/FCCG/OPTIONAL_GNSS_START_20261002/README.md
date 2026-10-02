# Optional GNSS START restoration — KF6 Release candidate

Production commit: `d1c991a813f752b45dcdc8a2145647ab5dbaf55d`.
Source + actual-interface regression commit: `0610150f991ddd21ad04d02aa911e48a72ffd675`.
Independent branch/worktree only; candidate not flashed, pushed, merged or tagged.
Generated from complete JY901B/NEO-M9N/SX1281/storage radio-handshake fixture with KF6,
logging enabled and selected VectorConstraints alignment. Configuration remains unchanged.

The GNSS-fusion-preflight-origin macro still equals 1. It constrains GNSS fusion,
not whether every mission requires GNSS. Alignment uses the declared required mask
(default ATTITUDE|BARO). Freeze rejects absent GNSS only when explicitly required;
otherwise its real origin/frame/sample remain invalid and GNSS fusion is disabled.
It clears old frozen GNSS/frame state before a new freeze. Late fixes cannot establish
an origin after mission freeze. No pseudo-origin, automatic moving rebase, timing or
receiver-profile changes are introduced. Required attitude, barometer, calibration,
storage and mission safety admission continue through their actual owning interfaces.

The new Host integration compiles the actual INS/alignment strategy, calibration,
health/capabilities, logging-enabled storage admission, lifecycle, FlightTask and selected
estimator. Sensor samples and startup device reports are raw endpoint inputs; the stored
projection snapshot is an explicit input to the real storage expression, not evidence
of an SD commit or flash test. Readiness, Freeze, PrepareNavigation and START are not
stubbed. It covers optional no-fix START, explicit required-GNSS rejection, required
attitude/barometer/storage rejection, normal origin START, no late origin/fusion, and
clearing a previously valid frozen origin. Default integration: 782 checks; explicit
required integration: 669 checks; both zero failures.

GSHC START prerequisites are exactly preflight command entry, calibration.ready,
alignment.ready, system_ready and start_unlocked. start_ready further requires no
pending command and start_block_reason == AirAckResult.OK. Connection, capability ACK,
profile support, restart suspicion, pending START/ACK/retry behavior remain intact.
NAV diagnostics remain display information, including UNSUPPORTED for absent NAV schema;
they do not override M0. GNSS transition/availability event code is unchanged. No AIR/M0
field, wire layout or ID changed. Targeted GUI/state/ACK tests: 66 passed + 3 subtests;
one pytest configuration warning from disabling its cache provider is preserved.

The ESKF actual Initialize already calls Reset after argument validation and before
configuration/source/frame setup. Reset now clears s_frame. Exact source appears in
owning_functions.md. SF6/ESKF full algorithm qualification and Debug remain deferred;
this candidate closes the prioritized KF6 Release gates only.

History: both mandatory-GNSS gates originated in old FCCG commit
6288994b593ab47fda0554a35deaec2c71a10a0b (2026-09-27, Implement ESKF15 navigation
readiness sensor contracts); the unified repo inherited them in 2763bb8. Historical
TEST_0–3 estimator_task sources lack the added gate; TEST_4 contains it. Historical and
frozen packages were read only. Counter generation at old production base 004551 with
new assertions fails real Alignment (297 checks, 1 failure) and separately real
Freeze/Prepare (294 checks, 6 failures). First two direct Freeze/Prepare failures are
the decisive second counterexample; a later uninitialized-output check in that initial
test is not interpreted as production evidence. The final test initializes snapshots.

Evidence retains all initial and harness failure logs. The initial final candidate's
analyzer was interrupted by exec transport loss: INCOMPLETE, not a pass. The final2
fresh generation is the sole final candidate. The first RealHarness1 zero-job run is
INVALID, not a pass; the target runner now requires both actual executables. Early
fixture failures (including missing device.present and wrong calibration/Alignment
init order) are preserved and corrected in fixture inputs only.

All seven final2 gates must have actual exit 0 for this package script to run. PoT's
critical contract result remains NOT_PROVEN and requires manual review; no safety or
flight qualification claim follows from these tooling checks. Firmware identity and
full resource/stack results are in manifest.json and compressed original gate logs.

Tools: generation/GUI uses exact Python D:\python_software\SilverStar\.venv\Scripts\python.exe (3.14.0),
whose base is C:\Users\chdxm\AppData\Local\Programs\Python\Python314. The Host
storage stdlib subprocess resolves bare python through the documented PATH prefix to
D:\msys64\ucrt64\bin\python.exe (3.14.5). Both interpreter identities were verified.
ARM GNU 14.3 rel1 gcc 14.3.1, UCRT64 Host gcc 16.1.0, mingw32-make 4.4.1; ARM and Host
make invoked with -j2 SHELL=cmd.exe CONFIG=Release. No shared environment edits or serial I/O.
