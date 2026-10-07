# Lightweight default and release scope — 2026-10-07

The user authorized the four Chinese tier labels **完整 / 标准 / 轻量 / 最简**
and synchronization into the local daily workspace. Persistent keys remain
`full / standard / compact / minimal`; schema, legacy loading and retained
configuration choices remain compatible.

Following the parent `review_f1_port_boundaries` conditional acceptance and
the user's permission for detectable ordinary log loss, the `compact` tier
now generates **56 normal / 16 estimator** log slots, independently of MCU.
The existing 200-byte slots and 4096-byte aggregation remain unchanged.
`minimal` retains 24/16, its selected smaller record slots and aggregation;
`full` and `standard` retain their previous 80/48 defaults. This change does
not alter navigation mathematics, estimator parameters, task stacks,
protocol checks, assertions or sensor timing.

The retained actual-rate evidence is isolated commit
`19c11c8e2fdd4573c6d265699cc9645ee0694747`, Library evidence version3
`libfile_d458ec7579c0819183ab196aaf0085a2`, payload
`file_00000000327481f88b3a9770bd1c6f5a`. IMU200/increment100/barometer20/GNSS25 Hz
logical Host inputs execute the real SF6, Flight START capture/owned request,
logger, F1 diskio and FatFs paths. Baseline zero-loss passes. A single additional
80 ms START sync delay fails one SF6_STATE enqueue, producing a detectable
sequence gap, overflow1 and health_flags256. The test and strict audit remain
**FAIL, exit1**. Original 56/16 and 64/16 pressure stress overflows217/22 also
remain FAIL. No recorded failure is reclassified as zero-loss success.

These ordinary-loss cases are accepted for the requested lightweight use;
they are not algorithm or critical START failures. Both normal actual-rate
cases persist every one of the 58 START records and 40 stream descriptors,
then acknowledge internal durability only after successful f_sync. Injected
f_sync error retains pending/captured state and ACK0. No loss tolerance applies
to critical metadata, false durability ACK, command readiness or fault handling.

The Reference JY901B lightweight configuration has57 boot snapshot records,
whereas the RF actual configuration has54. The owning logger has an independent
request with a uint16 cursor/count and generated const descriptor tables;
ordinary queue capacity does not store this whole snapshot. The generated
assertion is aligned to that real owner bound, including the four additional
START records and maximum magnetometer calibration records. All descriptors
remain covered. Descriptor-array and runtime request validation remain intact.

No new ARM build, static-analysis run, Power10 run, stack proof or hardware
action is performed for this default/label/template-only closeout. Fresh
SourceGraph/configuration rendering and selected tier, logging, compatibility,
GUI and translation regressions are recorded separately. Previous actual RF
ARM evidence remains scoped to the unchanged product source with56/16 build
definitions: Flash256748 B, RAM86872/98304 B, spare11432 B (11.629%). Previous
RE minimal24/16: Flash209472 B, RAM54208/65536 B, spare11328 B (17.285%). Task
stacks and MSP are already included once in RAM. The20% spare target is advisory,
not a newly imposed release gate.

The user explicitly waived additional F103 board testing and further field
testing as mandatory closeout gates. Release notes must disclose the software
compilation/Host evidence and unavailable F103 hardware evidence. No claim of
F103 hardware, flight, timing or sensor accuracy qualification is made. Software
and critical log contracts retain their gates; broader Power10 manual proof
limitations are not erased by this conditional-use decision.

Frequency readback is source/configuration evidence, not a new measurement.
BMP280/BMP390/MS5611 advertise fixed20 Hz configurations. BMP390/MS5611 enforce
50 ms cycles. BMP280 waits at least45 ms but lacks a50 ms cycle limiter, so
20 Hz is not an exact measured runtime cadence; an ideal1 ms state-machine
schedule yields approximately47 ms per completed sample. JY901B defaults to a
shared200 Hz IMU/module output setting and counts fresh0x56 frames; this does
not prove an independent pressure conversion for every frame. MPU6050 uses
SMPLRT_DIV4/DLPF_CFG3 and a5000 us profile. RF/RE select IMU200 Hz and two-sample
INS aggregation100 Hz. Host pressure inputs at20 Hz do not establish BMP280
physical conversion timing. No sensor cadence is changed in this closeout.

## Recorded validation

Final short regression: **78 passed, 3 deselected, exit0**, 152.65 seconds.
Scope is `test_feature_tiers.py`, `test_feature_tier_logging_policy.py`,
`test_compact_mode.py`, `test_i18n.py`, excluding three slow algorithm-view GUI
cases (`gui_sf6_pure_ins_switch` and `full_gui_views`). The first-page test
executes the actual tier combo and verifies all four exact Chinese labels and
unchanged itemData keys. This is not a full SCG/Host suite pass. One known
pytest `cache_dir` configuration warning is retained.

Both existing RF/RE models pass fresh SourceGraph and GeneratedFiles rendering
(22 outputs each, five key files retained per model in separate evidence
directories). RF renders56/16; RE renders24/16. The old models and generated
projects remain unchanged. No whole-repository or project payload copy.

The first run is retained:78 passed/3 failed, exit1. The failures identify
the new Reference snapshot57 versus queue56 check, the old Chinese label
expectation, and a previously stale Minimal queue-versus-owned-snapshot
expectation. The latter two contract checks now verify the real independent
snapshot owner rather than requiring the ordinary queue to store its whole
batch. The second run is retained with a test helper import typo, collection
error/exit1; the third run above fixes that import and completes. Earlier
source states are traceable in the conversation; local dirty source snapshots
were not captured for the first two runs. Final source is committed and all
commands, complete logs, source hashes and output hashes are saved.
