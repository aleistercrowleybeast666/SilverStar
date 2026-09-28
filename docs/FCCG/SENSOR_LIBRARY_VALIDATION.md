# Joint sensor library implementation and validation

Executed 2026-09-27. This report covers FCCG builtin drivers, startup/readback,
source/resource generation, Host mocks and compilation. Original SS_0_5_TEST_3
firmware and logs remained read-only. No hardware was flashed or commanded and
no physical output was triggered. Repository-wide acceptance remains in
[VALIDATION.md](VALIDATION.md).

## Explicit implementation limits

- BMI088 raw200 retains independent accel/gyro direct reads and raw FIFO events.
  Separate **Sync400 I2C/SPI** plugins implement the pinned Bosch synchronization
  image and 400 Hz synchronized register path. They require declared physical-net
  bindings and runtime gyro-input/sync-ready IRQ pairs before any valid sample.
  Raw200 has no navigation qualification; borrowing Sync400/JY901B qualification
  while reading raw200 is rejected by the generic same-source capability contract.
- Physical DRDY edges are not timestamp-captured. SPI adapters observe an IRQ
  notification; FIFO initial MCU anchors and fixed-ODR reconstruction retain
  `TIME_UNCERTAIN`. Native ICM/BMI323 ticks preserve physical sample spacing after
  that anchor. Electrical timing, drift and target task WCET remain unmeasured.
- New UBX optional NAV-SAT/MON-RF/DOP APIs are unsupported and are not enabled.
  The compact last-configuration report retains actual readback evidence;
  unrecorded write/settle/PVT-recovery stage histories are `NOT_EXECUTED`.
- M8 independent persistent-layer comparison is unsupported. Normal startup is
  RAM-only; explicit persistence returns `UNSUPPORTED` without CFG-CFG. JY901B
  defaults to RAM without SAVE because stored-layer equality cannot be proved.

All new hardware is **HARDWARE_UNVERIFIED**. Sync400 has software pairing and generation evidence, while
physical synchronization timing, field validation and launch readiness remain unverified.

## Shared implementation

`silverstar.sensor.register_bus` owns bounded register I/O, shared IMU mechanics
and adapters in `Devices/SensorBus`; physical profiles/wrappers are in
`Devices/IMU/<MODEL>`. `silverstar.sensor.ubx` owns the new bounded parser and
adapter in `Devices/GNSS/UBX`. Selected instances own independent state; only
selected packages and dependencies enter the source graph. The existing M9
hardware plugin retains its established implementation, expanded with identity,
RAM-only boot and differential persistent-layer verification. The shared UBX M9
profile also has mock coverage; this is not a claim that M9's old parser was replaced.

Samples carry signed raw values, SI vectors, source/configuration/calibration
generation, sample/receive time and quality. Scaling is admitted only after
fixed-profile readback. Unsupported ODR/range requests are rejected. Clipped
samples retain sign. Configuration rejects an active runtime owner. SPI uses
bounded transfers, error-path CS release and model-specific dummy bytes.

The Device task nominally runs every 1 ms. The new IMU adapter consumes one chip
FIFO sample per iteration; it does not allocate another software queue. Remaining
FIFO depth/ODR or native ticks reconstruct physical sample time, rather than
giving a whole batch the host read time. Overflow/malformed/discontinuous data
are errors. Stop/start performs a volatile reset and invalidates old history.
ST 240 Hz uses the rational 12500/3 us period, avoiding cumulative 4167 us rounding.
ST320X's high-g output remains separate from the low-g INS input.

## Per-model profiles

Every new IMU writes only volatile differences, verifies masked readback, waits
for settling and requires a valid sample before READY. No SAVE/OTP/trim/firmware
update is sent. All listed I²C/SPI forms have actual Host mock and strict compile
coverage. The generated-interface table below is mechanically derived from the
selected plugin's actual sources and resource declarations.

| Model | Identity | Effective fixed profile | Actual FIFO/time behavior |
|---|---|---|---|
| MPU6000/6050 | WHO_AM_I 0x68 | 200 Hz, ±16 g, ±2000 dps, DLPF 3 | 14-byte big-endian accel/temp/gyro, depth/ODR epoch; MPU6050 has no SPI plugin |
| MPU6500 | 0x70 | 200 Hz, ±16 g, ±2000 dps, DLPF 3 | 512-byte FIFO, model-specific temperature scale |
| MPU9250 | 0x71 | 200 Hz, ±16 g, ±2000 dps, DLPF 3 | Six-axis FIFO; magnetic function is not required for IMU readiness |
| BMI088 | accel 0x1E, gyro 0x0F | 200 Hz, accel ±24 g; gyro ±2000 dps / 23 Hz BW | Separate 0x18/0x68 or CS resources; dual-ready raw reads; independent tagged accel and gyro FIFOs, no synchronization qualification |
| BMI323 | 0x43 | 200 Hz, ±16 g, ±2000 dps; 0x40B9/0x40C9 | Word registers and feature preparation; 16-byte FIFO with 39.0625 us ticks; required SPI activation/dummy bytes |
| ICM-42605 | 0x42 | 200 Hz, ±16 g, ±2000 dps, low noise, UI 0x33 | 16-byte uncompressed FIFO, big-endian count/data, 1 us native ticks |
| ICM-42688-P | 0x47 | Same selected rate/ranges, separate model profile | Model identity/readback; 16-byte FIFO and 1 us ticks |
| ICM-45686 | 0xE9 at 0x72 | 200 Hz, ±16 g, ±2000 dps, low noise | Distinct reset/indirect-register preparation, double count read per AN-000364; little-endian 16-byte FIFO/native ticks |
| LSM6DSV32X | 0x70 | 240 Hz, ±16 g, ±2000 dps, high performance | Tagged gyro/accel pairs; repeated/unknown tags rejected; rational ODR epoch |
| LSM6DSV320X | 0x73 | Low-g 240 Hz/±16 g; gyro ±2000 dps; independent high-g 480 Hz/±320 g | Low-g tagged FIFO plus separate high-g status/data/range API; no implicit substitution |

| GNSS | Identity / factory → target baud | RAM target | Persistent policy |
|---|---|---|---|
| NEO-M8N | MON-VER model + PROTVER 18; 9600 → 115200 | CFG-RATE/MSG/NAV5/GNSS/PRT, 5 Hz portable | RAM only; no unverified CFG-CFG save |
| NEO-M9N | PROTVER 27; finite search including 38400/9600 → 921600 | Preserved 25 Hz airborne 4g baseline | Default RAM; explicit BBR/Flash compare/difference write/readback |
| MAX-M10S | PROTVER 34; 9600 → 115200 | VALGET/VALSET, 5 Hz portable | Default RAM; explicit BBR supported; Flash rejected |
| NEO-F10N | PROTVER 40; 38400 → 115200 | VALGET/VALSET, 5 Hz portable | Default RAM; explicit supported BBR/Flash compare/write/readback |

New UBX major constellation targets are GPS/Galileo/BeiDou. F10 has no GLONASS
key; individual signal-band settings remain unchanged and no L5-health override
is sent. Signal writes wait for ACK plus 0.5 s, including uncertain-ACK recovery.
Baud is changed last, followed by host switch and MON-VER/readback. A new NAV-PVT
is required for initial READY. Wrong model, NAK, checksum/length fault, timeout and
wrong readback do not become success. A lost ACK leads to readback, not repeated
NVM writes. Four-satellite valid PVT remains valid; accuracy units, ellipsoid/MSL
and NED-to-ENU signs are preserved.

`HardwareConfigRead` always starts a fresh read-only transaction and clears its
response mask. A mismatch retains the actual value and fails with zero repair
writes. `EffectiveConfigGet` copies the actual validated ledger. Explicit
`ConfigPersist` is separate; default `ConfigApply` reports `persisted=0`.

JY901B raw rail/near-rail, time continuity and history flags do not rewrite data.
Its effective ±16 g/±2000 dps range is used after readback. Default startup reads
before and after RAM differences and sends **zero SAVE commands**. Explicit
maintenance Save remains separate and is not claimed independently NVM verified.

## Evidence

Detailed logs and commands are below `tests/joint_rework_20260927/sensors/`.
They execute actual C code with simulated I/O. Host execution is not hardware
timing validation; linked target memory and stack acceptance belongs to the
parent build matrix.

| Evidence | Result |
|---|---|
| `pytest_sensor_fixtures_final.log` | 69 passed with permanent exported fixtures: real register/UBX/Sync400 mocks, 26 interface source graphs, strict ARM compile, source qualification, bindings/fingerprints and JY quality |
| `ubx_adapter_run.log` | Four models: fresh queries, actual response evidence, mismatch/timeout without writes, ownership rejection, explicit persistence and repeat zero writes |
| `jy901b_device_ram_run.txt` | 50 checks, zero failures, default SAVE count zero |
| `jy901b_adapter_ram_run.txt` | 28 checks, zero failures |
| `jy901b_multi_instance_ram_run.txt` | 27 checks, zero failures after RAM-only change |
| `neo_m9n_run.txt` | 566 checks, zero failures in actual existing M9 driver |
| `power10_sync_final.log` | Unmodified Power of Ten checker: 2,897 checks, 66 C files, 1,106 functions; pass |
| `sensor_abi_sync_sizes.log` | ARM EABI: SystemImuSample 80 B, SensorImu 112 B, SensorImuAdapter 256 B, UbxReceiverReadback 24 B, UbxReceiver 792 B, UbxSystemAdapter 920 B |

SystemImuSample remains 80 bytes: quality flags consume previous padding, so
existing per-sample queue storage does not grow. New contexts are selected-only.
No queue, stack or RAM budget was increased to force acceptance. New hardware
stays unverified even when its source graph and Host checks pass.

The final combined matrix (`pytest_sensor_fixtures_final.log`) passed **69 tests**:
39 sensor-library checks and 30 generation/contract checks, including all
21 raw IMU interfaces, two BMI088 Sync400 interfaces and three new GNSS models.
Each generated case resolves its actual selected source graph, typed bus/GPIO
bindings, generated resource/instance code and strict ARM compiler inputs.
New GNSS cases retain the complete Reference navigation selection and real KF6
parameters; their 115200 IOC and UART init C are changed consistently only in
the independent tests-directory CubeMX fixture. Original reference firmware and
Board payload remain unchanged. `pytest_sync_final2.log` additionally verifies
that a later wrong feature readback clears verification and latches FAULT.
Exact final repository-wide results belong in VALIDATION.md.

## Official sources and licenses

Acquired/rechecked 2026-09-27. Downloaded file SHA-256 values, URLs and source
commits were recorded in the former FCCG `tests/joint_rework_20260927/sensors/vendor_reference/sources.json` workspace; that historical scratch file is not part of this monorepo baseline.
Production driver logic is first-party implementation. The exact Bosch 6144-byte
synchronization image is copied as const data with its BSD-3-Clause copyright and
complete license retained in the production SensorBus payload. Other vendor
reference source stays isolated below the test directory and outside the graph. No GPL implementation was used. Vendor technical
documents are copyrighted reference material, not source-code licenses.

| Model | Actual official reference / pinned revision | Scope / license |
|---|---|---|
| MPU6000/6050 | [MPU-6000/6050 register map](https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map1.pdf), Rev 4.2 | Registers, scales, FIFO, reset; document reference |
| MPU6500 | [MPU-6500 register map](https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6500-Register-Map2.pdf), Rev 2.1 | Model-specific ID, FIFO and temperature; document reference |
| MPU9250 | [RM-MPU-9250A-00](https://invensense.tdk.com/wp-content/uploads/2017/11/RM-MPU-9250A-00-v1.6.pdf), Rev 1.6 | Six-axis register/FIFO path; document reference |
| BMI088 | [Bosch BMI08x SensorAPI](https://github.com/boschsensortec/BMI08x_SensorAPI/tree/c1ed227e7bb7da1fa600bbd4e5c82d0da1eb416a), `c1ed227e7bb7da1fa600bbd4e5c82d0da1eb416a` | BSD-3-Clause reference. Official synchronization API supports 400/1000/2000 Hz; the new Sync400 plugins implement the 400 Hz mode; raw200 remains unqualified |
| BMI323 | [Bosch BMI323 SensorAPI](https://github.com/boschsensortec/BMI323_SensorAPI/tree/b3033e78bc6e2c2e473f24e6d79afef0e16c4655), `b3033e78bc6e2c2e473f24e6d79afef0e16c4655`; BST-BMI323-DS000 | BSD-3-Clause reference; word transport, feature preparation and FIFO layout |
| ICM-42605 | [Official product documentation](https://www.invensense.tdk.com/en-us/products/inertial-sensors/icm-42605), DS-000292 v1.7 listing / available v1.6 register text | Document reference. Failed download is named `ICM42605_download_failed.html`; it is not represented as an acquired PDF |
| ICM-42688-P | [DS-000347 v1.5](https://invensense.tdk.com/wp-content/uploads/2021/06/DS-000347-ICM-42688-P-v1.5.pdf) | Document reference; distinct ID/profile and FIFO |
| ICM-45686 | [TDK official driver](https://github.com/tdk-invn-oss/motion.mcu.icm45686.driver/tree/0a5bed6975b5cdeecb98f95db420f3058dd88547), `0a5bed6975b5cdeecb98f95db420f3058dd88547`; DS-000577 and AN-000364 | BSD-3-Clause reference; model-specific reset/indirect-register/FIFO procedures |
| LSM6DSV32X | [ST driver](https://github.com/STMicroelectronics/lsm6dsv32x-pid/tree/ba78ab6cf58e8d58ca287dc5784935de40d08f5c), `ba78ab6cf58e8d58ca287dc5784935de40d08f5c` | BSD-3-Clause reference |
| LSM6DSV320X | [ST driver](https://github.com/STMicroelectronics/lsm6dsv320x-pid/tree/7fdcb10d2fe2195635413c95b4a2fb59642c466b), `7fdcb10d2fe2195635413c95b4a2fb59642c466b` | BSD-3-Clause reference; separate high-g registers |
| NEO-M8N | u-blox 8/M8 receiver description / UBX-13003221 | Legacy CFG protocol document reference; no vendor parser copied |
| NEO-M9N | M9 plugin and u-blox M9 PROTVER 27 VALGET/VALSET description | Preserved implementation plus actual driver Host regression |
| MAX-M10S | [UBX-21035062 R03 / SPG 5.10](https://content.u-blox.com/sites/default/files/u-blox-M10-SPG-5.10_InterfaceDescription_UBX-21035062.pdf), §4.9.21; [UBX-20053088 integration manual](https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf) | Constellation keys, UART/rate/PVT, supported layers, ACK + 0.5 s restart wait |
| NEO-F10N | [UBX-23002975 R02 / SPG 6.00](https://content.u-blox.com/sites/default/files/documents/u-blox-F10-SPG-6.00_InterfaceDescription_UBX-23002975.pdf), §4.9.20; UBXDOC-963802114-12193 integration manual | Local PDF SHA recorded; no unsupported GLONASS key or signal-health override |

## Next physical validation

Start with JY901B + NEO-M9N, RAM-only default startup and physical outputs disabled
for the bench. Read back actual rate/ranges/baud, inspect clipping and generation,
verify sample/receive-time continuity and START admission, and measure task time,
queue HWM, I/O latency and logger behavior. New-model bench work must also measure
FIFO fill/overflow, DRDY latency, SI/temperature conversion and selected profile
timing. BMI088 navigation requires the implemented Sync400 profile with its declared
INT3(G)-INT1(A) wiring and INT2(A) synchronized-ready connection physically verified. **NOT_FIELD_VALIDATED** remains the final hardware status.

## Per-interface source and maturity inventory

Each row refers to the selected physical plugin. Shared bus/protocol sources are ordinary resolved dependencies. Every listed interface passed actual generated-graph ARM object compilation as well as its Host/adapter checks; final matrix evidence is above.

| Model / interface | Exact plugin source package | DRDY / FIFO | Readback / persistence | Maturity |
|---|---|---|---|---|
| BMI088 / I2C | [`silverstar_device_imu_bmi088`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_bmi088/payload/Devices/IMU/BMI088/Src/bmi088_device.c) | status polling; independent raw FIFOs | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED; RAW_ONLY (use separate Sync400 for synchronized navigation) |
| BMI088 / SPI | [`silverstar_device_imu_bmi088_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_bmi088/payload/Devices/IMU/BMI088_SPI/Src/bmi088_spi_device.c) | CS + IRQ notification; independent raw FIFOs | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED; RAW_ONLY (use separate Sync400 for synchronized navigation) |
| BMI323 / I2C | [`silverstar_device_imu_bmi323`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_bmi323/payload/Devices/IMU/BMI323/Src/bmi323_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| BMI323 / SPI | [`silverstar_device_imu_bmi323_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_bmi323/payload/Devices/IMU/BMI323_SPI/Src/bmi323_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM42605 / I2C | [`silverstar_device_imu_icm42605`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm42605/payload/Devices/IMU/ICM42605/Src/icm42605_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM42605 / SPI | [`silverstar_device_imu_icm42605_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm42605/payload/Devices/IMU/ICM42605_SPI/Src/icm42605_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM42688P / I2C | [`silverstar_device_imu_icm42688p`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm42688p/payload/Devices/IMU/ICM42688P/Src/icm42688p_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM42688P / SPI | [`silverstar_device_imu_icm42688p_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm42688p/payload/Devices/IMU/ICM42688P_SPI/Src/icm42688p_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM45686 / I2C | [`silverstar_device_imu_icm45686`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm45686/payload/Devices/IMU/ICM45686/Src/icm45686_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| ICM45686 / SPI | [`silverstar_device_imu_icm45686_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_icm45686/payload/Devices/IMU/ICM45686_SPI/Src/icm45686_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| LSM6DSV320X / I2C | [`silverstar_device_imu_lsm6dsv320x`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_lsm6dsv320x/payload/Devices/IMU/LSM6DSV320X/Src/lsm6dsv320x_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| LSM6DSV320X / SPI | [`silverstar_device_imu_lsm6dsv320x_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_lsm6dsv320x/payload/Devices/IMU/LSM6DSV320X_SPI/Src/lsm6dsv320x_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| LSM6DSV32X / I2C | [`silverstar_device_imu_lsm6dsv32x`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_lsm6dsv32x/payload/Devices/IMU/LSM6DSV32X/Src/lsm6dsv32x_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| LSM6DSV32X / SPI | [`silverstar_device_imu_lsm6dsv32x_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_lsm6dsv32x/payload/Devices/IMU/LSM6DSV32X_SPI/Src/lsm6dsv32x_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU6000 / I2C | [`silverstar_device_imu_mpu6000`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu6000/payload/Devices/IMU/MPU6000/Src/mpu6000_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU6000 / SPI | [`silverstar_device_imu_mpu6000_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu6000/payload/Devices/IMU/MPU6000_SPI/Src/mpu6000_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU6050 / I2C | [`silverstar_device_imu_mpu6050`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu6050/payload/Devices/IMU/MPU6050/Src/mpu6050_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU6500 / I2C | [`silverstar_device_imu_mpu6500`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu6500/payload/Devices/IMU/MPU6500/Src/mpu6500_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU6500 / SPI | [`silverstar_device_imu_mpu6500_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu6500/payload/Devices/IMU/MPU6500_SPI/Src/mpu6500_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU9250 / I2C | [`silverstar_device_imu_mpu9250`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu9250/payload/Devices/IMU/MPU9250/Src/mpu9250_device.c) | status polling; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MPU9250 / SPI | [`silverstar_device_imu_mpu9250_spi`](../../apps/FCCG/plugins/builtin/silverstar_device_imu_mpu9250/payload/Devices/IMU/MPU9250_SPI/Src/mpu9250_spi_device.c) | CS + IRQ notification; actual model FIFO | Masked register readback; volatile only | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| NEO_M8N / UART | [`silverstar_device_gnss_neo_m8n`](../../apps/FCCG/plugins/builtin/silverstar_device_gnss_neo_m8n/payload/Devices/GNSS/NEO_M8N/Src/neo_m8n_instance.c) | PVT iTOW; bounded byte parser | Actual response ledger; RAM default; M8 NVM unsupported | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| MAX_M10S / UART | [`silverstar_device_gnss_max_m10s`](../../apps/FCCG/plugins/builtin/silverstar_device_gnss_max_m10s/payload/Devices/GNSS/MAX_M10S/Src/max_m10s_instance.c) | PVT iTOW; bounded byte parser | Actual response ledger; RAM default; explicit BBR | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| NEO_F10N / UART | [`silverstar_device_gnss_neo_f10n`](../../apps/FCCG/plugins/builtin/silverstar_device_gnss_neo_f10n/payload/Devices/GNSS/NEO_F10N/Src/neo_f10n_instance.c) | PVT iTOW; bounded byte parser | Actual response ledger; RAM default; explicit BBR/Flash | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |

## BMI088 Sync400 closeout

The two additional plugins are `silverstar.device.imu.bmi088_sync400` and
`silverstar.device.imu.bmi088_sync400_spi`. They declare only the documented
400 Hz mode: accel 400 Hz normal/±24 g, gyro 400 Hz/47 Hz bandwidth/±2000 dps.
The independent raw FIFO mode is not used for synchronized navigation.

Both require distinct MCU IRQ resources with exact IOC net labels
`BMI088_G_INT3_A_INT1_SYNC_NET` and `BMI088_A_INT2_SYNC_READY`. These labels
declare the external gyro INT3→accel INT1 connection and accel INT2 ready line;
they are not proof of real wiring. Missing/wrong labels produce ordinary resource
contract errors, and constrained-label changes invalidate binding and manual
confirmation fingerprints. Ordinary display labels remain excluded. Runtime
requires gyro-input then synchronized-ready notifications; missing, repeated,
late or reversed pairs cannot produce READY.

The driver resets both dies, disables APS with 450 us wait, loads 192 bounded
32-byte blocks, enables the image, waits 150 ms, reads ASIC status, sets and
reads feature mode 1, then reads back every range/ODR/interrupt register. Reads
use official synchronized accel GP0/GP4 plus gyro registers. A second gyro read
and post-read IRQ check reject torn/cross-epoch pairs; a processing guard rejects
reentry. No new software queue is allocated. Late/missing epochs set time error
and history reset; consumption timestamps remain `TIME_UNCERTAIN`.

Source: Bosch BMI08x SensorAPI commit
`c1ed227e7bb7da1fa600bbd4e5c82d0da1eb416a`, `bmi08xa.c` v1.9.0.
Exact image size: **6144 bytes const Flash data**; SHA-256:
`996efc7079e75bc0b93f302f520e8a3bfa74c147b0a28fd6a2306d74a690fe88`.
The full BSD-3-Clause license is `Devices/SensorBus/BMI088_SYNC_LICENSE.txt`;
`bmi088_sync_image.inc` carries the original 2024 Bosch copyright. The importer
retains these complete workspace-owned packages through their declared
`fccg_joint_sensor_library` ownership, including image and license.

ARM ABI after Sync400: **SystemImuSample 80 B; SensorImu 112 B; adapter 256 B**,
unchanged from the pre-sync state. The new reentry byte uses existing padding;
configuration index and pending-pair time reuse existing per-model scratch space.
The strict ARM O2 driver object is **7325 bytes text/const, 0 data, 0 BSS**
(`sync_release_size.log`), including the 6144-byte image. This is object-level
cost, not a substituted linked-application memory result. Physical sample rate is 400 Hz, without inserted samples;
the existing production two-sample inertial path owns BODY production.

`pytest_sync3.log`: actual C I2C/SPI image/reset/readback/IRQ/order/gap/reentry/
cross-epoch/stall/error mocks and both real generated ARM graphs passed.
`pytest_sync5.log`: binding/fingerprint, same-source qualification, exact official
image/license and two generated interfaces passed. `power10_sync_final.log`: original
checker passed **2897 checks / 66 C files / 1106 functions**.

| Profile | Source | Generation / qualification | Maturity |
|---|---|---|---|
| BMI088 Sync400 I2C | `Devices/IMU/BMI088_SYNC400`, shared `sensor_bmi088_sync.c` | dual I2C addresses + both declared sync IRQ nets required; software qualified only as its actual selected source | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |
| BMI088 Sync400 SPI | `Devices/IMU/BMI088_SYNC400_SPI`, same shared driver/image | dual CS/dummy transport + both declared sync IRQ nets required | MOCK_VALIDATED / COMPILE_VALIDATED / HARDWARE_UNVERIFIED |

The production raw-to-BODY cadence is independently exercised by
`tests/test_eskf_body_cadence.py` (`tests/joint_rework_20260927/body_cadence400_retry.log`): 801 raw
samples with alternating 2/3 ms receive proxies produce 400 BODY increments
in 2 s, 200 Hz BODY, and 120/192 history occupancy at 600 ms. There is no history
overflow or inserted sample; stationary position/velocity remain near zero,
and `TIME_UNCERTAIN` survives the actual production correction/pairing path.

Permanent C test authority is `tests/fixtures/sensors/` (seven test sources, plus
the pinned Bosch image-source/license reference). Source-package exports retain
these fixtures; tests no longer depend on the excluded acceptance-output tree.
Historical logs and original executed C evidence remain below
`tests/joint_rework_20260927/sensors/`.

Final changed Python checks: `ruff_sync_final.log` passes E4/E7/E9/F/I;
`compileall_sync_final.log` exits 0. These checks include the generic GPIO
SET/RESET and push-pull/open-drain token fixes, pin-label constraint and
constrained-label fingerprint code. No warning or acceptance threshold was relaxed.
