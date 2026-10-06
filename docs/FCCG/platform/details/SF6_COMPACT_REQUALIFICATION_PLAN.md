# SF6 compact MPU requalification transaction: review plan

2026-10-06, isolated candidate after 84b336e. Design and read-only evidence only;
no production re-admission behavior or protocol change is implemented here.

Physical recovery currently preserves the same MPU instance, source lock,
mount configuration and sample sequence, with bounded attempt deadlines and
backoff. Qualification remains revoked. Recovered online samples may be useful
for fresh calibration; online must not itself restore READY or mission-capable.
A separately queried driver generation cannot safely identify a sample that was
already queued under a previous generation.

The smallest proposed transport change is compact-MPU-only internal source ID
and epoch metadata copied coherently from the native sample's source/config
identity into SystemImuSample and SystemInertialSample. Carry it through the IMU
queue, calibration input and alignment input. Do not add it to M0 messages or
existing SSLOG records/descriptors. If implementation needs a serialized format
change, stop and report it before changing the contract. Epoch advancement must
be monotonic or invalidate on wrap; compare equality, not chronology inferred
from unbounded subtraction. Never memset the locked source context to recover.

Device task owns physical epoch/recovery changes. Flight/lifecycle owns the
qualification witness. A new epoch revokes READY, drains or rejects old queued
samples, invalidates CAL/ALIGN witnesses and the barometric origin. CAL and ALIGN
must be explicitly completed again for that same source/epoch; CAL_NONE/reset
must not manufacture a fresh qualification witness. Startup's historical failed
report remains diagnostic evidence. Any current-epoch admission logic must
exempt only the specifically reviewed recovered IMU condition, never unrelated
failed required devices. GNSS absence of fix remains an ordinary no-fix state.

START reserves source/epoch plus successful CAL/ALIGN/origin generations before
its existing blocking storage/snapshot preparation. Immediately before publishing
FLIGHT, revalidate the reservation and all witnesses in a bounded coherent
critical section. Never hold IRQ masking over I2C, FatFs or queue waiting. A
recovery epoch change during preparation aborts the existing transaction through
its established error path, clears stale readiness and publishes no success.
Repeated recovery of the same locked instance remains possible; source reselection
and automatic acceptance of old origins are forbidden.

The conditional scope must come from the authoritative generation capability,
not runtime mode tests alone. Shared bridge/CAL/ALIGN/lifecycle code also compiles
for F407. Normal F407 layouts/behavior should remain unchanged under the disabled
capability; compact F407+MPU exercises the same new path if supported. JY901B/M9N
normal regressions and the current F407 ARM configuration are required. No
blanket change to generic startup acceptance or default algorithm rejection.

Read-only GDB examination of the actual RE ARM ELF reports SystemImuSample=80,
SystemInertialSample=80, the 16-entry IMU queue=1280, calibration latest sample=80,
SensorImuAdapter=256 and the single MPU adapter context array=256. Adding two
uint32 fields makes the intended sample layout 88 bytes (must be compiled to
verify): queue +128, calibration latest +8, adapter latest +8, totaling 144 bytes
of identified persistent sample growth. A coordinator/token/witness design is
expected to add roughly 32–64 more bytes, so an initial estimate is 176–208 bytes,
not an actual map delta or complete RAM/stack bound. Native sample metadata
already exists and need not enlarge its device buffers. All local sample copies
and changed stack frames must be remeasured; the RE spare 1800 bytes is not a
20-percent margin or proof that this change will link safely. GDB emits a host
encoding warning; complete commands/output and partial earlier errors are saved.

Required regression cases: initial success; pre-START recovery; recovery during
CAL, ALIGN, origin capture, each blocking START stage and final publication;
stale queued samples; same-instance lock retention; repeated bounded attempts;
epoch wrap; initial failed IMU with a different required startup device failed;
recovered IMU with CAL_NONE; no-fix GNSS; ordinary normal F407 behavior; corrupt
internal witness/state entering bounded fail-stop; expected external timeout/error
paths remaining ordinary failures. Show each pre-fix failure and normal/fault
post-fix behavior before manual acceptance. Fresh ARM map/ELF, emitted Power10,
real analyzer, relevant Host and revised stack reports are required after any
implementation. All of these implementation checks are NOT RUN for this plan.
