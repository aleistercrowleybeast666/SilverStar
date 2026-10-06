# SF6 compact callback stack checkpoint (2026-10-06)

This revision changes the owning core checker and its reference overlay,
not target firmware, task sizes, protocols or failure expectations. It keeps
256 bytes of context allowance and the existing 256-byte minimum task margin.
Dynamic frames, recursion, missing selected-source `.su` reports and unknown
indirect instructions remain failures.

For the selected compact MPU6050 I2C path, the checker verifies the canonical
initialization and dispatch bodies, the selected source graph and direct
initialization callers. The actual linked read-only profile, ARM layout and
getter literal must agree; prepare/frame_read/extra_verify must be NULL in
the ELF. Register read/write dispatch adds the concrete adapter callbacks
and their full PlatformI2c, HAL and deadline descendants. A function name
alone earns no callback exemption. Changed bodies require a gate review.

Startup operation tables come from selected JY901B and/or M9N sources. All
seven callbacks remain covered. M9N recovery retains its immutable operation
table through controller.config, with either its separate or inlined caller
form. The M9N-only RF path no longer requires an unselected JY901B initializer.
SamplePoll's 112-byte frame and the 344-byte GNSS processing frame are nested
with their ancestors, never represented by a zero-cost callback exception.

The selected F1 FatFs provider is `sd_diskio_stm32f1flight.c`, not the unused
CubeMX generic sd_diskio.c. R0.11 declares SD_Driver writable: the checker
does not call it immutable. It verifies the exact fixed five-entry table,
registration/dispatch source fingerprints, source references, direct callers
and actual ELF initializer pointers. This records the existing vendor ABI
exception and does not authorize another callback registry. F4's existing
write/ioctl conditional slots remain supported when their callbacks are linked.
No F4/H7 HAL or RTOS implementation changes.

Real Release ELF results, with GCC 14.3.Rel1 and their complete `.su` sets:

| Target | Device estimate / configured | Logger estimate / configured | Result |
|---|---:|---:|---|
| RET6, SF6 + MPU6050/E28/BMP280/local SSLOG | 1720 / 2560 | 3072 / 3072 | FAIL: Logger margin 0 < 256 |
| RFT6, same plus M9N | 2112 / 2560 | 3072 / 3072 | FAIL: Logger margin 0 < 256 |
| F407, Full reference with JY901B/M9N/KF6 | 2144 / 2560 | 2104 / 3072 | PASS: all eight configured task budgets |

The F1 logger path includes the 1128-byte `f_open` frame and the actual disk
callback subtree. The next firmware batch must supply at least the missing
256-byte task margin without reducing this threshold, and record the real
linked RAM impact. No stack allocation was changed in this checkpoint.
Current RE/RF firmware ELF hashes remain those of ec1bfcd; a changed checker
is not a new firmware binary.

The 34 Host checker cases cover both selected startup sets, callback subtree
depth, changed bindings, non-NULL/writable MPU profiles, unknown callers,
extra indirect calls, recursion, missing frames, SD aliases/initializer
mutations and insufficient margins. These are injected tool-output fixtures;
actual ARM ELF checks are separate. The corrected ordinary MPU fixture now
selects Full tier explicitly; its three tests pass. Earlier compact_mode-only
fixture results did not prove Full behavior under the authoritative tier model.

F407 fresh ARM compilation/link succeeds. The six selected JY901B/M9N,
source-selector and startup Host executables complete, but their runner then
fails the mandatory storage integrity case at its stream configuration
expectation (test_logger_storage.c:372). This is a failed invocation, not a
selected or full-suite PASS. Historical full F1 Host failures remain recorded.

Evidence is `.work/evidence/f103_stack_closure`: complete commands/logs,
checker dirty snapshot, emitted-gate results and ELF-associated stack JSON.
The normal F407 project uses repository board payloads; this small regression
did not run CubeMX or establish hardware evidence. RE/RF reuse the previously
executed official CubeMX projects. Text Power10, real analyzer and ARM results
for unchanged F1 firmware retain their prior ec1bfcd scope; no new full safety
suite result is asserted here.

MSP/main, ISR nesting, runtime high water, timing, library semantic contracts
and the complete manual critical-contract review remain NOT PROVEN. Task
stack PASS alone is not a whole-firmware stack proof or acceptance.

## MPU readmission boundary, still pending

Physical recovery currently leaves qualification_revoked latched. Neither
SystemImuSample nor SystemInertialSample transports the native configuration
epoch. A current IoDetail query cannot prove the epoch of an already copied or
queued sample. Merely clearing healthy after configuration, incrementing
CAL_NONE/ALIGN generations, or ignoring the historical startup failure would
not satisfy readmission.

A safe next batch must review device publication, the inertial bridge and
queue consumers, calibration collection/commit, alignment including barometer
origin, health's historical startup mission_capable gate, and START's final
publication after potentially asynchronous storage work. These are shared
core consumers and require a small normal F407/JY901B/M9N regression. A
compact-only internal sample epoch would change RAM/stack/queue layout and
must be measured; serialized AIR M0/SSLOG record layouts need not change.
No such extension or historical-health bypass was implemented here.

Faults during calibration, alignment, origin collection and each START/storage
boundary must revoke current admission while retaining historical diagnostics.
START source locks must survive; retries must reuse the same device instance.
User-selected calibration/alignment and fresh barometer origin remain required.
GNSS no-fix remains ordinary navigation unavailability. SF6 already excludes
its unused double-window integrity machinery; the approximately 6936-byte
GNSS origin/ENU sample storage is not that machinery and is not removed.
