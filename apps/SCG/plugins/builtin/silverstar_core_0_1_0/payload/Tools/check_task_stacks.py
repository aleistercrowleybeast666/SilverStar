"""Conservative, reproducible stack budgets from GCC .su and the linked Arm ELF.

No LTO is used by the generated Make project. Inline frames are already in .su.
All direct calls and cross-function branches are conservatively nested, including
tail calls (overestimates). Linked library frames without .su use the sum of all
constant stack decrements/pushes in disassembly, also an overestimate. Unknown
indirect calls, dynamic frames, recursion and unaccounted SP writes fail closed.
This is a worst-known static budget, not a hardware high-water measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

TASKS = {
    "Device": ("AppTask_Device", "s_device_stack"),
    "INS": ("AppTask_Ins", "s_ins_stack"),
    "Estimator": ("AppTask_Estimator", "s_estimator_stack"),
    "Flight": ("AppTask_Flight", "s_flight_stack"),
    "Logger": ("AppTask_Logger", "s_logger_stack"),
    "Serial": ("AppTask_Serial", "s_serial_stack"),
    "Telemetry": ("AppTask_Telemetry", "s_telemetry_stack"),
    "Idle": ("prvIdleTask", "s_idle_task_stack"),
}
# FatFs diskio.c calls the single CubeMX SD_Driver table. Verify this binding
# below before adding the edges; no arbitrary plugin callback is assumed safe.
DISK_CALLBACKS = {
    "disk_initialize": "SD_initialize", "disk_status": "SD_status",
    "disk_read": "SD_read", "disk_write": "SD_write", "disk_ioctl": "SD_ioctl",
}
STARTUP_CALLBACK_SOURCES = (
    "Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c",
    "Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c",
)
# Cortex-M4F: hardware core + FP exception frame (104), software r4-r11/lr
# and s16-s31 (100), worst alignment padding (4), rounded up to 256 bytes.
# Nested ISR frames use MSP, whose separate linker reservation is audited too.
CONTEXT_BYTES = 256
MIN_MARGIN_BYTES = 256


def Command_Read(command: list[str], root: Path) -> str:
    return subprocess.run(command, cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="strict").stdout


def RegisterBytes_Get(registers: str, width: int) -> int:
    total = 0
    for item in registers.strip("{}").split(","):
        item = item.strip()
        if "-" in item:
            first, last = item.split("-")
            total += int(re.search(r"\d+", last)[0]) - int(re.search(r"\d+", first)[0]) + 1
        elif item:
            total += 1
    return total * width


def FunctionBody_Get(source: str, name: str) -> str:
    """Canonical reviewed binding body; comments/formatting earn no exception."""
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", source)
    if match is None:
        raise ValueError("Missing callback binding body: " + name)
    depth = 1
    for end in range(match.end(), len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return re.sub(r"\s+", "", source[match.start():end + 1])
    raise ValueError("Unclosed callback binding body: " + name)


def MpuCallbackBindings_Resolve(root, sources, instructions, edges, indirect, nm, prefix, elf):
    """Resolve a reviewed immutable MPU profile and its concrete I2C bus.

    Source body fingerprints preserve the reviewed provenance, not merely
    function names. The selected graph, actual linked read-only profile bytes,
    profile getter literal and direct initialization callers must agree. Any
    extra indirect instruction, caller or changed binding requires review.
    """
    optional = {"SensorImu_Verify", "SensorImu_ProcessConfigure", "SensorImu_Read"}
    if not optional.intersection(indirect):
        return []
    project = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf-8"))
    imus = {device["plugin"] for device in project["components"]["devices"]
            if device["plugin"].startswith("silverstar.device.imu.")}
    if imus != {"silverstar.device.imu.mpu6050"}:
        raise ValueError("Unreviewed SensorImu selected profile binding")
    imu = "Devices/SensorBus/Src/sensor_imu.c"
    bus = "Devices/SensorBus/Src/sensor_register_bus.c"
    adapter = "Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c"
    instance = "Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c"
    profile = "Devices/IMU/MPU6050/Src/mpu6050_device.c"
    # Each body was reviewed as part of the binding proof. They establish
    # immutable profile assignment and read/write targets, and guarded optional
    # calls. This deliberately fails after a semantic change until re-reviewed.
    reviewed = {
        imu: {
            "SensorImu_Init": "da3bd34fc08e65fb32e5a72b68f60a0f2a08eafd2c630a92914621c949878453",
            "SensorImu_Verify": "8b6786ccf36eec5eddabb1878139eb463d345eefa88a573e34c7ddf8bf7a3a04",
            "SensorImu_ProcessConfigure": "6eb4ee07a620e1c9a2ea532046a25bd3f1c4595ac90461fd9e17f76e02dd71d2",
            "SensorImu_Read": "f97d205c95377a02e4d1a4283d7018688f67caef15d10942bb5bd8aa7843c579",
        },
        bus: {
            "SensorRegister_Read": "29b0b73fcbc3f3f3d248d790bab51870a564852c4eec5a4b1d265be19af3f971",
            "SensorRegister_Write": "b08b754cf52dc6558f9d3af40ea3db36a09331df7774ba3a96987f62bfd82929",
        },
        adapter: {
            "SensorImuAdapter_PrepareI2c": "652772579357ed30ad767d5d49a6888a691e30ea07b5addd7f12a89b76b4c1a4",
        },
        instance: {
            "Mpu6050ImuInstance_Init": "4776cec45657cafb0e67926917d05f1cf0b553fbe650ef81fbfcf0b0b322c614",
        },
    }
    proofs = []
    for path, bodies in reviewed.items():
        if path not in sources:
            raise ValueError("Missing selected callback binding source: " + path)
        text = (root / path).read_text(encoding="utf-8")
        for name, expected in bodies.items():
            actual = hashlib.sha256(FunctionBody_Get(text, name).encode()).hexdigest()
            if actual != expected:
                raise ValueError("Changed reviewed callback binding body: " + name)
        proofs.append({"source": path, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    if profile not in sources:
        raise ValueError("Missing selected MPU profile source")
    text = (root / profile).read_text(encoding="utf-8")
    if FunctionBody_Get(text, "Mpu6050_ProfileGet") != "Mpu6050_ProfileGet(void){return&s_profile;}":
        raise ValueError("Changed immutable MPU profile getter")
    table = re.search(r"static\s+const\s+SensorImuProfile\s+s_profile\s*=\s*\{(.*?)\n};", text, re.DOTALL)
    if table is None or re.search(r"\.(prepare|frame_read|extra_verify)\s*=", table[1]):
        raise ValueError("Unreviewed MPU optional profile callbacks")
    # ARM AAPCS32 layout: five byte fields follow the name pointer, then float,
    # then the three callbacks at 16/20/24. Reject a changed prefix/type layout.
    header = re.sub(r"/\*.*?\*/", "", (root / "Devices/SensorBus/Inc/sensor_imu.h").read_text(encoding="utf-8"), flags=re.DOTALL)
    layout = ("constchar*name;uint8_tregister_width;uint8_ti2c_dummy_bytes;"
              "uint8_tauxiliary_address_7bit;uint8_tspi_dummy_bytes;"
              "uint8_tauxiliary_spi_dummy_bytes;floataccel_full_scale_g;"
              "SensorImuPrepareprepare;SensorImuFrameReadframe_read;SensorImuExtraVerifyextra_verify;")
    if layout not in re.sub(r"\s+", "", header):
        raise ValueError("Changed MPU profile callback layout")
    symbols = [parts for line in nm.splitlines() if len(parts := line.split()) == 4 and parts[3] == "s_profile"]
    if len(symbols) != 1 or symbols[0][2].lower() != "r" or int(symbols[0][1], 16) < 28:
        raise ValueError("MPU profile is not one linked read-only object")
    address = int(symbols[0][0], 16)
    data = Command_Read([prefix + "objdump", "-s", "--start-address=" + hex(address),
                         "--stop-address=" + hex(address + 28), str(elf)], root)
    if "file format elf32-littlearm" not in data:
        raise ValueError("Unreviewed MPU profile ELF ABI")
    bytes_by_address = {}
    for line in data.splitlines():
        if match := re.match(r"\s*([0-9a-f]+)\s+((?:[0-9a-f]{8}\s*){1,4})", line):
            start = int(match[1], 16)
            for offset, byte in enumerate(bytes.fromhex(match[2])):
                bytes_by_address[start + offset] = byte
    if any(bytes_by_address.get(address + offset) != 0 for offset in range(16, 28)):
        raise ValueError("Linked MPU optional callbacks are not NULL")
    getter_words = {int(args, 16) for op, args in instructions.get("Mpu6050_ProfileGet", []) if op == ".word"}
    if address not in getter_words:
        raise ValueError("Linked MPU getter does not bind the reviewed profile")
    init_callers = {name for name, calls in edges.items() if "SensorImu_Init" in calls}
    prepare_callers = {name for name, calls in edges.items() if "SensorImuAdapter_PrepareI2c" in calls}
    if init_callers != {"SensorImuAdapter_PrepareI2c"} or prepare_callers != {"Mpu6050ImuInstance_Init"}:
        raise ValueError("Unreviewed linked SensorImu initialization provenance")
    resolved = {"SensorRegister_Read": "SensorImuAdapter_ReadRegister",
                "SensorRegister_Write": "SensorImuAdapter_WriteRegister"}
    for name in optional | set(resolved):
        if name not in indirect:
            continue
        calls = [op for op, args in instructions[name]
                 if (op == "blx" and "<" not in args) or (op.startswith("bx") and args.strip() != "lr")]
        if len(calls) != 1:
            raise ValueError("Extra indirect MPU callback instruction: " + name)
        if name in resolved:
            callee = resolved[name]
            if callee not in instructions:
                raise ValueError("Missing concrete MPU register callback: " + callee)
            edges[name].add(callee)
        indirect.remove(name)
    for path in ("Devices/SensorBus/Inc/sensor_imu.h", "Devices/SensorBus/Inc/sensor_register_bus.h", "Devices/SensorBus/Adapter/Inc/sensor_imu_adapter.h"):
        BindingHeader_Verify(root, path)
    return [{"kind": "immutable_mpu6050_i2c", "profile_address": hex(address),
             "null_callbacks": ["prepare", "frame_read", "extra_verify"],
             "bus_edges": resolved, "reviewed_sources": proofs}]


# Reviewed binding contract v2 freezes all selected translation units and
# GCC-reported transitive project inputs of three recorded builds. This closes
# writes through other sources/macros without pretending to analyze C aliases.
# Unknown versions or compiler shapes require explicit evidence and re-review.
BINDING_SOURCE_V2 = {'APP/Inc/app_task_config.h': ['1ac3a475161ffe967c1c88c22cf5052f575683089b93eb55a66d5b849e58a4c5'],
 'APP/Inc/app_tasks.h': ['69b84ed60fe560f9ce6c3add42e78e549fe38522638e132924956d45c9b2a164'],
 'APP/Inc/device_native_log.h': ['e8d219737f36906678c846888a38f9c7ad314455773319c9ca0468f1598663f1'],
 'APP/Inc/diagnostic_log.h': ['28e45d3fc50a1a507ca897cbbe4d7f660cb00eee090309a6a63908b3d8ed924f'],
 'APP/Inc/estimator_barometer_pending.h': ['1e15d3cffeb4f5648df11285b8aba3698602ef7b34289c78888b46df60e7f734'],
 'APP/Inc/estimator_bus.h': ['6399fe13f11aad094de3d8ea62499a6ed3041b54350564edf48eccac8bb78147'],
 'APP/Inc/estimator_task.h': ['e8e75aa6f4e47a839e517caebc4d6c9505eeac915a3a049239e6ef00c765ddd1'],
 'APP/Inc/imu_sample_bus.h': ['2a88c1167b91d28173f21a32db028c10d75684f164a6d5f6bd30bcd2ce714faa'],
 'APP/Inc/ins_task.h': ['10e6353ca21f2903b96acc29824f182cd22596ce32730f2a52ddc79c8a56d38b'],
 'APP/Inc/logger_bus.h': ['608975eef353579ad65f8cd265dda883f57e54701f50255786dd2a69934e98ac'],
 'APP/Inc/logger_task.h': ['d4b91c842ae6aa5c639fed04cb0d527ebbac51094f0b9f4ce3383dc21af42fdc'],
 'APP/Inc/serial_task.h': ['d722b804bbf2425cc90556d0b22ec79b1d4ca922c7768a6e2fe07982675c6492'],
 'APP/Src/app_tasks.c': ['0ca986bb443e97a336d736c0ca9ed5f4ea0beb9f8c7c0aff0c92f15c20df8b7c'],
 'APP/Src/device_native_log.c': ['4eeb3ad42a0579ec98ba3a1f0008cf40ba4058e397009f059437b74f806b4253'],
 'APP/Src/device_task.c': ['e109b2438356617928bf307c67f341efa8b46db2d32e8a5d829ec4d38a570f76'],
 'APP/Src/diagnostic_log.c': ['0e47a0a5ab736f66e5b0566f37839015bf33060ea3781be05757618dedb4483d'],
 'APP/Src/estimator_barometer_pending.c': ['ffa6068a12158921f031cd2d33abf40977d46bb194110d23472b696ca9e4673b'],
 'APP/Src/estimator_bus.c': ['4e0e22def926dd3d4d3c20b7be0c761571093cefcb7b6cbfb40857ebe8f48e0e'],
 'APP/Src/estimator_task.c': ['71584a5e992f30da63372c487c5f29925fc9cbd5ef10176f6186408fdcc5de47'],
 'APP/Src/flight_task.c': ['bc922be48f1d09415f8d5a5cd09552e750603bc1381b714784337f4e85a59d79'],
 'APP/Src/imu_sample_bus.c': ['a401cd784468cfe647aa825548a6cc60f3ed6c7bdb4fcc30e6fce5a756a943f3'],
 'APP/Src/ins_task.c': ['30bec977ea226e4c3adc3be09e66e303f04ab7f0ebf2133fadd9024018259f5e'],
 'APP/Src/logger_bus.c': ['c7f63361c7c815a79eb14ca6c25ab8eb57b06180f9761f21f9f77cee198838cd'],
 'APP/Src/logger_task.c': ['e7067b8a1e3d5bc58667107a928fd78138462b10391faa65c9d5f1fd186e5a32'],
 'APP/Src/serial_task.c': ['e81449873dbd9361db473c0d3ab7f8738e453ff55374abfa69e91162fd3a7eca'],
 'APP/Src/telemetry_task.c': ['682f91918892f7970bb86ff332dfcb301c55f82acfce62eff8bee96a87bd985b'],
 'Algorithm/Alignment/Common/Inc/alignment_strategy_types.h': ['ba1e47e581143eaea900020b64f5cf2fcbb14c4492a485cc46ca3a322d906d89'],
 'Algorithm/Alignment/Common/Inc/attitude_alignment.h': ['54dee12bb2e88c05afdf0fcf353c676d332c3b472453ed25db746e91bc42dc45'],
 'Algorithm/Alignment/Common/Inc/attitude_preflight.h': ['12c32075d7068807159317661730dc1696efa33bdf11720d91006224c3d75aca'],
 'Algorithm/Alignment/Common/Inc/vector_constraints.h': ['49c0d039e271620102ff0e9ce67ce0344580ed33882e2408d6ea17bb50401ae4'],
 'Algorithm/Alignment/Common/Src/attitude_alignment.c': ['cbe0d694c23c3e637941fe4b76a1741cd98522a13ad480deb780a728087a76d6'],
 'Algorithm/Alignment/Common/Src/attitude_preflight.c': ['720055bfd1dced68e98a8a62f47b56dd7597af003665b8483b42747cad43f7de'],
 'Algorithm/Alignment/Common/Src/vector_constraints.c': ['b510a1e8c38c691f2aed83e7e0fa00f9893554c0f8f9dafa00c2cd92e5f298c5'],
 'Algorithm/Alignment/VectorConstraints/Inc/alignment_strategy_binding.h': ['23ad9e903906c554da66502b0129b87dae432e302362ccb9d4bfff664772cde2'],
 'Algorithm/Alignment/VectorConstraints/Src/alignment_strategy_binding.c': ['229de0e5621d078d68568d76e3cb7a4537ca85d2675bb1e78559d806febf4207'],
 'Algorithm/Calibration/Inc/imu_six_face_calibration.h': ['198c92e3983b7e6e171fd613cdd3c3549628e9c9dad9049510568b20f5e11385'],
 'Algorithm/Calibration/Src/imu_six_face_calibration.c': ['db9ba934f47189c4ee1cb2df6a627d1f9dde8a2d0ad9a7174b70f546320b5f88'],
 'Algorithm/Common/Inc/attitude_frame.h': ['35b9747126686a19dab2a7e08237ecd874aae86b13bf233cf102d5e25a172567'],
 'Algorithm/Common/Inc/geodesy_local.h': ['7cdc83f368f0705279952ec05bc383fc859111282e1211ffa0011dfa883ff88c'],
 'Algorithm/Common/Inc/navigation_quality.h': ['3f85c7df8aff1518ab4899a8951dd70560e82d9c22c13bf9a5fcb104b8596492'],
 'Algorithm/Common/Src/attitude_frame.c': ['407ae1bc41a066ca7c3525c989ab970d662cf460876a0847a0295b7b7dd068db'],
 'Algorithm/Common/Src/geodesy_local.c': ['c03752abccf645633fa94e5b407010350685c9da378d44c397ec6491457fbb89'],
 'Algorithm/Common/Src/navigation_quality.c': ['dccb743060f47abd5cbbf56cc95409f984431607caffa86534cf53e7c0a98869'],
 'Algorithm/Estimator/KF6/Inc/navigation_integrity.h': ['408089a07f29dc633dd0b33187c3d8b97a7e2cb69e7b3675640ad2c4e7af8969'],
 'Algorithm/Estimator/KF6/Inc/navigation_kf.h': ['85d1e97fb94e60dfbfe74afc3131b32a3b4ebfb3a817b9b30bee957b8451f7cd'],
 'Algorithm/Estimator/KF6/Inc/navigation_kf_replay.h': ['48b53731c86f049192609ebafe18cd9f9e8d0951a3960618ced333bdec11cab9'],
 'Algorithm/Estimator/KF6/Src/navigation_integrity.c': ['3c27a9e8ce2dc1e1b54a2ca44e19aae5c8dc7fa72a2e1ad6ba0538bd42288210'],
 'Algorithm/Estimator/KF6/Src/navigation_kf.c': ['168a5b04c394099afc255589217f33dd02884a83df0fd26dfb11c82168121f30'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['2c3cad41f361ee3ed0634461ac951dd8af12a25619d098b912941c0edb80ea84'],
 'Algorithm/Estimator/SF6/Inc/navigation_sf6.h': ['6bd1b7e848fddf43f3ad5d81628c02ad7c182636d3f5b9fe7e12268e3984b95f'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6.c': ['7f0fd56ea6c9b4b43432ef70d4762234a730328a724ba4c3f8db3e996e5ced12'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c': ['ee68b750ff222e00f6e552c7ac52fd965fdd47a4a869f95fe79a3a42236d10fc'],
 'Algorithm/INS/Coning2Sculling2/Inc/ins_mechanization.h': ['2a4fee215e350587e3c6a7bbb41034415331891677f6212bf62c7b8abebdbcee'],
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c': ['fde2c0ce70e8a48f5355a6cb70a6d99dac3d9e2ef9143e9402372633ab159e2e'],
 'Common/Inc/common_format.h': ['60703ab3b9b356d4bf5da2fb1524bbeed00269dcfc81e12ede18bb9f3f18b307'],
 'Common/Inc/common_ringbuf.h': ['0cc5f36b2929a400d761fa66b6a9f8c763273ddf1c39c6a070293eca6cef6fbf'],
 'Common/Inc/common_spsc_queue.h': ['c16044db87b42276b30d569744a311ff8dfde2ac2d13c37c5dea70e14b93d77c'],
 'Common/Inc/debug_log.h': ['f00d66160e1c1c52820502dc8ad12e0ec68b35b1336c0dcc3d24a1a4b24cb7d6'],
 'Common/Inc/silverstar_assert.h': ['e7dbcb7168f71bb13b5bb3c05b596d8388ba50884507f40ae764920525d47615'],
 'Common/Inc/silverstar_compiler.h': ['d9176d94ca250f5dbf257520163c51e773ad3345ce01705842b15349458d5f32'],
 'Common/Inc/silverstar_sensor_id.h': ['846a6a24e573c7d67690a5fade5e3b969241049aa0038914d6507dec6adef082'],
 'Common/Src/common_format.c': ['170b4a5d66afbe2e1f84ed46d4323955c0a8d64cfffe5e81ecc4f3502b59539c'],
 'Common/Src/common_ringbuf.c': ['9a0622c71f496afc47328c2c08a6112285d7c0111536ad85b28272f55a1d145d'],
 'Common/Src/common_spsc_queue.c': ['5ceb0431072956af77e3fd3c20d6332710447e81bcb37da176bf637591b6d25a'],
 'Common/Src/debug_log.c': ['7cddbe4bb94cc1c7387209f3fb18a9782365af02d6830c0c6b8020299495f960'],
 'Common/Src/silverstar_assert.c': ['f1ef7202ad760eac40737675b390f45a29582814b2c8b222afca044e2f0510d2'],
 'Core/Inc/adc.h': ['f4a398c623ab113e838e695dfd4d5ed9acce1b573101bbfbf993663f0151bc9f'],
 'Core/Inc/dma.h': ['f3190614531c4bd5af6cfcee9cc29aea0321863613eba43266dadb615e6f1036'],
 'Core/Inc/gpio.h': ['cd5a5f75903537cba4460073b40e3b0d18d4af6dd7522c5a0756f0b9261e03af'],
 'Core/Inc/main.h': ['4defcbc364c7791c92598119ac6b793e2e0f75e3d6ee4ee31a6d39eb6d728694'],
 'Core/Inc/sdio.h': ['296104874e74470045840e5752c6c451fe0c2ca469792d3a3e6e02c7e6b35dfc'],
 'Core/Inc/spi.h': ['fd689a3f7101cf17870b51472d997c4458b6544a2273a925a5b26cc0573af1ef'],
 'Core/Inc/stm32f4xx_hal_conf.h': ['132b5b6bd1ac5b82ae12f3e1b7a0d74be0e34a6fb4873bf58ca5bf3d6e10e030'],
 'Core/Inc/stm32f4xx_it.h': ['73712846b1945be8921798dec3c91ce8de7e0820803b78405e66badb4a2c01f6'],
 'Core/Inc/usart.h': ['ee156182918dcffe31197827a380e72817a35fba815c4ad3ae816a001a58ebea'],
 'Core/Src/adc.c': ['e91a96bc10a18e323e121c1fb9dbf77f6229186903d65289adc5d33ee38e8f84'],
 'Core/Src/dma.c': ['0e8241d12f0098a80dc410318614cfd8531aaef3b2f10a83a896728815e43450'],
 'Core/Src/gpio.c': ['396584df5faeb8e09750a5c0cb626d447ad3a99301d14635f832d469bda19f2d'],
 'Core/Src/main.c': ['b3cf33f0a654ee1b61ab5aca39db0b3cca146589462df1881ab11a7c684378de'],
 'Core/Src/sdio.c': ['82ac2cc2aeb4c96bc6a6ab3170e8dabc956090af5aeac5beaa7bd96d766668b1'],
 'Core/Src/spi.c': ['ec245f1f861e4139da9aa7a165fffb468b0672976906fadd5ea0293beb728d96'],
 'Core/Src/stm32f4xx_hal_msp.c': ['7c9760ddc78da41c87d36dd297c32dc879bebff03e0a2be0b24f9fc1cf023222'],
 'Core/Src/stm32f4xx_hal_timebase_tim.c': ['e4acc90e2c4bd89cc3e5eb8f8eacbfdc196b699d1bae2c5112540dd5df447e22'],
 'Core/Src/stm32f4xx_it.c': ['6524724019b90cb6b2bc2386755f99b4cf93815411b359d4cc8713d5ffb33be4'],
 'Core/Src/syscalls.c': ['03c06c72eafb44b499814cf9234aba57dd830f345d9b8779b5d7090e78517600'],
 'Core/Src/system_stm32f4xx.c': ['a31929eab936ac98db060c18917118acf79dc96e1f03ed4b57d614535dd06d70'],
 'Core/Src/usart.c': ['86b5946b448d909879510a1f4771444079e49064b525ecc77ae4962d94d40c0a'],
 'Devices/Barometer/BMP280/Adapter/Inc/bmp280_adapter.h': ['d10d61a11fed9d5866a8b16e98dc034aaba95d0eb4f35752f0f07bbd393e766c'],
 'Devices/Barometer/BMP280/Adapter/Inc/bmp280_instance.h': ['d844731753c5e564eaa0290e15ec0d12cf63da2d9d34ec5f94f62bc452f30f6c'],
 'Devices/Barometer/BMP280/Adapter/Src/bmp280_adapter.c': ['2ea6a2d9232a6a6288cc84ef775f34715e0c883550b534cd795f772f41770701'],
 'Devices/Barometer/BMP280/Adapter/Src/bmp280_i2c_instance.c': ['6494f067a7fa575dee7b7ff2ac3a18322a7c9a467b2000a71a1a6132036cceb2'],
 'Devices/Barometer/BMP280/Inc/bmp280_core.h': ['75bbe6dff891cb9dd663b5fc9e276ba68c29be1042dcd43e117161568ee87663'],
 'Devices/Barometer/BMP280/Src/bmp280_core.c': ['d339fec40280310c114edaddc705445182b00478df098af721f1747f8c566376'],
 'Devices/Console/UART/Adapter/Src/uart_console_adapter.c': ['7de0ecd65987c6ab158590307548eeb025bacab272dbfa91c564de36fc6dc452'],
 'Devices/Console/UART/Inc/console_uart_device.h': ['cb499989fdb9fcfb5bae87cc40ac59160062640cc6b9d9c5898a07024a6abfd7'],
 'Devices/Console/UART/Src/console_uart_device.c': ['b86f9c9f7352d6fe2086620f3225dddc17337ade56a880e566f5e4b6554dffa3'],
 'Devices/GNSS/NEO_M9N/Adapter/Inc/neo_m9n_instance.h': ['dda334314d42199b2c8401627891e2822f068aa6528078a3ef84ee2ecbec363e'],
 'Devices/GNSS/NEO_M9N/Adapter/Inc/neo_m9n_startup.h': ['a34bc46bb088f55778331b6e9693afd706e36852b5761bc20c5b9728151137f8'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c': ['9dc8906371177999914ecef0c2604ba06e3b3115462f305fe3dfc6e94871666b'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_system_adapter.c': ['e5eaeb4814b6abbf879f047153015c0cc75e1b4c9500c192b463b524bc60a6ba'],
 'Devices/GNSS/NEO_M9N/Inc/neo_m9n_build_capabilities.h': ['793b542715ea21596e985fda1c74585d391c76893c63d1889137a8d10d6492ac'],
 'Devices/GNSS/NEO_M9N/Inc/neo_m9n_config.h': ['15c6ec4f42ff903a99bd0501149a3ca7a508137773da335f0ed7ea5afb6c8e04'],
 'Devices/GNSS/NEO_M9N/Inc/neo_m9n_config_keys.h': ['c2a38087f7c8acfa9989884d7c6a9d4eccb15602c2f02ff03c139907aa917f65'],
 'Devices/GNSS/NEO_M9N/Inc/neo_m9n_device.h': ['9c6330cbe1a0dedbc7e8aba302b1f0ce51347876754126858441edeec4b07d0a'],
 'Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c': ['a0ddd9a4a8c4d3b8ead74b873a36a18b01d381065a0fcf8622f9c4ba0a126de2'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_barometer_build_capabilities.h': ['eaaef3e1b8b3a34163e2d217a984cdc1b9b877cebc6a59aa2c414458ab85952f'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_instance.h': ['db0b6676b83d80f7eb5fdf382736d704eea50efe563b2343974402c1d6b84bc0'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_magnetometer_build_capabilities.h': ['e29b04139eee3707b26377cf7ac508ffa9cdd435543613688edce376290488c9'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_magnetometer_config.h': ['c3e3e6223aef996f30bb15d34f888c10ae7c796ce69ffbed443d150476f54d61'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_sample_quality.h': ['082013b92d32722fcf2c263c9879b10b929cbcc9e996ed80ba2ba76620d3e768'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_sensor_adapter.h': ['972a2d95250eadb05a3d4a87c3366bb8ead1438b1fc758a321a7d27c55cdc40d'],
 'Devices/IMU/JY901B/Adapter/Inc/jy901b_startup.h': ['620d9f50f27bff5a2a3100b319df9844a5a85392cfdb33e1b6d23d98154023c1'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c': ['e8d6780ee213a6fd17bd4715835b194d0c6bf21aa977d257f29d70258a43a7cf'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c': ['183c71b43d036a8b18981e7a216ec77e56a7748b5b39f27ff9c581385cfead50'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c': ['e0176f486cfab7b2f8ad778fa16671545039ce8635f7bab20f1871e0ae808f30'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c': ['af8a19e53aa2a9288309487dd4f86612ea2feefd9aedae376fde7f92276e6d32'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c': ['da3ae46be9723782bc0816d0ebd313b5f807359c03e50baf3fca15aababd9e2e'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c': ['38ff40a9b7f491d4480b0bfe282ab42ce9161d0b880314ee9b9990260a75b4e6'],
 'Devices/IMU/JY901B/Inc/jy901b_config.h': ['887b4ca3f9737382b8412e085006339f90ed6ad0ce7fd07c2909136e9e05bf4a'],
 'Devices/IMU/JY901B/Inc/jy901b_device.h': ['5e95067a810393c81f2366f0fd1b0ebe16834debf276ddf08d467e8afda2dc16'],
 'Devices/IMU/JY901B/Inc/jy901b_imu_build_capabilities.h': ['fb7da40857bf2364e226f620bf975f77885e3a283841fe0b78aec29d64d0aec6'],
 'Devices/IMU/JY901B/Src/jy901b_device.c': ['9fddf8603a18a76fe3aec4b5f32122b30ad9ffbf4b812ae07fe98aba87f070b8'],
 'Devices/IMU/MPU6050/Adapter/Inc/mpu6050_instance.h': ['1cb8f6ff5c23c9f293201c86405205d635e1e75429c4e7ada3c9ab25a53d8fea'],
 'Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c': ['69028163a562a3d39b60bfdd017c4375897e7f17cc7d0371ce51b82b6d14fc27'],
 'Devices/IMU/MPU6050/Inc/mpu6050_device.h': ['14749feb341ac9da58f347daacbd09542642e3d73b8031477ab1e4ab38640dcd'],
 'Devices/IMU/MPU6050/Src/mpu6050_device.c': ['df5c31341ad973c6a4604217bdaa6abd0b925b0aa1029aacc70ab462b47170ab'],
 'Devices/Power/InputVoltage/Inc/adc_power_config.h': ['df6a9110e261cff24d63aa4a3c71973961f9f047631a5f9c2ac20f3c309d9f76'],
 'Devices/Power/InputVoltage/Src/power_service.c': ['d375930dbb1d1efe7d73640f3e1c9b90b6d862b36b92db39843bade31bc08e6c'],
 'Devices/SensorBus/Adapter/Inc/sensor_imu_adapter.h': ['112b6d603c070f5901c1574fad1c11d4166fe6e367ce380af3df55fbd0392253'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c': ['7960114a40c6103b21b497bfaa0881325121183c8d30fcd8cabe4c9380ca07a9'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_spi_adapter.c': ['45a6cda4fc329a954f4a0d067321df1e63bd1bb188d6f60437902fb2cf6ff782'],
 'Devices/SensorBus/Inc/sensor_bmi088_fifo.h': ['5288905e09a48cba6ab58de799bc80eb86ccaeee77c810a61dbcdc180054e9d1'],
 'Devices/SensorBus/Inc/sensor_bmi088_sync.h': ['fb43cfe41894a4e592a5e9fbb6e2ebb1cd86a093b3087d73c37552c326ae433f'],
 'Devices/SensorBus/Inc/sensor_imu.h': ['22ff44a7b987d7a8f184f02dbd87dfff90dc6e8149e075ee15cdd0d6fe9f8dbe'],
 'Devices/SensorBus/Inc/sensor_register_bus.h': ['9ea60d3ce1b36c932fe4e73d180cc1fd2bbba0f172639b4cbda4edea440f2e47'],
 'Devices/SensorBus/Src/bmi088_sync_image.inc': ['32eb714c760a84ba9b749d4208cf2b53a521de7cffda0ed2f1316e5746afd68a'],
 'Devices/SensorBus/Src/sensor_bmi088_fifo.c': ['d73d79c9da06508897f26ca13ac95e9222568c95bc4ed4db0b12dc1386b5f284'],
 'Devices/SensorBus/Src/sensor_bmi088_sync.c': ['0552f0f6286bb7e73fa1cecf66fb27f257c38b51219cd21b2a0c7a4057b9494e'],
 'Devices/SensorBus/Src/sensor_high_g.c': ['3dc2ac1db0761b8b4d89740be22fc0f22df67166adfcd1875529cc9dcfe780bd'],
 'Devices/SensorBus/Src/sensor_imu.c': ['7526e305b6a047aa3a2d1db18b2c8d69165fb21cc43698022c5c0c9b96e0d9f4'],
 'Devices/SensorBus/Src/sensor_register_bus.c': ['e39bdd2e172d3911a0d2c40849d20e26cd2510fc42a56154c2649c3f0423313c'],
 'Devices/Storage/SdSdioFatFs/Adapter/Inc/persistent_storage.h': ['87e20166c75d688c0e78fefb70866def2614189d3144e1d491b21be237b82482'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_sink_service.c': ['50d8f55c4a68f5313ab8dc3b5f89b75528f1998b733f83cd9244907346e38c85'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['2c3c761ae971fef98ca7ce81acb751124594db882c53e97055138dae6679de30'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['3d237fa5bbb52c5b583d457103969c249db31fb625c7f132f43d7d352df7ad3e'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c': ['7a0ff3e6b484a9b6e5ddacbdc61d2aa87fd50fecb6f863b986785b97d2eb911d'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c': ['0f313c63caf4857f0d14d15873b1a58c529501feedb1f3564416ff88af92f3dd',
                                                               '1067eb558770eb0fb6cf49f3b4c6b3fd8a4aaefc851dc22907e5c9bee16e3291'],
 'Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c': ['be5f2e0daeaf8f2623e6f1eaa6ca8681e1323ce42d594464dada11dca1977ce3'],
 'Devices/Telemetry/SX1281/Adapter/Inc/sx1281_instance.h': ['6c5392da7d877550a47649b4043feaba3ebc88448b30611a1e040c0862ef4eb1'],
 'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c': ['86d9d4091c94f1b1fb525902a2c0d62421d44769952d3fadf5b35291aec14c84'],
 'Devices/Telemetry/SX1281/Inc/sx1281_bus.h': ['cb8ad9390fd66e047094f105e4a7f4a55a204f0678b7af84ff5dac7aafdf776b'],
 'Devices/Telemetry/SX1281/Inc/sx1281_config.h': ['138507aa26e2d45a7955a390764508f02de79b2fb02f87f1654a3327fd9185fa'],
 'Devices/Telemetry/SX1281/Inc/sx1281_device.h': ['8ba0320fe9967a4e149861a24c83c3184f22b8b6ad2c3fd669fc14765a1a4a2b'],
 'Devices/Telemetry/SX1281/Src/sx1281_bus.c': ['0dd97926ef2bd4e7e80d4f4ade2547d67ae0270395c8ab17640d89816d92fac5'],
 'Devices/Telemetry/SX1281/Src/sx1281_device.c': ['0c9096e56e659f28319221ac9d56e559b375c1174787844946f2517e8dc22bed'],
 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xe.h': ['2104082df11b7e172ecf85461a72689b849e05b222a573e3cae0b2ab279800c3'],
 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f103xg.h': ['7ca8ab045885a99481ffb141e01b0cc4f6df4d5e1914561fc0ee67b6f4a4e99a'],
 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f1xx.h': ['05e93fa3ddefb2e83d762b9ca4de36e3bba9cd8e9690400fe9f2c11fc0a3cef5'],
 'Drivers/CMSIS/Device/ST/STM32F1xx/Include/system_stm32f1xx.h': ['a54dfbb3480c672f532d472a6e84bcf34df6551771d2e9966c5a3503c676b6ab'],
 'Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f407xx.h': ['bd21220ea8b6858c2d727cca1d2a5f1077f8a81717acdac583a1e9165d858160'],
 'Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f4xx.h': ['a19edea6b2f4df2ab3c567782c4d313a52319c4303bd56ad7dd1d0e077014657'],
 'Drivers/CMSIS/Device/ST/STM32F4xx/Include/system_stm32f4xx.h': ['02c067d5a135f540c03215dc834b1e60a97bbd4e55bfd3994b0c82a15ea3012a'],
 'Drivers/CMSIS/Include/cmsis_compiler.h': ['03ab80c426a8360eaaad833ac816462a9f38cb2e4dbdc490914880ad071181fe',
                                            'b51963d271c1571ca3463654c76aa7ea50c4eac5d0a2710df10414ac64d9e0f8'],
 'Drivers/CMSIS/Include/cmsis_gcc.h': ['341982e6d6c91119214c47d7a04b31f1f8ce0970c45e2c9fe0870c80d0876e28',
                                       '43bfd1fe69fbbc2ca70aaf7d43cc3e20f16e0c7f66e1bdef9b51af6dc14b2617'],
 'Drivers/CMSIS/Include/cmsis_version.h': ['184c19fd3ee73632edf35a0b4d49cd48be75fbf49e6ccb19d9db05fa83bea4b3',
                                           'c2570d56ee85d4f2ec0fb62f31d080d3cddf3a015500a4ed5a006a571637b43c'],
 'Drivers/CMSIS/Include/core_cm3.h': ['655bb08e9474438dec8b1874ea6c63749dc2787b85f06a0987c4870bcb580f21'],
 'Drivers/CMSIS/Include/core_cm4.h': ['f5b63d52dd1557b15ca414cb59c264f595a7b5669db2a5878dffe22f4caedc8c'],
 'Drivers/CMSIS/Include/mpu_armv7.h': ['29206b52ee02290ed6f5a5415ebd4187de802cf176d9b3cb844390d8e5571372',
                                       'e4968e627df085e4ebf46be5140be657e035d978ae1938c1c2e3ee49fbde5030'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/Legacy/stm32_hal_legacy.h': ['583cd8373bde87cbf384a9153b7c8ba9c456139baebb248bffe7116c926e2286'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal.h': ['cc3851d46bc92478fe355f8b1fedd013deaa70da5e8e4136ce5cbb2536519803'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_cortex.h': ['11ef612e231958eb9f3d4f825cda6bed35bd482996ecbf51f34b5ee7d84371f7'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_def.h': ['377e7fc68715cfb6d09715e9d77bd5cee09e79f00479f502d3191016c3c388dd'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_dma.h': ['22cbcbf02ef1867f0d9bbf28c600c9aeb71a7d221608449ae64cb48339687928'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_dma_ex.h': ['1b09d5229c87587ab894fc3237182a7027b1672a20433b9659433fb978e459f3'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_exti.h': ['745bd5b830259f613d116286a445d18c26677a72170117f2b35b7e0607fd563c'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_flash.h': ['fc9d0c2df0c277cbcb37a5baca8e0b6f112e4c7e879dc753b62aa9095732fff5'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_flash_ex.h': ['6bdda70eea1f54de098cf7033091c1d367e40043e3e0759ec08700718d38ab35'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_gpio.h': ['d43ff762af74f1494439c274a0cd409d09db769e6e85d8de941614c81b02b853'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_gpio_ex.h': ['ab0cf7892b25d9b2488b5284c4836b59f679bbc2ec7c7bc4199f83b2855add68'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_i2c.h': ['3c1f12595819a7c97bc28f4d6c82dcf45dd1d3c8a589f1a76bde97762aae9d19'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_pwr.h': ['1353dc09e32e7e6ec686b725b80981a9286c7e8b5383f8f4259f672470d481c3'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_rcc.h': ['8bf099bedb0c4fa035df81520f99e289464293b27e71d7e8759c8d5160ce8ac1'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_rcc_ex.h': ['ed9ac1b6349ed0989367a1daa82819390dcefec0f6cef6fa432e09b2c9ea0adc'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_sd.h': ['8cc0886f1070d1836e1d235422c3390fe7a59c674e5af568a185d1981d178d8d'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_spi.h': ['261464a3f9e9ad0c8c6390eeec680f1bbf87cf5c72c80008ada16928070446e9'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_tim.h': ['7a3dac99a810297b21b785846927dea4b1a43f854b2bd19e0f6b3af767e4eda9'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_tim_ex.h': ['21f24eb4e1b8eaeeb50240dbb0c177619f55cd4b12e366ddf4105c269ff628ac'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_hal_uart.h': ['949edfcd2021d8c73c5eb36d5cc1fb995b6f7a19fc084121b340c7502d33c135'],
 'Drivers/STM32F1xx_HAL_Driver/Inc/stm32f1xx_ll_sdmmc.h': ['a9b150c9e496fe646d7987ff1fdcfe541037e45e788bfc27dcb7f8276f4e6d12'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal.c': ['607343f969fce8d49111fe4d8d32001c9b289742408d0452ae49761034f39f01'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_cortex.c': ['21ccc3b54e45e62b278e7f32fd34533bb1e0f4105c7f47c9218ffa0801bfbddd'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_dma.c': ['9ec6e91366c9b27c64b93c4d31fb4636dbc830b055ec501dc728c34eff6900da'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_exti.c': ['6f201feccce8c53717098109bd4d2b4a0894ce4334cd1d6cdd8d15d5e69a8eb6'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_flash.c': ['cddd2adcf578c7d63fd27f55a6ef88f50540a3b65927dfc411c192900c127bb1'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_flash_ex.c': ['5e0631a9ce807629cc24d26effb6dba3b0e4eeca10e9d46ae9d5dc40fa1989da'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_gpio.c': ['397a5911cb314d5afb0e20b33721a056d6b25377272aae2cceb1078b6c224e63'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_gpio_ex.c': ['dd1c7ad7f83c855f8a8e58ffceff70be0e5b117fbac62b26850c1e5b81367dd7'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_i2c.c': ['25c683a3412e9be97acbc01711aa9630e55a2feeae68de2791275fe6c123ca6c'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_pwr.c': ['d7db81f800f7f41c942b485e2f3fe9a27f5b21def71830297ecb44f131d91e60'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_rcc.c': ['5c64b13347aa70dd970f803331d3e106e915e13e2bb029d27c673cfba7cd394c'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_rcc_ex.c': ['2dc02facf7141e4a25ae5653287d7100adbc3847b8a25e3e00969927c2e727d5'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_sd.c': ['9d363fac83023e248ae9789a646e49d93921892cb137556cdb034938813a2234'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_spi.c': ['74c20012ae5e579f6f720b941e66cae7b39ca47d80d873dc53d2274519795802'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_tim.c': ['d48299529390beba290db650bdac9851d69b9c127d6f9f7bd3dc9f205c843aaf'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_tim_ex.c': ['5f129af0c70c87e7c960c11cc046864d5d2f3963b4a952526d306a88d3295c0d'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_uart.c': ['0baff878faf8551e43ad63959f04bae08d61ee94e686e56a56cd97d02535c4d9'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_ll_sdmmc.c': ['c0cdeb33fdd4ddf4f4841f02a466d30b1e7551d90fc31fe972d219f15ee29a63'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/Legacy/stm32_hal_legacy.h': ['8c2d2feb90e8ed88fe5756f3f1616a2b67aa1cd0858da8b130ed69607688c8c0'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal.h': ['6942f40453fee331e026179cfac4c0f24ffe6313fedcb68af9c3382f702dbaf5'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_adc.h': ['d1be882b4bef7d53646e85e3d1783b47e7880647ee8a1436da58d652c803b12f'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_adc_ex.h': ['c7da815c495df4b6d5e0764af990c1ae8df871fdd9e7f6e49416e931d40b3a0f'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_cortex.h': ['d96dba22903abda49d66cad29ac0c49357e6a27cf9cb03dfd8c6db71b61a7fca'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_def.h': ['c8eb3f7b393f8c5a0c32e16ccfa101c83ddb59e96bd42239b8a5c5d4da83e97f'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_dma.h': ['71c38dfd65c5415b388375147e5317c7ac018b39893d6fd0ac1c897f4313329c'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_dma_ex.h': ['3ee15423d73ac394de39e7b65821775966389b13749ff0849894548ab6968676'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_exti.h': ['61e8f76bdb45dedf38fef592504e10418ca410952c7a209cd271b45ac835833a'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_flash.h': ['10be06c6e06fcf4eb11e236641948aed861898fea235c606ae221fa72bc46638'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_flash_ex.h': ['7c206f5dbed3c147a6f090ab808933132a1b06b8339623ad7174fd0a222e981c'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_flash_ramfunc.h': ['f18a6eabc99f56483566f9231ca33c780afa98bc93929e60bb419b5e544eee2a'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_gpio.h': ['0b40fc83363b64d3c7396a202be7a914ceaa7735ab0fa81d566ed320102b23fb'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_gpio_ex.h': ['4091beefc5bf8b250f376d400f43ca028ef7378e1c7ba5c9eb5de64ec74231c0'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_pwr.h': ['d6f6abc4af3d5a1ca59d886f5a9154e44f257a43af77c7f18173f160825ed6b5'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_pwr_ex.h': ['1794b88c5e080858c0205a2e94340c0250ac9171b3a3f01cad6d050005a1b09d'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_rcc.h': ['eb6911d964b1cf8a83993b19c8feb9845e8793d7c0e5d643390b53207c8b078e'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_rcc_ex.h': ['49f0c8068524e1de248738530cff3bbe630dc4784b6e8b5568fbc7e1a154f772'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_sd.h': ['86fe44effc4ee65ed2a46dca2362dfb175d563fe4586b4caadd9dfa6bd6f6fb6'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_spi.h': ['330803c32d1d5ec40df5a827a74cb1d850ec60b207eda5bf6299c57d575795a6'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_tim.h': ['63f00354e2a5e8d3a8d211fc736517273e12b99a1eb782aa7a2670cb1264a16d'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_tim_ex.h': ['aa6695d64677e8a7b46d719da3d81049290f42383c17e76271605bc68143fd1e'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_hal_uart.h': ['42528bc9caa6e2fe96b7e6d7b3fcdf35d8d85ae38d33195a233e18a072f157a1'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_ll_adc.h': ['fabfc9706709a9997e96d87aee25356b3ca84021668a915ad816ba42e1babadc'],
 'Drivers/STM32F4xx_HAL_Driver/Inc/stm32f4xx_ll_sdmmc.h': ['46fafb73c1c6fe5390a5a80049a28a443877c03f6dc42586cac11294f5f5a642'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c': ['97e715cda2a34bd564b59ce4ba9b16bd29651f8f229161105aaec666d76ea91a'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c': ['275b278044c92159719b25adebe672454387976ee5baeb1eb61e83c34deb13d1'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c': ['54378229ed51c2b3e4665983bc0e9a644eca93a7838f622f7234710071967965'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c': ['9aaa0f19137d700616bec01a5a806786c24e3f3386120365c5d2addaa4055505'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c': ['a345a1b1fe0221c827d5ad21d5a0f5387296bc2c075e06e5b8539c23da5678e4'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c': ['90cafb5a5b17a46b478770ef4abdc9a641cb395419abbb80f288138a63d44582'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_exti.c': ['f56651f86e5d89e8bba3bcb331353e00f291db15c902927a205d81bbe8951e6d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c': ['8bf12eeb6e6cfc12a17587ed6d761724e0835a4a3dc0f6b14a8d1ca068bcb55b'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c': ['51a70deb9b19dd43f6f202430fae052f2deb26c39232c09c79230c8d8a61f773'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c': ['d3b426e8cb9d617f9064d2b0cea2a1d02b7bb6a74cba3f094779d6e922e477e3'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c': ['408908b15477b6ce2b0b9703caabcb053293d98f2f109d6e6940e076a6a3902b'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c': ['d779468a95df34421bf6c8417136a79aa910753381a644afa9ed10b185ae18b5'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c': ['4409dddc0d2019f918d0ddebecf659f06d4de3f9aa28566621a16ea47203331f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c': ['f3ac468e2f415adb74281107c0dec1448008950b64a7bb11c14cbe3ee1a936de'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c': ['526324811fa113c3eadfa84cd24ea5e607ad8e8bf003a2085456c04b734ca25e'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_sd.c': ['02d7ccefa2b8574febacb1ad595bf1c20f3f0601853d4dd5ff536ce4f815c29b'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c': ['641ad467e834c17a83c445cf8eea7c8317a71976d7e0c77da740be999251efe4'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c': ['a7dea3b10a771a380915007b9ece123654c6bd2a40f611102220df9bfdd143e4'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c': ['4471b582d56545fbd48725401249b4a2a728ccc0d933b3f1a02e2b09dda8d8fa'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c': ['a74ed3a9a13a4fcbaada9e6f88f7d4fcabe2a75852a6ce4c09f8d4314a2e851a'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_adc.c': ['9fe6fbeee8b8d44d8bc548f6d4abd8ee06693f56f12be013277dac2f767f19ec'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_sdmmc.c': ['888999f70d05daa37f57dc144c6cd31aa50259ac30d73a33ed628e663247f7a4'],
 'FATFS/App/fatfs.c': ['a048d5f55fa022c4c6e3eb48704df8bf5d1bcf7c2e1ff982d07f8ecb6850117a'],
 'FATFS/App/fatfs.h': ['768b6f39109371bb68f6985d5298781b9ed0c583f1f23d925d673452daf06a24'],
 'FATFS/Target/bsp_driver_sd.c': ['6ef6eb4e8ba3b3e2c7c84cc1ef4512ef2e7eb84ee0dee25ab48101cf9252292b'],
 'FATFS/Target/bsp_driver_sd.h': ['14cc10d30d986bdbefa6a342f9f1dfab348073b6703a0e993ea6daadb55c2e5c'],
 'FATFS/Target/fatfs_platform.c': ['835b5d3ed8592c63d71b0b1004a879bad024bc5fb6d7bbdd2e852d16ead110b2'],
 'FATFS/Target/fatfs_platform.h': ['b39eab113dc3d9855be64ab7283472cf88649ea21e66a9425f2154c94f77de5f'],
 'FATFS/Target/ffconf.h': ['596f74c270e0f5a011501c10f30e20539d20c611f2eabce2fd97cea79e4dd9c4'],
 'FATFS/Target/sd_diskio.c': ['2a03fc2f56b14ccfbc1df0ba30e0b57ea45d49cb5b76ecdc2f153313ba273dce'],
 'FATFS/Target/sd_diskio.h': ['b73bc37f6ca8b3f1918a87b69fc188b2dba847b868ac994f48b2afc103a731d1'],
 'FlightLogic/Deployment/MultiTrigger/Inc/flight_deployment.h': ['210e88a092d6ebcd0480ed180f77e1c24d9e7c5e7d6cb20f24b022de2185a84a'],
 'FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c': ['f22499afafe73eaaeee1410c886d53bf412d90493411d4aeda3bb7eab19c0362'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['cc78d4f7036f1570c83de6fe04fb69c6ad1786fb19b4966d7995a1bf186cb4c0'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c': ['1773ac4d97dec9e426c1f94940502f3c708934d7d6d9b374331c16da51ea8144'],
 'FlightLogic/Indicator/GpioStatus/Src/indicator_service.c': ['f0768fd8f6db8d346507a1c8cc05387a46e35a732a9d0428fff8e5fc6f7bf3ca'],
 'FlightLogic/Landing/BarometerImuWindow/Inc/flight_landing.h': ['2531bc2dadcf7d91d1177026302d61289d31378432789751afe7c398611d92ba'],
 'FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c': ['a3c7fafa5c2cf6a10eca822694884b5e8d530fb2ded35057d0555c57a769979d'],
 'FlightLogic/MissionAction/GpioOutput/Inc/mission_action_output_config.h': ['a01c52122d66971de781abf22af1cc700409f67d38408097f83fdffdff209a8e'],
 'FlightLogic/MissionAction/GpioOutput/Src/mission_action_service.c': ['d5c5f173f5b4149f64fd2ab8aef28fc85a65bd4f3ca1e7ed0294272ba931de93'],
 'FlightLogic/MissionAction/GpioOutput/Src/output_service.c': ['448d893d8c626105cf103d1a77ddc455770c3e59a6eeaba011486678efcc3e75'],
 'Generated/Inc/air_link_config.h': ['f0ccc4b3380f7dab45d259862dceff135a1b798f23b69e1eb592230d10cff1b9'],
 'Generated/Inc/project_algorithm_parameters.h': ['52152200a68c5a7499752c1405e261e2282fd87dc40076453a8b376ec614e2cb',
                                                  '6e99ff45257aebb8d090fdde463b79f7a4ec2fdc418ea6af2f0a2eaddde6250a'],
 'Generated/Inc/project_capability_routes.h': ['68e8d297cba2418e3e9d54ed16906e999ec2defefcd908888fa83bf5354cb5b2'],
 'Generated/Inc/project_device_build_capabilities.h': ['706e244020e5e231e11f3966d5e3a10ff82a13d64beff2dbfc33094711990435',
                                                       '86225ae13393ebd993e519d453d441b31a4d52e2d38d87f83d7b4bd35807c046',
                                                       '9b244468f3b907563ea350c0517c1f6ef11a917135914f258896cbbbfec6833c'],
 'Generated/Inc/project_device_instances.h': ['180613dc37a27abcdd4cf3660351a8283de4bc4b3bb464cb50e448cea6ec7e9d',
                                              '907208cda29d653dad166c43d5e34702d296e36c6932a858439b697d21e2e388',
                                              'c98e3ebcc802f34f76f501da85f58f24fcc6327c9d7bc9f15e69d868db2c25b8'],
 'Generated/Inc/project_flight_config.h': ['52d3be87909b59acf2f5877562ab49ab776d52b09ee04074b50bda55ed6bb56d',
                                           '72ed95e9867badc0c780fb13f078cf2b2497d8a2152d6b3c4aa845cd717c5ccb',
                                           'b01b7bc1731ca79d4f635cacc2c62a84ace7a5af6ae58e3b394bdcf180104d7f'],
 'Generated/Inc/project_log_config.h': ['364e6b29b70366d74d63932c34dd803d9f3f6c6ea7d3e7f6daf4b2731dd4192d'],
 'Generated/Inc/project_log_decoder_profile.h': ['dd91708d50aab35355a7d04a0739fb07a60fe6839456cb7b4ae0467603a92bf2'],
 'Generated/Inc/project_resources.h': ['b9a515b62620816c2fa38cde0e0e69726298510bdbf4c66d54cdfac023c63ebb',
                                       'bcfa240313765db2fce116f774302bfbd61a5c9f658fc383109ddfc977a0058c',
                                       'ec162a07c17211145f62bcf2308e5beb81a8abc0ae508c0c5f1e4d61120e3ce2'],
 'Generated/Inc/project_storage_binding.h': ['24d5cef2b56d2375c4693656b6dddac5c3a5877fe0c717d6a242f25b6d3ca4d1'],
 'Generated/Src/platform_resources.c': ['3d429b5ff33993edade52600923dfa8ba524d1a85f55943a604d4f3e3c1e657b',
                                        '6718586e468d3b136b5f32d831a6203c3b1ae4b884321910f62ce1e15c25aa8b',
                                        'c9ba3926fae99455bde347565b62ace761ac1ac04ac6b0d135cae32fb1a2f3ae'],
 'Generated/Src/project_capability_routes.c': ['0f417906079cb36b1e772ff7e5d47fd8170093f9849f7045903f45dd13681f23',
                                               '975d0f91186c0aca98874a2093ab481a08a759ec016b2fe6c66b48bff7d283d2',
                                               'd7da22dfec3c0d4e3e30af34f47056696be51436d66ea3bfa3d1406cf0422772'],
 'Generated/Src/project_device_instances.c': ['051f2e55df2faeb9bf0973c64ae4a5c6709643b8c89a2b621ed2f935855be6bf',
                                              '462769c1996bc2ba55f2f9a19d08bb60599df06b3671076c90fa6a88b79e89e2',
                                              'c9a5e6ac670e7109dcec3d01bd99fd466c6f9d4265fbe533d84f820c9bed9ecb'],
 'Generated/Src/project_log_config.c': ['dc038bb9ce54cbdd92552ac2b2bc940259714b4dd9a36313cade9f783db02fb7',
                                        'f642124cd04fb1e8155a682d2eb894310fdbd2bc0de1da0571c50887020c7753',
                                        'fba6c0ab330e20811c777965a670509fcbf3c288577d5baa6aef4bdee62c6302'],
 'Generated/Src/project_log_decoder_profile.c': ['5ba2bd352ffe8fef69de33d7fb2d512b47788735aa275b78e3e12015a6b19998',
                                                 'bfef2767ec8a1e5049d1e40e628327242b255601b22e645b902269b15798be51',
                                                 'd5104d48bc13a6510490fc88210ada8993ab8be664685c0b4ac1a8b7a1b5f198'],
 'Generated/Src/project_metadata.c': ['174acab00110f698c8c3c5d666a9d8359a4ade1d409ec3690df6805f6e3e31e2',
                                      '2fc35e9d2c35b8fa5c992e6df203806d4fe110707122ee08c67fab8654c8d7f1',
                                      'a617ea4e8a6a13ceb1cae73b97c298a9d9e1bb741ee8efd6bc56913c4cbfae57'],
 'Generated/Src/project_mission_parameters.c': ['2deb7ab0ea38d495f7e60d3c4d3c6fefb1fe1b6ead5e24474aa7ed850dad248c',
                                                '3cc327f5ae54dcdcdaa997eac0315a5afd6df5fe3dd27380d07b16b505859e08'],
 'Generated/Src/project_resources.c': ['3645afa0cbada24aec5352b89179dc603013d2d17ded9ac010bf7f8a19b58642',
                                       '6e713c8d4e41ae835a6b7654834287c4310cf16adafda9093bc64289296dca98',
                                       'bc865aab17957bf675b47fe115fd32682ab672d33db79d3955864b1bb03d0737'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/dma.h': ['f3190614531c4bd5af6cfcee9cc29aea0321863613eba43266dadb615e6f1036'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/gpio.h': ['cd5a5f75903537cba4460073b40e3b0d18d4af6dd7522c5a0756f0b9261e03af'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/i2c.h': ['6f6f14ff041e9ddeef2faea1ebfb7ef335ffbc5684328918c303731c3104fa60'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/main.h': ['75d8b5dcb13ae83480d455cfab20a24586bc479e455bdef492a554108186921b'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/sdio.h': ['296104874e74470045840e5752c6c451fe0c2ca469792d3a3e6e02c7e6b35dfc'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/spi.h': ['fd689a3f7101cf17870b51472d997c4458b6544a2273a925a5b26cc0573af1ef'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/stm32f1xx_hal_conf.h': ['2a3eb49aeeb936b64901f0cbf997e5e8fbe5c329c797b3820b01ef0304e10fd6',
                                                                 '4fef6a7d4e1cb588089ab17787fa4453e4d0d37e7f505c86ce1ee72d21df4469'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/stm32f1xx_it.h': ['03e11501deaf0c8c8b30c0628e34795c0d069bf9d7dce882304e3ec954dd2802',
                                                           '279bde2b417bc59bc7f7cdc864a24b532dd6bb269d39e62607c244a6a6312fd1'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/usart.h': ['3830463196e8f3dddfdfa638032dc19bfced8f9b757a3cfdcb785ef154808cab'],
 'HardwareGenerated/STM32CubeMX/Core/Src/dma.c': ['858144ed23d875682731d7857a929824d3685585c60f7572f440f63506f39d28',
                                                  'f16c263dd2537fda3b2cd41fd760f938d727b2f7acfc78c1fb1ebfe3b62e949f'],
 'HardwareGenerated/STM32CubeMX/Core/Src/gpio.c': ['42efaac6d62d827024542ba9fd012efc6118a6bf6b435b439364ed2933a33ee7',
                                                   'c0406e7ca314ebf2c9fee6f14a3a1e6d35982b05be0972b1ab6c59560527bd5d'],
 'HardwareGenerated/STM32CubeMX/Core/Src/i2c.c': ['050c3d95999d8413db3c644ef70927e8f40757c565eeda64efa6099a91090366',
                                                  '73eb212ca82cbea9dfed96ba5eeef18399ac5bed67fa64e07f21542c01c4ad3a'],
 'HardwareGenerated/STM32CubeMX/Core/Src/main.c': ['2c2761fe62beec6c7af92fb7063c165e503830e2403fdbf86a5e0f975aa2dbaf',
                                                   'b8e5538e1d76809a3bbad519818a1cde4118e7ea3373decd2c108fd77242e7b1'],
 'HardwareGenerated/STM32CubeMX/Core/Src/sdio.c': ['0bbfb1b75b38c9f3a2dd1eec2ebcfeb2c84de35c287bcc7918a179d04fddf94f',
                                                   'eddefde01a33e5de6bbcbeec9a69df52c07c71b5f5e337c09c49a98f8740f9fc'],
 'HardwareGenerated/STM32CubeMX/Core/Src/spi.c': ['2a915b9565073411cd453022e25b058a5274f46173ccc72f3114cfc0d4c162fc'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_hal_msp.c': ['82fcf9e74c536bc88e82ece381349b44f908e40915f989f01ca58f7c99603406'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_hal_timebase_tim.c': ['f028ea0404f854f7f1ca870ffc0e493307b7be15db70c9a81e1fa308cfbf36cd'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_it.c': ['247e03c42afab942bebaf9d883c4a50b0f4ccd15fd17d3df0f440264bbeb9c12',
                                                           '671835fb2bfedcab437d64fc04ec7c38763d7b91e592e306653aaf463496a04c'],
 'HardwareGenerated/STM32CubeMX/Core/Src/syscalls.c': ['03c06c72eafb44b499814cf9234aba57dd830f345d9b8779b5d7090e78517600'],
 'HardwareGenerated/STM32CubeMX/Core/Src/system_stm32f1xx.c': ['6f13b57054f33b4dcb8f3f23fa05b2942d9dca8abd9a2a08ecde6f99693505a5'],
 'HardwareGenerated/STM32CubeMX/Core/Src/usart.c': ['cc854cace032083132de997ca4a9f8b4258f4b8ba24a66bded0d475bb2f40dd5'],
 'HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c': ['d96b2615b745ad0b200035577588d76969ba68c856f8932831798bdcfabc1cc0'],
 'HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.h': ['768b6f39109371bb68f6985d5298781b9ed0c583f1f23d925d673452daf06a24'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/bsp_driver_sd.c': ['193653bc18328c0a43f3871bf6d0814748120478890b75404e498e14d4228e0d',
                                                                'ad7d02483eeda4f9f48fb9ac1484e86d7c3ed6f3a2af2cc716d8163cc0aa863e'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/bsp_driver_sd.h': ['04105b164eb5abac88e25134a5643495f7dd7710db26a5a9c3a079179e919311'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/fatfs_platform.c': ['835b5d3ed8592c63d71b0b1004a879bad024bc5fb6d7bbdd2e852d16ead110b2'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/fatfs_platform.h': ['94448969218eb69e0be8698ee029905b730358ba1171fcfd6d95ecdd61f6d903'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/ffconf.h': ['807e10827786181a386788a8870967e7df29e463c1acefb54cb3f1444e7d2a88'],
 'Interfaces/Inc/system_barometer_if.h': ['2863c5f3b127ba4269d045d5d0f0f72cc4f65ab297e742aaeadb9679057365ea'],
 'Interfaces/Inc/system_console_if.h': ['b59439abe8d596a088cf14e492372c4dd8e2c6cc63450b5a8995ec170f89d9ed'],
 'Interfaces/Inc/system_descriptor_if.h': ['555cda8fdd2b0ba8b5589c7d3fa2c11b9043951f3b60c3807868dd54f7500b53'],
 'Interfaces/Inc/system_device_types.h': ['b3527077a9b1b7fc64c76fb714c368e0f910cce3d9e4a83037c0e3f904e08283'],
 'Interfaces/Inc/system_gnss_if.h': ['9f04960c39d8ef6961332b92ddf368cc3ec4b03418de90366e64c64c081d4c7f'],
 'Interfaces/Inc/system_hardware_quaternion_if.h': ['bf8f5dcfffc52fefe11cb2a34830a7a8b8c4980fe8b65b96a1de475f1d569726'],
 'Interfaces/Inc/system_imu_if.h': ['71b7e3ea457af482d22bb943f327821ce690a84d964a81714ada56298177eaad'],
 'Interfaces/Inc/system_indicator_if.h': ['84e1df0d58f44257a7322674995125a9e036474785d0410a87848c7fdc85e90c'],
 'Interfaces/Inc/system_log_sink_if.h': ['3b4cb8c318ed55f16d32acbb74c605c28822fbf90d022aec7c36db4ea39772bc'],
 'Interfaces/Inc/system_mag_calibration_storage_if.h': ['c2fd04f7abc1d3282fad17198e5e52559dab462a30d7ef9c95e827a775f6c052'],
 'Interfaces/Inc/system_magnetometer_if.h': ['ffebb406126fb0fd8b691800795703d369134c1026a13d6f3ac38d4038704561'],
 'Interfaces/Inc/system_mission_action_if.h': ['a91fec0bd3d43af3b65025f0470a978218d4312241844bc6a60bf6f84a413b49'],
 'Interfaces/Inc/system_mission_snapshot_if.h': ['eef6764f8787f5da8ef0afe1ba3630e5b75316ec5389f30571dda4685c57323f'],
 'Interfaces/Inc/system_navigation_backend.h': ['e5d93e1c993f6833bcdc9fb2a94f473e205f3c32885e3f388ccb1efc1f678614'],
 'Interfaces/Inc/system_output_if.h': ['ebfd844d3549ede753cd83821b31a57ea20765387381b9cbcb68325a16fac850'],
 'Interfaces/Inc/system_power_if.h': ['e509ff46dbd46d8fc431a61ea69ff00cbfd75c73dbfb4188602d1b539bbff5e8'],
 'Interfaces/Inc/system_project_parameters_if.h': ['00fa9e3ec1ded9548decbcfb215e4c81a40a44ce98994ec75b31dcc4b1a2c887'],
 'Interfaces/Inc/system_storage_if.h': ['524f26dc8a71a50bba3a6ee1fd6089d3f5f8691a804fe02f47ffafefa3646d06'],
 'Interfaces/Inc/system_telemetry_transport_if.h': ['b24d1566eb498e7b3dafbe9d0ef8465291585db8f959e112c86ebab3da7b3d57'],
 'Middlewares/Third_Party/FatFs/src/diskio.c': ['28979897da7fb95a2441eafc57b3ba72b336e8b4244074286d7d905210da1fc1',
                                                'a536b78c8435bc426ac35c170acab52f82610417e38e9ca06295ed0984f3ffc0'],
 'Middlewares/Third_Party/FatFs/src/diskio.h': ['4a924049b43b851ebb4a68557215a0d65f7115751eec443a87bf2a0e08fe40c1',
                                                'd6c1d42c52a72796f7d2d4ebea1420026f55eb8bc4d31ff29f763ba4c9116f1a'],
 'Middlewares/Third_Party/FatFs/src/drivers/sd_diskio.h': ['77ea2884e5924b34349a8afec392b24a0825eab73ffd4cd92fcdff4ce556f44c'],
 'Middlewares/Third_Party/FatFs/src/ff.c': ['6dbf1b844f3c68b8baf73b243ff9c41478a832e134acc1da3610cf5e93d645a6',
                                            'd63c152f2c6cb10388b7ec8721c6510c5632ef46ceb55e77af3acc737788cf3a'],
 'Middlewares/Third_Party/FatFs/src/ff.h': ['e05e0fa39f796590e03bf8ca369ea61fe3e567e7d00a6fe258508972ac54e845',
                                            'f5ffb869bd4609e7a0113fc95685e0a6e75c91d71bd6ff3a593d781f5629c704'],
 'Middlewares/Third_Party/FatFs/src/ff_gen_drv.c': ['05d1bc3c395dd710213e530b31c854067653df40432b67ef2ec99fcf2cdec1dc',
                                                    'e7ef79811c24d68a3ded89e10cf6c9a1d009f9f2380130981f8e2bcc30b0565a'],
 'Middlewares/Third_Party/FatFs/src/ff_gen_drv.h': ['4518f84d83623921a3286ea6e57d24334e6c17aa6a5b160426a8163191b59f6c',
                                                    '599a324cee4f7e11c23aa6a7a899a14f5075b0077199f2fb401b2c98615e95a1'],
 'Middlewares/Third_Party/FatFs/src/integer.h': ['5af970bc2fab410f425d86750c2d6d1901cac20e1e50858c4654412da9abba52',
                                                 'ecfb04bdc94c49981ce4dfd195d7096769a662ae5bdf81badd651680cb48b281'],
 'Middlewares/Third_Party/SX1280lib/RangingCorrection.h': ['67d46add57927bab630479f36e000f2718205f0af2bc64f6c3e3652165bd8882'],
 'Middlewares/Third_Party/SX1280lib/hw.h': ['e640f30c18f1160bca2930cca1d9b18356c4f6caa4d6cdfa2ca16c7af08a1b44'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF10BW0400.h': ['70fa2ce6ff97febc1f0adb73d0d5edb0e895c2d34c647a2c6e3b5ee061d9d46d'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF10BW0800.h': ['fea2af4e86cc58cf0d7d90d3d383d20fd07149c862ab5a2182aa571df1f8488b'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF10BW1600.h': ['92dc9cd0265b693c1af9f9a3b6955531b2278be5474f836871bea1b6f4bccc8b'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF5BW0400.h': ['c987a1050256472963a610062d0bd20fa761f31287377a391b270eae7f3ee1c3'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF5BW0800.h': ['b172c0d8a1a87e976d4c8fef2238412bbebb2c37bcb29375a90f5419f2f684ef'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF5BW1600.h': ['73b03063030f8dc1d6e205febdea58334f44cfb8a061e6980f8a0f4f59aff7a6'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF6BW0400.h': ['a3bb69c16de3bdfdab249cfc0a9c19c8693ae3e759ae643f623e8226ef6f0d68'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF6BW0800.h': ['5df17648080dbdd6f94bb04bf0c3823e0253e329a4c9419be3457925acd60da1'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF6BW1600.h': ['cec1095086a3f133d8e3203967cca2274de8f3bb4aa28bcb945b1e54d9ada775'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF7BW0400.h': ['0be1d64d3da5785ac2f155cebed2b9c8929eb3b7a93466dd63a56e8a38730bb4'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF7BW0800.h': ['e4b1bc27ca354dcf0a4df1cdcdc2f7f6eb052c65f07d9cfea00f91e1778b5c79'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF7BW1600.h': ['f9a9178d3177f450edf61a7b64ed6478a9297b36bc052755ee7759536093110c'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF8BW0400.h': ['f028ae632ee011dca7831037ff5ea087bededec2d9881234e539354f70af3691'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF8BW0800.h': ['59fcb56af0fb00575a0044f88ca6a217b467769df9c16dd226fcfab9ff322c11'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF8BW1600.h': ['0e556d03c671b0609f26c4e3ca1225dc71445864275cb71e68ccd4e41e113766'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF9BW0400.h': ['27930bf0e80ee2a5635e96b97d503f3a7ebafd6f09edc7c03a14b4ad4229dafe'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF9BW0800.h': ['96b987edc3cdd69b47ca7ef6eb75dafe5299bfbbb0864d629220c4b4670406ed'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrectionSF9BW1600.h': ['018ed8894f93850db9fb6206b033c23902927ba4b014a0a588056ab964b60633'],
 'Middlewares/Third_Party/SX1280lib/rangingCorrection/rangingCorrection_defines.h': ['cba6d6df1cb5dcafcf429768e91d48fe57720551ec2711254f48e4d74f85515e'],
 'Middlewares/Third_Party/SX1280lib/sx1280-hal.c': ['fb75e779068aa4704b15c5ed3ad76b459abbd8a17c6191e6682072989ff96323'],
 'Middlewares/Third_Party/SX1280lib/sx1280-hal.h': ['67c375fbbfc71e506466eccd04febe9482a8d2fd69e5e724fb003b0710dedebb'],
 'Middlewares/Third_Party/SX1280lib/sx1280.c': ['8afe88a8156575e181830407295d68d5f0e2221749a9dd312a0cf6a66bc910f9'],
 'Middlewares/Third_Party/SX1280lib/sx1280.h': ['b6ad13b77f1c7fef35c9a17153cb1ee0d9eac1869dea3812ed419678b44ecffd'],
 'Modules/Inc/telemetry_service.h': ['f599c7be9d015522c78a13096931dc894f7c22b42ddc06310fa750f1c61d8ddd'],
 'Modules/Src/telemetry_service.c': ['3c4acd4b1df7681e51d7b0359728721412dd639b1f5cd7f2bd7882735a263dcb'],
 'OS/FreeRTOS/FreeRTOSConfig.h': ['aadf85d5ca5e93a303fadedbb0d2fb05f4cdca3891e95f88bad7b5471b790f60'],
 'OS/FreeRTOS/freertos_hooks.c': ['52874a75c3509a5569597fe813820b96703c978a62e1190d534ee0e9db18c201'],
 'Platform/Inc/platform_adc.h': ['5038d93afcdfef7cd808b3a4a5580c9109f630126d30f9aaee3b8ab7bd176a02'],
 'Platform/Inc/platform_can.h': ['b5b8aff2b064068d8edf49c21ed36e452ab55da14c1d6c4248fa8ca3329190d9'],
 'Platform/Inc/platform_critical.h': ['814f177a99c6504e70ade339bef843d3dc69cf4fb66e0bfc55cf271feba16e59'],
 'Platform/Inc/platform_gpio.h': ['a2d382188da0b09a2362f7d7c123262cf6a414cef950cb185f72f4469e022d8d'],
 'Platform/Inc/platform_i2c.h': ['e59180913673babc6b3b216b8e16676ee078fb26d8c69d62ddd5ade0db774de0'],
 'Platform/Inc/platform_memory.h': ['4174334dcfa27752f66ccdca39012b5b417c301e9cd183104444356176fbed00'],
 'Platform/Inc/platform_pwm.h': ['27e954b8d283a5a96bd00094926d8efe3a577aec982079aea13c45bc60991cc2'],
 'Platform/Inc/platform_spi.h': ['1f254211cf54eb0358a7172bfd51a9cdd7d91517cd16d5a12b9465da30329852'],
 'Platform/Inc/platform_time.h': ['b9839aea07741c962d836b6ddec066805bdcca17a0e7f7532449ca74dcde25ac'],
 'Platform/Inc/platform_types.h': ['a23f937f97396c53e6028ac121a067cb9e3ea2fff6b40f10a504e0128712bb15'],
 'Platform/Inc/platform_uart.h': ['0dc6cb85829afe8193bd04e5efc04d503516356c3ee707245d2f00f5f815d09b'],
 'Platform/STM32F1/Src/platform_critical_stm32f1.c': ['7a8196557ac5caf31cf45e3882ef918e0d4286eb1bcab37a0b46dc24214d5311'],
 'Platform/STM32F1Flight/Inc/platform_i2c_deadline.h': ['7fee84707f8396f06c1a6b97b2261abdfe85439ca31e056dc06b34a3c2006754'],
 'Platform/STM32F1Flight/Inc/platform_sd_clock.h': ['0312c8cf9572147a458ad837b9634a6171c5344986a3adf44cb1f6ba048e9f90'],
 'Platform/STM32F1Flight/Inc/platform_stm32f1flight_resources.h': ['35e92a7336508113f5ec36f781571cd51a4f82c3b7b2aa43bde9fb9eb276b6fd'],
 'Platform/STM32F1Flight/Src/platform_gpio_stm32f1flight.c': ['5c17d223e7237053eeee4db9388aec96839eb92d27352144deb951dd63473f9b'],
 'Platform/STM32F1Flight/Src/platform_i2c_deadline.c': ['65104ae4225c88f6b29b32da480b00b8e90f07f94d389dc1546e5a0867e0b041'],
 'Platform/STM32F1Flight/Src/platform_i2c_stm32f1flight.c': ['d68104f2dcdc1003d91f84cc919f7a593f9a8158fd309bba8d6f09ac645a6db4'],
 'Platform/STM32F1Flight/Src/platform_memory_stm32f1flight.c': ['94bc5d939c7571be486abb181669a5182fb58224494a6679ebc7cd6ea05f5569'],
 'Platform/STM32F1Flight/Src/platform_sd_clock.c': ['a423abcb041b93c74e0728442749cd6c22a654881f66c336bd609ec90345a6f3'],
 'Platform/STM32F1Flight/Src/platform_spi_stm32f1flight.c': ['1ca7760371948f1b724b4dc16480413a621d1670819737760a665437ac31e6d8'],
 'Platform/STM32F1Flight/Src/platform_time_stm32f1flight.c': ['463c8e1d13a258b351dfcabcee2f6e7697b2c202ef502f80fc871d5b0659b285'],
 'Platform/STM32F1Flight/Src/platform_uart_stm32f1flight.c': ['b0acec453d1b14eecd442fba44eed84112797898bb5a706da05af66ef41aaf9a'],
 'Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c': ['4920219fa17172cd3b86eb9079ef1deb41587b30c77dc215e3db11deeabb61db'],
 'Platform/STM32F4/Inc/platform_stm32f4_resources.h': ['b87acfbd074ddf5b73cf1bf5d83711358a76168dcc7d5f25f6e9cf315cf133d8'],
 'Platform/STM32F4/Src/platform_adc_stm32f4.c': ['71a57406179864685e6491ed1a692acfb37b9cba60e0581230c041eaaecd77c8'],
 'Platform/STM32F4/Src/platform_critical_stm32f4.c': ['7a8196557ac5caf31cf45e3882ef918e0d4286eb1bcab37a0b46dc24214d5311'],
 'Platform/STM32F4/Src/platform_gpio_stm32f4.c': ['7fe0d3115f995739e0775c68a6845ee60f26a4d2df3e55bb6625d208530b0cc3'],
 'Platform/STM32F4/Src/platform_memory_stm32f4.c': ['6632d69e1982a43d25a446f5e968acddbe0fe016f3061a9e6df043085a4392fa'],
 'Platform/STM32F4/Src/platform_spi_stm32f4.c': ['98e75be753fc28b3f002af3f00cd44a9282d0beec542b1f6477a44a44c8d8efb'],
 'Platform/STM32F4/Src/platform_time_stm32f4.c': ['1410dad1ed2d52aa9583db12cae186cc1b5c16e46f9f563dc61581b052f952ba'],
 'Platform/STM32F4/Src/platform_uart_stm32f4.c': ['62fd5b0902876a6e3bdbc0c21606b75aa0f43809f62905a364673e0256719355'],
 'Protocol/Inc/air_protocol.h': ['006a4184bf7f5cb6bbc69716726f2d764ca3680e9ba4e70bace765a7d2cf9ec4'],
 'Protocol/SSLOG/Inc/sslog_protocol.h': ['d3e21c68fb9a6fba0f5e296c16d65b678523a6c613a009be6982bd1a934f2335'],
 'Protocol/SSLOG/Inc/sslog_records.h': ['ac4820bec3ba7ce8c3ad95f8eab8cd094ae31ca510ee31b2266826b571c03eaf'],
 'Protocol/SSLOG/Src/sslog_protocol.c': ['7e926e2af2b869880af5a4de56a4349845cb096ba9f88ef840c1c16a4914889a'],
 'Protocol/SSLOG/Src/sslog_records.c': ['aee25855cff5ff3ff3a4d815d5b7f1e4d28f3a1b91fa081f5b3e49b50a3ada60'],
 'Protocol/Src/air_protocol.c': ['d67b4369f148167ac663a724f5f0bb92e940cba3f79e703d91fe73d50f15085c'],
 'System/Alignment/Inc/system_alignment.h': ['a72f2771f12354fca87732b6c5f7c9a0c061cf15e0456485d786865e5bcfa2b1'],
 'System/Alignment/Inc/system_alignment_backend.h': ['50aa0e7f5473f170d9f6eb8da4982c33ac77d23315ea95bac680bdd16a641074'],
 'System/Alignment/Src/system_alignment.c': ['b68a0501482df1359b8c36008b61203d871095a73319195b1005070415886f77'],
 'System/Alignment/Src/system_alignment_source.c': ['df558170c66daa8a42d801be31848e4da27ef9825820909036a29da959374514'],
 'System/Calibration/Inc/system_calibration.h': ['2632d568e51ed61031d1c07133fdfd07daa46d7296b70a2d8c0909dc08bb39e4'],
 'System/Calibration/Inc/system_mag_calibration.h': ['3bba88420b0089cbfac8a6e281d873bc1a4f108140245135c1e981a9daab175c'],
 'System/Calibration/Src/system_calibration.c': ['766c071bcb30e3d81c2a3ffbb5d63f2e74c81f9b605029c406b2ebb60b5a9d36'],
 'System/Calibration/Src/system_calibration_correction.c': ['9cbea764af1e49fbe1a726af61469661ac51fac69b15b2208af3627fb1550fd2'],
 'System/Calibration/Src/system_mag_calibration.c': ['8ea3f92141b61d0bada055e83bc9167d73a9aec2e72e5bc522c820d687ef75b0'],
 'System/Inc/system_barometer.h': ['a6fda781f4272266d6bff5e4f242fc5729f91de9b2dd6ceda48a5ba16840d3d7'],
 'System/Inc/system_barometer_cold.h': ['e55b291d74c07ab6a0d88e9ab5392b7de42c9c0cabda9128fe9dd254d980a423'],
 'System/Inc/system_capabilities.h': ['9d43c393512e5a3879c740d8c9f41328de7deb671beedede3e0036584284eda1'],
 'System/Inc/system_configuration_types.h': ['bd34df332643d1d63f7cd385e96d53fd073ce9f2b3ba107377cbdaca26618d19'],
 'System/Inc/system_console.h': ['c39b26ef44a9890a653b8f05f4096765e56101e646ac4a969e35706c479a7ca9'],
 'System/Inc/system_device_startup.h': ['0d0bc34b00805dd18f6fa4ce29097eed33d3e1580e0777d509ddf7ec62c11303'],
 'System/Inc/system_estimator_diagnostics.h': ['59c4f84e258388e366f3e403a3b051eb4ad2f3497fc175b6942984e24f66ad1b'],
 'System/Inc/system_estimator_profile.h': ['bb0edde9cfac33af6f25863e1d5f1d1dc63d938b6ee648845ce90be9869084fd'],
 'System/Inc/system_flight_recovery.h': ['af252c52c656109a16541871f7c3c985cc8699f0c107abc9f94d7fbdc1f3061b'],
 'System/Inc/system_gnss_quality.h': ['86ebf8d01b0912258ae37cb8641525acc11f6f0f71babe01cb118866338a4b1a'],
 'System/Inc/system_health.h': ['d11fff9a2595f59d518e88df538a4547466448d4b1e401d64f15e46a9fd9f9f9'],
 'System/Inc/system_lifecycle.h': ['941c911230447c734f56194de7fb2c2abce28d1de740a9d12d389f75d7298a73'],
 'System/Inc/system_lifecycle_backend.h': ['8fa00e4c44fd5d8cefe54ebac75d49d1663e41a161e451dcd1a66b97abae6b1f'],
 'System/Inc/system_log_policy.h': ['c9e3341261658fccdab5a33ed23c3170327169774277cf66232635a75f386737'],
 'System/Inc/system_navigation_health.h': ['2de09d7705c2f65d62ec9f46b50b6f223552e07c7fa6c5e3061019e0225aef5b'],
 'System/Inc/system_navigation_profile.h': ['944f94ef717332d876026a0bb120a7b759a3ae90e0f40fce87b3c9af315499d7'],
 'System/Inc/system_profile.h': ['90e2c3f586321be5687cb9a382a11b5f35dd0a379e811198801707360f573d2d'],
 'System/Inc/system_sensor_status.h': ['a65a5555201702cd57a9191f72ad70ee7bfe57f48b4c0f623fe6b11c18a61281'],
 'System/Inc/system_source_selector.h': ['eaafdfa4c77fd8d423cec680b5c4ab4c732e280d0946bd4804614fe783997d35'],
 'System/Inc/system_startup.h': ['3896cdd9e7cf451e248c6707ab091ffdffbab42b348d1d786308ba7968a1c0e2'],
 'System/Inc/system_task_stack.h': ['f31b1ed414e74a9e4692cbb3bbd6a9b3cf605bd42b51293ff2d92c65ce64b854'],
 'System/Inc/system_time.h': ['de901ee5021a94091276b6dd72c6307d00682f5d19ecb8046ed91d92484d1b6a'],
 'System/Inc/system_version.h': ['6b9bb8046d42de48e01ea88d011487426ba08288bb75981ce840aa6f3e3bd115'],
 'System/Indicator/Inc/system_indicator.h': ['cc065e5e5a6dc181bfa252b67e313ad2d85a8d1d028144cb802b6fa2c532584d'],
 'System/Indicator/Src/system_indicator.c': ['13b437384c37848b81e1a5c00050428422a64ef488237b36ae4b40daa7f6d83a'],
 'System/Inertial/Inc/system_inertial.h': ['dd06d94336c41cf4f31faea816806ec2d0b7b8e02166a6d039dc6d12adeef298'],
 'System/Inertial/Inc/system_inertial_source_if.h': ['e27d57ccee88a081d1b6e534e14a3bbc8813dc4773771ffd741a575fe1509394'],
 'System/Inertial/Inc/system_inertial_types.h': ['99939ca3790df0f313786c829c8071f642d93a871d4da4c1fb9f88b4c77747fd'],
 'System/Inertial/Src/system_inertial.c': ['973ddd7325eb238db624f19dfd04581d275d78bbaf27b84b4bd427413f44260a'],
 'System/Src/system_barometer.c': ['2e0e8b17188943f9ed10a821013b467fa7f8e183275e938a1c227c99e3c69964'],
 'System/Src/system_barometer_cold.c': ['8d90e9fa0912e199b71134875cbb595406c56ec43ad1746c190725c717999f4b'],
 'System/Src/system_capabilities.c': ['e47cee067ec308f6f977e717091ec81ada1a17296792d34001fe0881fef933cb'],
 'System/Src/system_console.c': ['b79f755b53690efc4862111cc46090879d8f4e6d0f1f1b2b4fe98639c65dba0d'],
 'System/Src/system_device_startup.c': ['b1240b9a65b137636370c0830980745480da7883edc3a2f578bfe868d5f8b0cd'],
 'System/Src/system_estimator_diagnostics.c': ['81b0c038aa6b1371299fbd424054e19fd47efbe8cf303c010cd6c88375e88c59'],
 'System/Src/system_estimator_profile.c': ['029b270b6d3f5fb1b6000a745f633f661876daae28a41beeb44367978f8d1aa9'],
 'System/Src/system_gnss_quality.c': ['273ec377d1849d36054f8d5cc7e84471c9b878826b9b7b4618ac7c10936deb15'],
 'System/Src/system_health.c': ['3d2aedf992272fbfff7e586415ae58b8ba75fb265b46c584bf9a3bfefc642577'],
 'System/Src/system_log_policy.c': ['1be6255706015c010512cef92823f1b17e7e9e0ec6564707c8fa47c7dde0e507'],
 'System/Src/system_navigation_health.c': ['a13c6d165e15183a74b8a3132d9a4ef2f6327bb4e84cb6a0448d716597edfee1'],
 'System/Src/system_navigation_profile.c': ['7d237564655e6338b1de682393fe813c39ece1b7ff5b1f3d27436118172aad43'],
 'System/Src/system_profile.c': ['33fb4e59ec64841d25356e0ec2b60e4377fe520106914abf9acfc4f410aacdd0'],
 'System/Src/system_sensor_status.c': ['f93b8c57df7f465dbc135d228eb59d6fcb1418a4624b071ff4c2fa4d7a6e6d03'],
 'System/Src/system_source_selector.c': ['899b233cbb6ba3b7d86eea8e4207d2f3d032e7a6a42bc1f5a60315ae6738a468'],
 'System/Src/system_startup.c': ['0224f6c3c6d6ea926ac7ce40d87a87fa5e785d2f82ab48030f87c69924df4001'],
 'System/Src/system_time.c': ['85bed63524a052d6f7f713f76050ea9490efe43c4c6b72a486986c0c8f421b12'],
 'System/User/system_user_alignment_config.h': ['dd905b4ed8ade7901396776c2fc4fd866f77ec7855d2f745b7fb91774b773349'],
 'System/User/system_user_capability_validation.h': ['c7df18da594bd7d91c80050bcf1d6976f52d1ccff5120c17a850b893e2f08567'],
 'System/User/system_user_config.h': ['f04d00e903a59eb854c4cd65b752be9f654b3b0d621815047960ab7f626effee'],
 'System/User/system_user_flight_config.h': ['a199afd3efd76605689fa960dd7d346e6f40e4f5e8cd37c737685f601b654a22'],
 'System/User/system_user_inertial_config.c': ['fb38f178e07cf79d22299cd7c065ee5d66e540c8dd84ebd38e934e49bc012f47'],
 'System/User/system_user_inertial_config.h': ['5c1f98d3ea600903b4e2d6cc0d8e3fc616103f2ac67de01ee84365088f32b727'],
 'System/User/system_user_platform_capabilities.h': ['b9ee041df54a4667232adcab28154f13deb7a0b59e699ed822b6475674b0e94a'],
 'System/User/system_user_startup_config.h': ['64792b03026b28bfd728841b7c5adb609f7f9dfd9bc826ccb755f7926efd32e2'],
 'Targets/SilverStar_F103RE/Inc/freertos_target_config.h': ['5f3be13b69c834b884f12916d20b83cd7a07c10867d4ad989f968aae69c46103'],
 'Targets/SilverStar_F103RE/Inc/platform_memory_target.h': ['a9b982e4c0d854660a26217f713a84a3d850593f5625ce5abbc0d3b4f491691b'],
 'Targets/SilverStar_F103RE/Inc/target_build_capabilities.h': ['0a85dae71a6c3582a5d5c6530f6ecff0925ac82d503262a46c8e04ac54a158a9'],
 'Targets/SilverStar_F103RE/Inc/target_system_config.h': ['c85995d4441f337556506945e2e6e26e7d999a24874c532cac33426c95127cc2'],
 'Targets/SilverStar_F103RE/Src/freertos_target_irq.c': ['3ccdababc8abd9475ce116e3569e5707d9cf07b4dff90c65d6d50d27fcd7c211'],
 'Targets/SilverStar_F103RF/Inc/platform_memory_target.h': ['05b1fe8fccdd9b14c6851a5cc09d4642595a4a9bc01f1f090c74ed1765d5f312'],
 'Targets/SilverStar_F103RF/Inc/target_build_capabilities.h': ['f0fe3084260b26345d91146dd2b59c34fff6272b5884b29c05dc45dc92a36e9c'],
 'Targets/SilverStar_F103RF/Inc/target_system_config.h': ['5f8ec52d52818eb6defe5b647d95e67bb9cc344d34172654370b6d15945a8ed7'],
 'Targets/SilverStar_F407/Inc/freertos_target_config.h': ['476932b9691775b2de598d31c7c9217a360561deb78042cd64514e0157257e6c'],
 'Targets/SilverStar_F407/Inc/platform_memory_target.h': ['1854e7701d5895e10b119083b42c748898e69178c59fe2a2686a17095185ed38'],
 'Targets/SilverStar_F407/Inc/target_build_capabilities.h': ['799134c4337590bcebdbfe53dfb86e81dfdcf36985cbf6916b53c3ca2a2f9e26'],
 'Targets/SilverStar_F407/Inc/target_system_config.h': ['9d35ef271c86232e1cd2693441584083ba2555f20d17d73d424592d1761fa826'],
 'Targets/SilverStar_F407/Src/freertos_target_irq.c': ['e4d1bfa43daa2513284b2cc6904e3f4e8dbc60ab11a6b07ea13a757e82e5f37c'],
 'ThirdParty/FreeRTOS-Kernel/include/FreeRTOS.h': ['b7a2b66e0752a9ee44f4ebfc34b39f067967cd0fb2afa24f49ed855d0316f8f4'],
 'ThirdParty/FreeRTOS-Kernel/include/deprecated_definitions.h': ['28fd296f0366339a1e646a00fc51f0456c3b9ed2e2ab5b6d795ac0e27ca99eb2'],
 'ThirdParty/FreeRTOS-Kernel/include/list.h': ['81fd1a0d3d75c54336a8c6ccf6d6afb6a3cf7fb6c42997497a603e3ad30726c8'],
 'ThirdParty/FreeRTOS-Kernel/include/mpu_wrappers.h': ['c43dc990b795aa1dc10c4a9744d93f20adcfe9dd228ea3b4cde6beaf4f041181'],
 'ThirdParty/FreeRTOS-Kernel/include/portable.h': ['76b713a03bec9a43faf260632676bc4d7daa4a1febc0ddf0dc351707123d0fe2'],
 'ThirdParty/FreeRTOS-Kernel/include/projdefs.h': ['fce85fc9cd622212fb622f6b5a04ec98ac54a5e3f914f11f4587f70d5993185e'],
 'ThirdParty/FreeRTOS-Kernel/include/queue.h': ['f94a5d84b0d9359a8ff1f096f557746fb6e32e8c1325bfb33ff334dc91eb3c55'],
 'ThirdParty/FreeRTOS-Kernel/include/stack_macros.h': ['7fe59a59cddf9ed4af9da3904385125636c76adff9897631c4b55139d71f87e0'],
 'ThirdParty/FreeRTOS-Kernel/include/task.h': ['db9c21bd53a89d0bda740504c29ed5c76fe75f21d7e9621be8dd8b0d0bd9053e'],
 'ThirdParty/FreeRTOS-Kernel/include/timers.h': ['f2f36bc850221d9077492d83ebba095961522677a80d76d9af7c28283887dc43'],
 'ThirdParty/FreeRTOS-Kernel/list.c': ['1a559a55d7b0b67e6ca1733f6a4eb42f707edbb981dd599494397f2f832cf983'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM3/port.c': ['6bdcc6e59ce2a63b14ddd4816af800efc019f2bf374962a42b6e6567cc754651'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM3/portmacro.h': ['160f89be7391541cff5efb5eca139ab2e88e16a7989b39250493a2ab78165982'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c': ['415481bd5077833ec512e6a9a73d568ab0e96a48395ff67584b889fa6d017b8c'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/portmacro.h': ['caff90fcb520c57de4c4b8ffdbd1a119384e972058bceab4e2ffc3bc6f4ead44'],
 'ThirdParty/FreeRTOS-Kernel/queue.c': ['101b2653a9449087801e212fff75ca0a220865557f0c63f7ca7b5915a94ef842'],
 'ThirdParty/FreeRTOS-Kernel/tasks.c': ['f6eead187c1b29ac5185c972952adfbb8154be0a4389e6460552911469104166']}
BINDING_DEPENDENCIES_V2 = {'APP/Src/app_tasks.c': ['43788606778a7eca77acf32a418371c62d9aeea9b2d5f924aef5067387798a55',
                         '5996b438a704ee38e2b3fc4fefa423246b0a67f91521309f7990dccff5ec4698',
                         'f2449819cac0c6af7690429aad8ccd7b12d3ef4c26f13e46a635c0f5530226ea'],
 'APP/Src/device_native_log.c': ['4377a1967475c3ab9b87521040c4c89813486638a73c839a126b3ef19a5a41e3',
                                 'bdfe7371026c0f398234974cac670ba498920392f430190600665e81adb7cd95',
                                 'ea1f5aee3ef530f312e27e70316faa91d3602c71d9d9e80b76d2c413fde26e19'],
 'APP/Src/device_task.c': ['0d4ce42a1d13a6f1eebc59565286fdc341ef6a970c9fdc69743392f9037b2960',
                           'c732a23664bd6e6c6ceb331d3372fc1cac5fd933d2c1e2cfb03d03bb8ca7c404',
                           'f337c76c9d8cd17a0dcf516fe19ea9707580c63e93c916bdbadc3cd6924a0f83'],
 'APP/Src/diagnostic_log.c': ['9485625cbb6ed4d160302851e548a33aab67e4c5b6fdf4d8dc25f46a2a1ab459',
                              '9c6ecc0b3a212ea7ff73f9003929a67a8a616e048f69ffdf2d1cc251dbb9648b',
                              'aab79a3c95226d5456d07eca0772d0e5668575e8b7809d8f97bc6238eec07a69'],
 'APP/Src/estimator_barometer_pending.c': ['68343eeaf1c45c43f374efc54b8baf17ecf7d70d1544aa1af77b7d0399cfb9b8',
                                           '803a7255f4291bfcabbfc1b1c344dd63a0288ae3fdec545d2b6a74ff5284c71f',
                                           '8979f4865e92f6f5b39af909b062a7665c8698131110551153fc7f8051e467a7'],
 'APP/Src/estimator_bus.c': ['15ed1102b814a898b0aeff61021a44baaa963c1ce94a6d7b6cb158779d99aaf5',
                             'bfeeab1bd01eb5ee11ee277aab2e1fcb359ac8c4b48cfc82234c2f530cbc95e6',
                             'c99d97d35b3c589dd74623df0fae092993f9c7e26828d3a421b7eab1c63156a1'],
 'APP/Src/estimator_task.c': ['1db41db52caede3c25f89b8ad485982ddcea0458401faaa543b81b4fd4e4edac',
                              '93363191e3c5ec6be884af2caab6c083782c2205395f232c5b16ab71316cbc66',
                              'd31ba09996d3ebfd9b3444be6c2660ca74d9d57cb079ee061c1c1b8b3582eadc'],
 'APP/Src/flight_task.c': ['00ee5b66f6a442955c40a6aead057970a4a7a75274b5897e422a0b1d6ca1b25d',
                           '43b46d8092b5ede8f12838b6f34081d80cd9a3191ee545c6d76b9f502954fb35',
                           '598ec462896cf9a9bf111c3eed6d8c7ae3b2c9677f69d5449b2bc4397aeaea38'],
 'APP/Src/imu_sample_bus.c': ['10954f00fb81b791c63bed63421051636b13419158d35a4ef157ff689af666b7',
                              '6bfc906d7ac21e30e01eec7cc8dfd7ddf6cd80608cf534021303f5c03781ac7d',
                              'fadf5e104fd39a5adcf86177da9fcc25456a91b00e720671840a19f875d48f92'],
 'APP/Src/ins_task.c': ['2c3aaeb7057d7d0a911659859a4c5b929c13f4b9dc7c7c09a17ac14f9b7ae2eb',
                        '658e4e8ef1991dbc833816359b648ab897a0f027651a48a32ec2e8de4572dc9e',
                        'f8efcba3290af2fb8226251f7cfd4cd1ff73b91ad9670c9ac4d3124364e85054'],
 'APP/Src/logger_bus.c': ['b15d9925e520088dc34020102e5703e3b36d17ecbe6bcbbf8bc1c0e470dbcb5c',
                          'b74337c8d3759001a2c08ca54b9f10828a14ceede438ecdefc7a790820621a22',
                          'f262d03c6b9d6209e5c65cc126a3f68d4aefbbccf581fe140d2ed8e9870e49a7'],
 'APP/Src/logger_task.c': ['30860df0971007522674d43dc2ab5b39629babf535d4a228cc00e5ef543b5f67',
                           'bae87570f6072d651fb43431d2534f31133658c3630027e3471d2d1ff9ad9fad',
                           'd14e26a6a16e4a6567c0d6e1051626608e6ccaa2b515d60a3daee352b067aed4'],
 'APP/Src/serial_task.c': ['3f39a5dfa9a5fab45943b8c530c32201a74dfb03fee9b519e84fef069622529d'],
 'APP/Src/telemetry_task.c': ['2b5aedda9f6056540e17bd588670d78382314d1fca66ec835f0aa975674d0739',
                              '5a6cea2c145b41d95f85b2dd48413016fb615139aed3fb720253355b497ea1bc',
                              '77cd5bd82bea30da2246ddcbc2fa0a59dcecc3529bcdeca85e0b3893d539e3c8'],
 'Algorithm/Alignment/Common/Src/attitude_alignment.c': ['bd89c7edc874817ee8f2079a299c7e6109cbb5113db55f6e0d51fe3043c484f9',
                                                         'f0d7deb9be824b02ba44ba4ab8522e5a3d36a0df4373e0d0ec0a6d23e23ad672',
                                                         'f45661ed1755b9a8fcb21a1faf27b5d6fa8e6a56596a0cfdf5fd4d30ffeb7480'],
 'Algorithm/Alignment/Common/Src/attitude_preflight.c': ['30f20f3ed1808a86ff982a6ae67f6f5f70ec55d4324cebed2106947592838559',
                                                         '6a39fe03a67e3b3e61a10084d2e08f3c2f00ce89cbe62dbaa947a4555cd2a31e',
                                                         'd1661eb43b8db8884076fd0408281c4b09d058e2afd56f20fd42c9cc5fdd34f4'],
 'Algorithm/Alignment/Common/Src/vector_constraints.c': ['3c23358d4dc45b8d18a87c1585223920d0ed8d098eb01d987f8888848cb25c9a',
                                                         '7727183557a39a426a167452b55b5d72593873968ba33fd0e2e2b7627797818e',
                                                         'f9b1ec421547389483f2264c5965f3f354818017602b9920c04de3720eecd888'],
 'Algorithm/Alignment/VectorConstraints/Src/alignment_strategy_binding.c': ['372f161d41bb79b99c4ab64afbb1c1c356412fd3e993181e553a1b10e59f0b54',
                                                                            '6ce48c331534dee2c3701f0836d671ea04f2bbbbafcac01f22f1bd6b6b0bd291',
                                                                            'c1578ec95443dd8d2d4ff3c7bd4cd81aa76ecbaab3966a4eee9e894b137edaf6'],
 'Algorithm/Calibration/Src/imu_six_face_calibration.c': ['123a38dadb2f49c6dadc70ce8d7d800aaed7a2a45cde17a3f421df33bd27df2f',
                                                          '619ec8b3144a383fb6085bca653360c8f4e6748eb3f25023d6ea4103d2b9542b',
                                                          'ccc8ea495aef131185b0121f55b76adddbd04bfcce4b491f177187b29d805360'],
 'Algorithm/Common/Src/attitude_frame.c': ['443e6ee4b392e75851abb5f58add14cad1f8d78cbedac8b6dd0552a94e36a9e3',
                                           'b36dc76b08be44f6c664857e6dc0d6d5f982b28eae8d1f8fd7341d826fbda3e8',
                                           'dad45bcd56d60a60e9d9727c8a839d707ea315a415f1e91da6c49d6409140303'],
 'Algorithm/Common/Src/geodesy_local.c': ['25ed5229ae39be7df0785d949c342dff256f5fd2fbe4406b9d0446f9623121fc',
                                          'af2e5944ccf98d8eafb2e8804cc611f5d77998a581206c0b7be4230a892ab316',
                                          'fc61d64e68f8212c04bb9697f8d21f1c193a9eafebe82c160bf6f2c475b5e500'],
 'Algorithm/Common/Src/navigation_quality.c': ['e16863a7d722086ed424635e43cb098d80c755954d58702f8cefd3fee4724e45',
                                               'e380557329e6e88613bb312483f57a51c10322d1b1a8737d6733c9b4c892e4e3',
                                               'f171d1ee37617ac1245b7efd4fb969bd57c683ca81836966c70c07b5f575bba2'],
 'Algorithm/Estimator/KF6/Src/navigation_integrity.c': ['1fa7b87471096bd83a05003eeb1e259491c3acaec2e7f4bcbbe2b5e27c483538'],
 'Algorithm/Estimator/KF6/Src/navigation_kf.c': ['f439fa6a1aba50c33dca62f24c338f1e55105cf7e29e286e32fdc3e444a68ed2'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['3e6fe662f073de5478469ea69230d11d1fb57ca6cd785869a74c4f2430b3cbf7'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6.c': ['ae4e15f5c66fe7c72e897874559a19b78396e812b463e62a00d613cb0de934dd',
                                                  'c5e0889d1a677f808612fb46bddea85a8c882f01faf0d0dcdb6fed2ab624cf50'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c': ['56bad834c541227e9c56442a2b4a00b0f8521401200d0ebee36718b5bef304bb',
                                                          '654e1db465cf5fe2869f76ad39ddc60a097097f6797e415b44eb4f94c52af5a3'],
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c': ['539fe69bb57069023ac8db95293f4793497fb31ddc4701547537ce3da7a120c2',
                                                            '87f67941b5632de14fac38bb1ec6b596737cb4d77276ec5b22d672b14c9396e9',
                                                            'cced07fac51be5050cc8c805408060d97031058b0968954bd06c828f61ed0b51'],
 'Common/Src/common_format.c': ['20029fc8408dd68d39cfafd31e0052515dd657c6737d891e0304c90e6e738034',
                                '8d257ed80bca3ffc886c885cceee27b41d2ae6e37eb5d3a023f2cc32601d6f5c',
                                'c1be864a41b99580ddde546c369b9a5f0b9b7a98a766638902b4024c23ab1693'],
 'Common/Src/common_ringbuf.c': ['6478d2164fe272fcaeaf7d90abf0b32e827f77b3aab7e9c0547aaeda5693a662',
                                 'b3d51ac8ce5b6d6749644c46072047e2988db3754912c1c7b255709f02841049',
                                 'ebca4e1d53b13f3b844e980c7f25db4905ecc02a6e078f5cadae8343a4e3af84'],
 'Common/Src/common_spsc_queue.c': ['c7ebc00d44293011ebdab50ce95896c89d8e30958bbc9dac5987047697d419da',
                                    'e1f26e81481ff30757aa46c78779a4cd4d8def07237bd44b65383bfa400a7925',
                                    'f1f909330c1ce69b836a13f4e62aa362a93c0ca6a38af25d42782462e11d0e83'],
 'Common/Src/debug_log.c': ['41fce858e77d592d777b64e7c8067b1edff9e900222fe71d06c050205d5a83da',
                            'b213cdd2ed5fb7e1e50f6a12e3f61781b13ef6daae973262d800e596ff008c9a',
                            'edf2b347c04dea1bcbccd867ffb9565332f5482b7c2af1e547e16834db5e50f3'],
 'Common/Src/silverstar_assert.c': ['72b64d054567c9d8c316537d3a69521c1da0fd9c80eda48015a491a9b43ea340',
                                    '759b23fb325b8e232a2e2b8d08f9811914d52028d355f4ae88dca5e45306d8a9',
                                    'bc6f3300cadcc953de2210e635d21dc1930743650a4b0b06086be5cc45252e94'],
 'Core/Src/adc.c': ['8e027c5d6efd936959e59f3984a2bf2c9af402314edfa46e8698261ab84c86f7'],
 'Core/Src/dma.c': ['943205e7cf9c60c8c9003b0563a9c80fab5d857d9d5d7af42ee4738de269a174'],
 'Core/Src/gpio.c': ['ef4a5ebe59046a7e6942cdffcafc69eaa1675aaf2bd089586b77c94a5ca16eb6'],
 'Core/Src/main.c': ['d4ca3c9cf57e142a41a9d3fa12c09cc9aa86dfac8b6e1900504a8bf2bdcef020'],
 'Core/Src/sdio.c': ['889c0fbb7fa5c3bb0da528ba880c83705e2fec953256d1ec04e2e9461dc26646'],
 'Core/Src/spi.c': ['4433db67f47c36a74df381f01fbea22608c741cd89913998fc1c28d7bcdc2b59'],
 'Core/Src/stm32f4xx_hal_msp.c': ['b3c31dd5704b914f422977bb8a1e609b3329335adc1d1196e7e920f14de9f45b'],
 'Core/Src/stm32f4xx_hal_timebase_tim.c': ['a89465603baf747261f25f924c0c2989693dbc7ab9229f9e1ac2d618ad659b5e'],
 'Core/Src/stm32f4xx_it.c': ['c908529849c64733a83c34ce65c1ef93d1296b3db5bb280b138e1881393252cf'],
 'Core/Src/syscalls.c': ['a7753334de3cd41d3f802b7fdff0860f5340b048d5cb6aa0f2db988b2d99dddd'],
 'Core/Src/system_stm32f4xx.c': ['4cc0009c028c1c848919f09b7002f7fa83df3d734503c6d9dcb3168ba456c299'],
 'Core/Src/usart.c': ['f6d27da430f041c59a8bb4c6af3af7490a0e88fdbb667cc815eed3830fb1ca99'],
 'Devices/Barometer/BMP280/Adapter/Src/bmp280_adapter.c': ['872008529f97fd090d81036e3968cf59a3fcbda16859467d8d8a98d82998cef6',
                                                           '9c23df87ad13f6d7e655b60826994d909b0d694538d207deb2f918f696d56e98'],
 'Devices/Barometer/BMP280/Adapter/Src/bmp280_i2c_instance.c': ['84182615184650173ffbcdc8cb2028c63c9a85a7047d540569b815124c63e5cf',
                                                                'e1c3acca5e13795a29bad50a2995f1eef79f774463f7022358aae6fdd52fa214'],
 'Devices/Barometer/BMP280/Src/bmp280_core.c': ['abd5c9d3d568d03d2feb44504f8d31cee97f4e157e87c6e34e42369fb9811098',
                                                'ebe17253341cc8fa63ec35ec3f96cdc50899f36e52acfbde2d0f93fc6163e1e8'],
 'Devices/Console/UART/Adapter/Src/uart_console_adapter.c': ['af589d6b24958c81dc67f72992ceab84320a68601489ab3ccd07b22f104534f4'],
 'Devices/Console/UART/Src/console_uart_device.c': ['3bcea1e6e6039e4e05238b7efb5d564663fa67fbf577f486ca8e472bb3c846f6'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c': ['702079bab80dd6f3e458ef4b69007263cd2c6948babd9a9e7954542db74cb6e5',
                                                        'b367c66dc9f54aa94b44aac086beec1c59c355df9dcb6cb5170f53751948be0e'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_system_adapter.c': ['566473fcc02e6e2b0bee4c2a53b497b68b9e88a40cc8236030460a003fedd907',
                                                               '71313090497ef2b1b26acb85be07193ab8f8c393620017615d1bfd24e84e744b'],
 'Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c': ['14be63fd5fc128db4a3066759b2f0c49b805efdb22be68568d754b685ad35a1a',
                                               '429583d789ee494ea9b9eee391baf66afe21e81df5c5cba2842345fea290ce6c'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c': ['dd415cfcb8599b6c926140475206f11f9837d8764843242a5ddf51c85d606ba7'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c': ['24a602cc27a6d70deaa16ef7a8819a3ed0e888ecceda0ddb06582b5b747a3f28'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c': ['7228598c2f2d90de5af9836fcc51ffbda32e82765b289ad60224f35fbdc68f65'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c': ['f5eac2160f09fca75b323dd93f115b8b0259752eda15768e512374192f29f12e'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c': ['00d33140045c4797075b7f9bfbc2f75fd5a87807b3100aa0d4556c1b1dbe9c00'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c': ['f3905e284a3c80d76c0698ec21f2cff277e1db9f62f303b58e7f5dd455605971'],
 'Devices/IMU/JY901B/Src/jy901b_device.c': ['235fee67c23f922b02c8cb19992874cb6521abe8467e0fcd38e0397eaeb0f083'],
 'Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c': ['05128a1db4da5047118d091e476c507202657590fd66998c5d19d9a858897a4e',
                                                        '41ad90e8669a86ce6b05a7a6704c7b207cc1c67b05bb4202d1580594c9ee88ac'],
 'Devices/IMU/MPU6050/Src/mpu6050_device.c': ['897a3b48b1d1f118c7d7d22a30ac14b29816d2acc5b098d0faa7e2d9227acb74',
                                              'b9470d25d5ad6864ee87f572faf6116de55643282fd009a7ac569d586bc1c7ea'],
 'Devices/Power/InputVoltage/Src/power_service.c': ['b78ae4a7ccdde456c6a48bc63269932827a7edd3a9bcdb438b3e525f5fc617f8'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c': ['1670693c262cf1a6d16436cef52e9d6b9f5578c174e099e7411f75e4d718f61b',
                                                        'e6e4e98ba48384451f2d97eec3557543c4e3229b6ce641ad4f6c4ed7a9834114'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_spi_adapter.c': ['4433de719cc43f435c16407db78329bbf28b967213160ff24f0e329eea2be904',
                                                            'b6b26a4977d964d9ba4444e8c561dd3db613f4cc422a3ce49423705955947cd5'],
 'Devices/SensorBus/Src/sensor_bmi088_fifo.c': ['37477c3a7098cb656813e207c32875827182eac606b4b50ec5c06359fe69ac77',
                                                'b1e897b50141650e04e988ee781e424c3894f9ea55d92d8c9e7c69efa2b30f44'],
 'Devices/SensorBus/Src/sensor_bmi088_sync.c': ['b8c4df7208ae0e92feadab9c0f48af74093c5bf6bf790e2ebc658cb00ca9a5fa',
                                                'f28351dbde88a93db0356856a9a65e2efd07dda6531fa20b82a97e958cfb624a'],
 'Devices/SensorBus/Src/sensor_high_g.c': ['081f59bbae06abacd9285577a125d417dc6e2cdd0bd042ec08ffecf3e0332217',
                                           '405d8a6531eb4ac11c55771c7c5114617729ff9b8d27dc8270c690e1ab8ead6a'],
 'Devices/SensorBus/Src/sensor_imu.c': ['2601ea4c0e92cc4928099ababe3506642efb350cdbb0e9da0860eeacdec65cb0',
                                        '3e12499df21ddd80afee940c22093374340283fb91a8b15739753e62dbc5732e'],
 'Devices/SensorBus/Src/sensor_register_bus.c': ['0eb94828a6ebbf112473401a78624846b31d1c1c2b4d694c382ead786b6b5f42',
                                                 'c940880d524401837fd49ed4e1fd991c48f6e19068f695d040935f6817122cb4'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_sink_service.c': ['75007c3909cc74f0b85bd1082cfb0f70868fe5dc4668f8459d6c48b1a8796187',
                                                                '92fe033e997b9b5beede7f024f0eddd23c2bfe71657309e65792571ef7ee3710',
                                                                'a8c0e2dfd1ebcc384df9901bc93fe731d5ff387c049a827c1dc7129540afbdbb'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['5d34988fd88dcc9fceb8f7d51f2b3264964e3df84ffe67ac6d74a5a84406e5d9',
                                                                       '77a9a7b63bc1fc679498a0b69bb4b7d456c5d57658c7866dadca23f72a2fcf35',
                                                                       'f655d63778f40aae04e093832782424d56857ddf85728d288630557a6d4d70a2'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['4393425cbc458090b643352e47d18adf19494a901c63e1b1ddcd2ee4b56a1e0b',
                                                                'bd68c016777a7753be13aaa6f24de7e50d184350550210a4896e63238718b828',
                                                                'fe8c8623465fb5c0c53f14fcacdb68180f2562ea6dc793246b1e1f5bb68c1d1f'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c': ['1dcc9ecdfa83cb296aea94930ecfa2c5b7487b4193a34326ef7a853ba243725d',
                                                                  '492670b34f5cf705fb51d81a65e51d6e406dfa3d6d134d65c307320e2a3507f8',
                                                                  'b4cfcd1ca9338a7741df62c8d4c3d3a9624db448027681e3bf1f589fcdc00c1d'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c': ['6d97c9a1909dcd18c5e11f18a0a168223fbdcf757c36044cc5e71f45d3f7198c',
                                                               'e1bf5188377bfe5cd181e9669be9af486ac9c23dde66e161e1f91fa3438b4e88',
                                                               'fa90ca1b8a9d2aefa49b765afd48992c90e479a7ecd16aaecf72bc36d0ef57b4'],
 'Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c': ['30cb94555cc6f513a892cd516f0b0d0c8dc0a139d2ef27ef003b1f2010efe536',
                                                       '5f312b1faabb05a80e7ed032c94ae3faee589bb20f78eb04c1668767ef917120',
                                                       'b324ded6819d376afc6fd06680d0871b52e08a5ecbe78c95c5f02761c4ea62ab'],
 'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c': ['85dda027717909d59b2b1b4acfa850a63b804d80b70220dc58e3aac079ad8ccc',
                                                                     'a9e7d67ed71ccf866827e87e35f9fffaaa927670b236db6d3955892b31e821a3',
                                                                     'f0acd7212d5890038212841427d5344c30f26073684c654a4ab7feb25fe4f1d0'],
 'Devices/Telemetry/SX1281/Src/sx1281_bus.c': ['4a878e5bf632c9738a0dc4814264abae7fa6354bd3eb313632f448571c321ca4',
                                               '948d4be23acf0b87114d1ed32aed898b4c078ecf11aeb19a5f6f0d4afddcd679',
                                               'c7da84b81e73ca74204e87616474a5c1cf22bf350166d4a84806150ba65f07be'],
 'Devices/Telemetry/SX1281/Src/sx1281_device.c': ['1f84d2a7824663a2e624ea5bb0046e587233f41bbbe5ab95116eef4c279a897f',
                                                  '2c7ceb6403402f145156970da8357a630168cb41a296a8b2c5f1789ac30582da',
                                                  '6c7485f64b8bae1bad802b2acbe183c050318a61808f1724870758fbb20b296e'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal.c': ['134a65e07b97a147e2148c5a87e2349a042fdea9e78864cf6072f18d43431540',
                                                      'cd4f41765842101348e45c0c076fcfce515eca4b9bc1d5b246fd1511cbbd78fe'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_cortex.c': ['1a85d1eeee26030a917b47102b66ecc1f8d5d4fe3f6eeeab6a68febe31c89695',
                                                             '531707dc6a30f39d07314e4fae77f48f26cac3796534e29c98e9a9188793b370'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_dma.c': ['1bb75f2d6414a6994186c42ae4f624595a643abd45b109dddd84e7170c74a647',
                                                          'c00da3434e82add5a5b4c76918280e30682b609d488511d5ab28d83e20444595'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_exti.c': ['7f86879c46137891ba352226d0cde44d74d0b00b92785f89135e5fc7210ad11f',
                                                           'fcac2188d387110d02442b4dfe6903118319ad2e3ec9924676138633601b43de'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_flash.c': ['5f0cd35b8109b388a940eabcc0287c7d395b7fb814a8a776ecd2fbb8f4c4d581',
                                                            'c9e73e3ff12c41364160623adfd89d325da7bcdfcc970559aa6dd0897794c7e8'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_flash_ex.c': ['89bc7b44593eff7b8f8671b73848b89f2641c09232c8f91d2fffc6678d95cdc9',
                                                               'ad8ef1a813cd1f8523a93380a444eb468d33803e00993a57b6c5f5c710c1b010'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_gpio.c': ['377bcd76f3a1e40eddb7c12ba19ecb75cf88e6bbe7e1df1a4203c71904787a4b',
                                                           '57d6bf21834b374ee37f20f1619638b187045cdade28f10c2f2671e348545239'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_gpio_ex.c': ['015adb747c90a41b1e411c553ee62afb99ff3a9c28ff29e3e9d0df5aed3fd90c',
                                                              '5f683cbd2f8672c6cecdc5f5f870dc34653ed5412be874868df19cd4c9a396d4'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_i2c.c': ['35e4489bb62eebe5a3154ecdc19d5e6b33d6be2e51acb70c900139892f21f86a',
                                                          'b1e57bb83d1cff8985f2d7a0c2ff55cd73cbf47b2fbc259b3406bda1de33fcd8'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_pwr.c': ['708858d83059c0d7c4fb626c9bca44615fd587007f85f7a9a417d5cc3898dacd',
                                                          '7555174ee06cd38e350faa62125ba84240c12b19064fac48b05f49a5be45065e'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_rcc.c': ['58597f4d683abd2387281956d20235260fefb3cd2f0daeb550d6dd849587fceb',
                                                          '8461030f111137dd463bc00835c458d229258ebc36987cd0faf8ae43400a3e54'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_rcc_ex.c': ['28189af65c2f04d5ae4f9ba397d671d527af2ee4c3de2312daf82731768b95c7',
                                                             '5165388472df2361b0431d6ce20d45208f624b3f352bdef20328c69c388c7be6'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_sd.c': ['4153f166d42d500a8745060432178ddbd8cf9e270fc34e39d921c939e8d30883',
                                                         '9ae982f00b2d355087a1538403e1d746f72c81328af2334a003773bad5cd7110'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_spi.c': ['31545a36d174c4cef3e97072f74531c4ca57d4f0ee29bd2b64eff250f883ee05',
                                                          'ef12d55142377faaf9bc403aacb0001afa4ae04b54cce1ae975c6cc6744d19d1'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_tim.c': ['1c42f062635c3940606a79a5627b61310ed279fe6e026d9ed9440c0347e4e23c',
                                                          '85f431753c1bdcb435605c6e5174e875050c3cd9805e3d3934067c52c32befb4'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_tim_ex.c': ['c348ae955151c4b338715e5d1984596d8c3206d45724637d7903a8bb833f72e0',
                                                             'c92ffb26d72cc21a491b134f2b2b73f73d84a7b3eb164e54eca7c3fd788d05cb'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_hal_uart.c': ['f4b0211c049a48ade329ac35bcde44d54152d7586ca8c122b2a38833364ced54'],
 'Drivers/STM32F1xx_HAL_Driver/Src/stm32f1xx_ll_sdmmc.c': ['4500437645a7c049295b695d97ffdf11ba58d07e7c869da4d538d427b4a7a448',
                                                           'b6e3dc84d93009d4ff2f65acaa6bd9451488831e6ddee7634e9979f9a461fca0'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c': ['892404d676d44e98d1c663087892acaa49f35bd8461eecaf914355d62f620e2a'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c': ['79e5e9c9bfedb365238d81e183b2b7f9c9b4454045a2c071050c1266720c1df5'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c': ['f4bf0e75b7b1c0494db7bfc2c04348e451e40e5d84c898cafd38f1d537041555'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c': ['b46f1b0e5f0a5b5c3c952bd1d74af016aa90dc487d1a8957792db44e8775580f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c': ['c0c41498e5e7f33cbd2c16af983b94339eadfdad48dd633afc712f4ee695f243'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c': ['d92fc7258f77af225bf8de910786c007d15c7ce437eab0a854ea8720257b3fba'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_exti.c': ['c68745aadd315cbbaf05db749c232755888c8583d8e5eda5d0525fad14e4f373'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c': ['e853b8383778a238974fe3a588ba3bea4fcab664ad7909a4f96ac199af280c08'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c': ['a94b02f004ab63deb9a246eb3cd3853e32da9de324ce02e78f0272006d18e579'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c': ['89a35bb0f2c8c7ff51252015664915a2e212ecd9c3d31d6f8e529721e6d2342d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c': ['deafc43c59af8283c516590697ff64d16be19ee68b507f623e352e25a892b194'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c': ['28b0d6fd719f4a6ce4193cbc838d992872f227f7a7933b8fea42866d5eedb976'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c': ['6f9ae93109752c148268b1641427a9054309548e300ba2bb6147fe81e14c2de7'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c': ['aba15ce494ba8d0c7f7bb45a09935cd1e881a299df4c944ce155d51c12dd108e'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c': ['a4c28c55eb3d03b8777eadcf4090f05a3a88e1fc4083108d0cfe3baff76c5dfe'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_sd.c': ['4e7d1ec06b4db18be3106c840eb11d6ffc76fc2a193fe951169aa13cfdfdb691'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c': ['32f2a574a25b6ebdde86799e1eb4dac58d35576cedb58c21a9884bc420749ee3'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c': ['6f9d43a9a35b2de6c2cca23a9b6d7b77df5f895f8618b530dd938e2db518c1fe'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c': ['6a1724e9fada6a3186668fc21626571e39743743afc898ddb862fab0b828a7f8'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c': ['f515d1c49ec58fc02ce57597f3f2e1a1f8b4cc7c15e4e34ce07021a8b39ec4a1'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_adc.c': ['8cc2c248f08aeb29f0d62336ac3a9944351112d0973062df8d8e5ee6af711dd9'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_sdmmc.c': ['21171d3bfd0634e291337133edd29db89488e831f21409ea7f296c59404f7995'],
 'FATFS/App/fatfs.c': ['8fc28c1518a846eef60a508a0b3a3a3c866221de632b55554bdda69494a86901'],
 'FATFS/Target/bsp_driver_sd.c': ['075475e2fcc7c43516cd43275140fba396c7164ddac04d32914bdac8f0d4f61b'],
 'FATFS/Target/fatfs_platform.c': ['62b9ec16da22a6edf8268b7e42515b14ae3661f5c52911ef69b1e9ad9c3e12be'],
 'FATFS/Target/sd_diskio.c': ['c0cde79dfa2ed8db5fca4d323d9734770abaf4d80275fb36a8491b97c4d49c9d'],
 'FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c': ['1438fed5481a30ef0642318a293a07357799626dfe66f50551764e79eb2c446f',
                                                                 'c6e3aacd2f57ab246911b22a1bf1b29796b369ecb3c403031568c753f3eb5819',
                                                                 'dd368fa28dc978b602ff87df6c8f52d582d41b6fc503e174593801dbc2bd6a39'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['664191e2a78591e1b19df0d93dc40e1e2faccde69c70abc8e2935cdca83afe4a',
                                                           '9b151e6653864e2b2151f1b843b81e6160c3b9422f35a09ea34b609b0037d7ef',
                                                           'a4c2f6dc54e7568cf769a1418f5a5569b4110b78b31e0c84dae16f4cb7b54387'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c': ['01d1fbc7066b60282a6ddbd92521416b7cd489ec7a3e40932efdccca989ecf3b',
                                                              '4b50c131a3494397e1b17592395dfb279ff8bec80148708380a6f7c8ec636a6f',
                                                              'f67df179731275409fcce1b13448ae3bbc4c7a203b7946fd92148af440aee99f'],
 'FlightLogic/Indicator/GpioStatus/Src/indicator_service.c': ['0e3df95afab0cd9b5cf3df98f8dfe1a92ad410e62957b0e959a730144baf2211',
                                                              '70ce232ba7fa8eecfd3cc80b89ba7655a59a36ffe69933e76e702ce66c338f44',
                                                              '8589162dda499ecb4396e4870fa176f892970c2fd7b65f735e3c8ac8bfcd7065'],
 'FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c': ['466b7b2381c524b6c8c32345236a2a7f44799f0e8af82e0a90d9117e4b0b294b',
                                                                 '7b1b08baec0fe9cb1c6c21645fd6ac07431bf179bdfef2b9c9d182eec6d8a934',
                                                                 'c6ccd5eef7d348abb40083971ce1f020de2b22ed7a7f0ab34584348c88405391'],
 'FlightLogic/MissionAction/GpioOutput/Src/mission_action_service.c': ['7ddd8705f9daf488634f388ee829f0497be4830c9028d247ff6422bde520d05e',
                                                                       'a6a2768c985b785159c85e811c1cc35886dd7e3d5739af57abcec59d57752996',
                                                                       'a9a03d5156b5ee87f3ee3f9c5af94c82b4b47d764ca91244c14e52ba84d715f2'],
 'FlightLogic/MissionAction/GpioOutput/Src/output_service.c': ['33316a01e4dc81303b4dbe19998d540f56990845efd22e65337a1568244c8198',
                                                               '7be59e2e1917b6223f2b3d697614d6bdb6a7c30dfd2d891ff63c1b3e31960fc7',
                                                               'ae6c219b2689ca11c964cc81fe7a334c2949aa05facd2df693cf0ae7449e6c52'],
 'Generated/Src/platform_resources.c': ['047b80e739dc1120e7f80108185f42ce58c314cf47a87e5d7e0f02fb46774fc7',
                                        '532c0d7c5711c8f7e02baf5aa7a7f8cdff58c7c1c8a5d53aab6fd524200e3ca1',
                                        '8a90b6c34b1b990d3d99e4d7fb1152c952a0727f972d3fbdfac55e6b99f22f00'],
 'Generated/Src/project_capability_routes.c': ['56082665d03ed650842fda1ffa87235632735660a0c8fc332b43bec78670bd72',
                                               '75b0794b9aadb7bc6f85872d398a7b19b655f81c6e704c84e13158f261775133',
                                               'cf074c7ad212d59d8957860e8202f6911b6fb12500ff8166cda9b7e137dd5476'],
 'Generated/Src/project_device_instances.c': ['88161ed197db064e78fd5f1fb72df3afc29e201e7fd9b493debc9a78c593f7be',
                                              '8de5e7dc99b65ac3f38247385b17656efebd7180048236a9dee3bc5ecd3fb06d',
                                              'b80a846fbc92f952856dac5ddc4c00f699516de8882bb59f10bcd46532ef84d2'],
 'Generated/Src/project_log_config.c': ['74a949431b5a487135700ddeccc4155924442e7ba369785288c257df8c0a1033',
                                        '827342248e98e6572772a0bf509b42bd2c351de75f98ef61362ff0b93f50840a',
                                        'aaf2921da1cb4517ae36124e6f090fece4d54964dc4ccd9c3007f815a039437a'],
 'Generated/Src/project_log_decoder_profile.c': ['0732387bfb610c331d448652492a37494c914a0f62d4565c4edd8e802ffb06f1',
                                                 '3611c187595d15f06768075f5dc78ec6668b3a169b1e2a5474004d12af1d2999',
                                                 'feeee4e1b959743721c37e0d15534af0bd7d8a496feffc774ea736d70a389e12'],
 'Generated/Src/project_metadata.c': ['5fd774d73048335568aaffed61054ee55875257f674b9c19f2942bbcb028d6b6',
                                      'b3c436c4e76a94345e6f7e09b190b3e89adbbb5bdddd8f1b1d4522e8ade6f03e',
                                      'f8c4866702b45c615fa76898f605b2e89ac33dc2e0735687ea1fd50783255e89'],
 'Generated/Src/project_mission_parameters.c': ['64853343ab60582941a7ea60352ea0f24e56dac0558d39a93a1ea850a0c1c5f2',
                                                'c397a18f0c790d9174d349848dff5b901fed779ef02aad975422cdae03acb9db',
                                                'c58e2b60e609eb5da041386aa533d26e394bb7a635ee4d55605a0ff98f01d881'],
 'Generated/Src/project_resources.c': ['14fe5bdba31bcb4d56e28bfe7308390ad18187927b1c03b519a0c4f08140f298',
                                       '76528baece9150d089de0bded6e19588b8ff454c964fbfdb2e4b0b11a01682f0',
                                       'b201dbcac9ef74cd47406987f81dc999fa3c3b49efd5b49e25b18464e6bf8727'],
 'HardwareGenerated/STM32CubeMX/Core/Src/dma.c': ['894270dd74c6f5e4b115e66d9ad498dc4c0fd7cd988abe9806046bc3ec37799d',
                                                  'e7462e3497e84b560bbd49aa38e6f9127956f7ae85f018f5d1d1e805ce07bdfc'],
 'HardwareGenerated/STM32CubeMX/Core/Src/gpio.c': ['182111e44e1bf01735b83d163d6be5d5b13828e8e73cb7a8d1f827dd6566e03b',
                                                   '3ed05c9a50167eb8d7393fb7af9e42d14aa9c2f2f99219e24b8c419f644fea9f'],
 'HardwareGenerated/STM32CubeMX/Core/Src/i2c.c': ['03aa824a985e8c539761e59d4ff167d99fd6c1c9b67fee03050ca8e5a3a3f783',
                                                  '72fe39a9d8247051a81bdeb7012a3373db66afbabd3a2032ce95302e8fa29bd5'],
 'HardwareGenerated/STM32CubeMX/Core/Src/main.c': ['61e5f55ed080fb1a59a15254ba43417d271fd37002727ea3fa660de425baccf9',
                                                   'd38d2f95d60fa50dcc49aaf635458b08572c15e15cc21658906d12027ab64cc7'],
 'HardwareGenerated/STM32CubeMX/Core/Src/sdio.c': ['10a26bf95fc54e84ff5ef16cae162733798a0db2443fb6291d21e1ca96a44dd3',
                                                   'e4e55033e3c6fd6a3f9048cb6f8309664cccce747f90a758721f17ad9a817acc'],
 'HardwareGenerated/STM32CubeMX/Core/Src/spi.c': ['696d52b2a40cf162dda2fbac89d9023e6e01cba89006d2e410c6981c29d4a32c',
                                                  'e9df4480e272455d51f50d54b1af7eea816ef6c101073b09186ce2603d7503d6'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_hal_msp.c': ['1f6d0218865994049a80d6831a3713e3ac8bf37645bf3f8cf053fd3abcea71cd',
                                                                '2264f94c9faf801c6326e5f3617e4e14d10e6f2495fb433d5f3ead245670ecb7'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_hal_timebase_tim.c': ['322083b00d420ad3c2c7f0ef465747d7d52b72f52f70677521f0d94ef424a908',
                                                                         '6266cc305635f92f73e5b829d4bdb342541e08ce6e7c4801d50d23731e139310'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_it.c': ['6fc2523495ef3c428f66b5fdbfdbd0cb40bdebd2c2431290dd0dcc7a5f43643a',
                                                           'b473a14006d502f767421fc7512950c58af55fcf4b8680c2cabdc2b2898cd989'],
 'HardwareGenerated/STM32CubeMX/Core/Src/syscalls.c': ['7a395c16ae5852d7d3be001edf78c006ec5537e6e5465e2a28157fa5370cc864'],
 'HardwareGenerated/STM32CubeMX/Core/Src/system_stm32f1xx.c': ['0ebd829354ca973d0ebc9c7c4f6fe5cd590420d15ed078c11df79a031203a7d7',
                                                               '895b866fae30e8c81a85bd192a9cc68731d2fa3a9c5c871144fe9be2f4470eb0'],
 'HardwareGenerated/STM32CubeMX/Core/Src/usart.c': ['9550e0b491e0f4a0a7447f1e2a19311f12310862e0d4212b3591307cac31dd30'],
 'HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c': ['6818a3e3ec41b3c775542a07e624ca43b2fb918e65984e1770261641ecda7353',
                                                     '793f6cd6d4c796faa9735e0d184bfacaa19aa01e2194c727e5c4294437bf1d7b'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/bsp_driver_sd.c': ['92584968614104fd5f267f342fe67c3e13d93da4cb8555c88adcebdc98a42c47',
                                                                'bc6a46222662d7f609231a398a0f797c1d1b08e8ee88b967a32e99709ae69327'],
 'HardwareGenerated/STM32CubeMX/FATFS/Target/fatfs_platform.c': ['15a6b05e14f76aea110775bf5cb40e628e256a6a1396d8b6b642c6493bfa1fa7',
                                                                 '6fa0292eb28a32fcb842d3c8459d886c62b57b6889fd2e9bc46d31cae2339a46'],
 'Middlewares/Third_Party/FatFs/src/diskio.c': ['3a7071e9168e048958178f872c8e9a04e982ee94e0f1fb9e47095043508fcd2b',
                                                '6a171f4d0a62960324d3695a5f163c7687c38b3be8e2333611a896892488d53f',
                                                'e6f1f5d4cc86064ef9b6b58590f7bcd28ece5b087b86c6d46a3cfc37aee371b7'],
 'Middlewares/Third_Party/FatFs/src/ff.c': ['1648dc75b0181abb5e19c52409d9de2458e48769dbb3a46e84764722c50cd6e7',
                                            '9128d331779125366782c873f203be3968be3fa560f19e458aec47c5db12c2b2',
                                            'ac4e6e8fc0b1ac123de418c2308acee8e206228423b2d5613a2401e550361ddb'],
 'Middlewares/Third_Party/FatFs/src/ff_gen_drv.c': ['2edccb3bb6274c0c749d3657fe8a275dfaf5417c4ba2edcb91ab9d29bb5720b5',
                                                    '4186ee1644be00c44a6b6736757796f5caf7c7a7fcc4faec98384facfe3db0c0',
                                                    'fac0e87a39a48e96a5db2c3300fb603aec588d449f4ad13aa3c514ca4c3b0076'],
 'Middlewares/Third_Party/SX1280lib/sx1280-hal.c': ['1145cb2d3eb5cb5e049805480abdcc0d1508f658282a362e77beec16b2c0fd74',
                                                    'ce28c00b1c39f54f0d3b9d75a55d27c293fda10c6bbba9afc8a2b3605a649f59',
                                                    'e5cfc3c0c9d5feba9fddc6ae4f8e7914b2f23197e1711655f5b662ed9dd2fc99'],
 'Middlewares/Third_Party/SX1280lib/sx1280.c': ['69f28cc87ca5a20f9789ebad2935ad241665706a0badd99d3dad94d3630762bc',
                                                '872ece0c853452d38cee8bf3044939917b332f9aaa7e7d6869aef4df24bfc16f',
                                                '9cace374a08b9fab18e85151f1af00991fd446e1c652ea5e4033e994109e9294'],
 'Modules/Src/telemetry_service.c': ['5a7779a164fd157cabc07c01fca1e3c554801ef43679f00b346d0253027a7234',
                                     '7e55c5b2c7752475f320af93a8e2b9c80179e36ed50afa296c1d59a5dcc0bd99',
                                     'e450621b83dec43a5c8a6c9d10d8f27106025186fef331f51351ad092ac16f0a'],
 'OS/FreeRTOS/freertos_hooks.c': ['4ba8e8ac6eaa20f80529ed2a93a118a41a0d631773a948d8bb89b75937973e44',
                                  'b65245cb71ac589bb0cfa73c82b6d4fe04d2aeaf8229cdca123189cfcb4b19be',
                                  'ba8857400bde0a2f1af50fa4efa5381f28feaee91debfb05173ed8768c732822'],
 'Platform/STM32F1/Src/platform_critical_stm32f1.c': ['610e141e927120c3603e799bdb5efb903b1eca26cfd033519c4396773956e624',
                                                      'dd4386f885a44ada000a88c5b35e9a464a2592dbd2dff4a229fba9f51261c0dd'],
 'Platform/STM32F1Flight/Src/platform_gpio_stm32f1flight.c': ['06d25620a8df5c8bcf3083367d7a4e933f1e5247459029b1648c581cdc7dcc36',
                                                              'c3074a7a51cc6f0821c74046eb4dbae3c78653e5dececcd69b7c8b09691dc56a'],
 'Platform/STM32F1Flight/Src/platform_i2c_deadline.c': ['120f67bda9119bc098cf5a17b7bd8f8540d9666e9ca975674f55e951f33048ac',
                                                        '49c51b543cebf330bcc30365cd5aa46647b9ec80bbd96f5288b3747b46320e43'],
 'Platform/STM32F1Flight/Src/platform_i2c_stm32f1flight.c': ['47791c4135e65cb78f08db3eb08ffaf3184300dbd1f5302a3811ed55558b4be8',
                                                             '9b1caf86f57316f87581dc4997c8cf5166752b02a56d90bba69a6099bf297be9'],
 'Platform/STM32F1Flight/Src/platform_memory_stm32f1flight.c': ['1e15e1ccda407aaf91d3e1e7dc2f1f2bc5e91a2de3f662cdecfad2bb59e7d28c',
                                                                'af8d52814187f8ac2a129f30acd830a42458d82db590c6fb03fdf580bf1bae7d'],
 'Platform/STM32F1Flight/Src/platform_sd_clock.c': ['a63fed9a449e8c0fb176673d622b00e41c9e3ad5df655f6157ce1b3c3deff22c',
                                                    'f558cb495fd9c68d2dee8781bcec133e8a2811aa6c85cf72de52642d86f9eae4'],
 'Platform/STM32F1Flight/Src/platform_spi_stm32f1flight.c': ['1a0f757814a081a4ae9e9e57f38f6d201b707fd012e0383a819b9e3160dff008',
                                                             'd9a21a72f62296c9d394b86d1ad0295304690d244d018bea088c31777fa706fc'],
 'Platform/STM32F1Flight/Src/platform_time_stm32f1flight.c': ['8ad1415cb0368d8188bb678433ca3d070205d3cf9b6bd09e1c675599eb8cb98a',
                                                              'bc3055356a551e702c1c0411b655c56c9927f848de334c04f29b1eab1b872023'],
 'Platform/STM32F1Flight/Src/platform_uart_stm32f1flight.c': ['89ebb8a5063461467d2780ca66d733914f4b20f3c21d42e5dd4693893d86cbac'],
 'Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c': ['d2bdfe31f45d97d4964f18dc81f40ddbf28c5550a70eeb5df68c8a7eeddcf677',
                                                          'f694cd6ddba0e73944fc808cedb616d6e2a3072a81cf30bbf9c18438d18980ab'],
 'Platform/STM32F4/Src/platform_adc_stm32f4.c': ['12530bb7cb5374e7644c3bd9fc543aff9dfa8021a13475bdb7c401b28b2f498c'],
 'Platform/STM32F4/Src/platform_critical_stm32f4.c': ['72a516d180e575b90852382beb5c75a24814083e99e0a6b0679144459ea00e45'],
 'Platform/STM32F4/Src/platform_gpio_stm32f4.c': ['c3e47fe7a455e51c926b886022e51f1f606c22baff986c0f6c127a16103da741'],
 'Platform/STM32F4/Src/platform_memory_stm32f4.c': ['fa39abb2666c73c179dd26735af8985d082dd3cb5b2817a3c5369f427874522d'],
 'Platform/STM32F4/Src/platform_spi_stm32f4.c': ['5ff1b6096046d2fcd32af1b820b19b47ed3e5bb75ddacf51f5b9b75d2714408b'],
 'Platform/STM32F4/Src/platform_time_stm32f4.c': ['dfb378e7bd21e4a680658cdac21dec3f5af5d5f815319ae18270c859dce8508a'],
 'Platform/STM32F4/Src/platform_uart_stm32f4.c': ['e882c1b71c586985cc461387c3282fb60cb1073cc9ac651a88b1bc40e1fd88f9'],
 'Protocol/SSLOG/Src/sslog_protocol.c': ['0c45d3c7d2cff5879a3f0227b5d3b3ee35c65d4bba2e123acc5101ebee018ddc',
                                         '20d398e232139ab2aef6da864c472f4b260c7c95705457bdf1a9c7f05dc4049d',
                                         '2261924a892437222ff8ba12129ea9eaf5ac0549c96b2c41a9d19b8dd80cdc6f'],
 'Protocol/SSLOG/Src/sslog_records.c': ['2eb4f4d6f5469f9da36fd59c4cfe8b599a7c1389f7c3e903e0c63d86b8b9eac7',
                                        '4f9602c5b3c2b599be8d2ea0526267e4f89559d8700956bb6e948b58f91df166',
                                        'b1cea26188f2eb1fa354c74c621f88c66ab65e5d609e6185e1e6070da9ae96b6'],
 'Protocol/Src/air_protocol.c': ['10b6440ca7a726176f92b4f93cc1e1f2edf0c9001178db731a419534f0d6c1c1',
                                 '2a24e6e6dd04cfefd99619dc2e736070299563b2ffcfe8426985d151534ab996',
                                 '5087834b446e525bf97945eeac7cbd9e87e67fc72f7589d5e68ac549ec329997'],
 'System/Alignment/Src/system_alignment.c': ['92cf389d14cfaff5c782822855aa0b828a6fb29402059075ba5c15a3bf875427',
                                             'c1ac0c6c1ab7aa27fb5c4249191ee701746423823d3846fd401ffb7a8ba9d2fe',
                                             'd28405b4e7ce0cda4d2e3bbbf2f2b48cd2cb5ccfdb5bf0f133ee1cf4eca8eed5'],
 'System/Alignment/Src/system_alignment_source.c': ['123d958bd7d6d2db9aa8d20febb37fe8f6dc853de5bdd89d8764b95fff4078a5',
                                                    '771119338f6bd333a710b879a191936a88040660970729f07c261ab9451c8d2c',
                                                    'bdce21d7e846f0530c222d23636a3e73087be87f4534eba9821f6893f88cb313'],
 'System/Calibration/Src/system_calibration.c': ['2f82524fe688b74d37a1678335f844a8f503925975463769786009ee89516906',
                                                 '4b5324f98812da2012569d5192a958d41b80b4765bce996c1fb0cf003da50dce',
                                                 'a7d23593c2a807abce569edab370d85aaf6b9f36c7ec0ba318c9334bec967bf5'],
 'System/Calibration/Src/system_calibration_correction.c': ['2274aa61228e374d47d99a4a7934e8d91682c0d13814f9cad0d399ed3a7fd2aa',
                                                            '58cd7ef8b74d3ecab55c7e2ee1e0cfcc3028ac54d0e57a64a3ac6c744c8fb00c',
                                                            '6d2308e1974eaf49ba76f9462aff31b1c109fbb729fa260aaa4f5bf6e2c7a823'],
 'System/Calibration/Src/system_mag_calibration.c': ['60b9892e0571fa20a0127fd395435e219785e41b7c37169de7eba3850f2fea07',
                                                     'c10891ba443663d4ebfdbfe7b22c147729b98e5b4b1e5495e4e3a68ab849bace',
                                                     'e26d8bac72c7a19d1404a207ae9d7dbaafe8f0924855882710fe7e7cb893bd55'],
 'System/Indicator/Src/system_indicator.c': ['1f13ad6f229f13dc1db49dfa384b157d7bca13e8b5db6870583a25790c52e191',
                                             '288260ff14de4c77a94b4ba76738a2c6eb7ecd1000740a09036ac3e3117478f7',
                                             '4e9ffaf5a203c1030ea44b9de731c61f6305bd586c639b5dd0bff9267efa1bc1'],
 'System/Inertial/Src/system_inertial.c': ['08f3f67b6dada3231cd2b2fef62a2991f1e01c9f1f4befb71231f0be67d5acb8',
                                           '5dbd51058b860ba6d0f2946576de33c8d6a1638eab4f95d0f334d7baf500c4ae',
                                           'ba27e0d167b297db38af9aef07e56f2eb4964d23b154f2f9b4dd3eb67bddc9bf'],
 'System/Src/system_barometer.c': ['51f234a3889fb7a29aa0fcd296af083e6a27649a9cca150ef076752ddc8a515d',
                                   '98a8bbd66c5e4d09f1389a5e278f45878462c8f0e211a0592ada70902c68ac11',
                                   'a73ea93edfdd44735d95023f484cc3b74031fca09ed22e0c48b7a3062bc59c3f'],
 'System/Src/system_barometer_cold.c': ['13e6a67697d9fae4d1ddb927d3e265c76fac0eccee57f8a48faba37406bb9664',
                                        '695f33b55baf01f799ab7585b3bb13f64b36a2ecfff7b4084d29b7eef02fe6d2',
                                        'f0843f91882c24cd58eded1dd231c4f30fc31675fbf03fd3c07c5aea2a222c2b'],
 'System/Src/system_capabilities.c': ['6db5dbbe40cda2b4595ae87689b509d5ab7302e34b2c87376e2fce35d566b681',
                                      '7481d7b1ae3646776e2c2ce0b95a4ae4f0f00554716934ee6a172dbd49934329',
                                      'db3c1609e4b2aa6a982675965ded5f0f86879da470b9b5cd8e29d37654d29f7e'],
 'System/Src/system_console.c': ['029afe6023488c82e8732e5b45f6b3fc75cb87f8397b19a6aa24dec0e4922cca'],
 'System/Src/system_device_startup.c': ['60095d5e12b3388d89f4ae1943a7e25485e4859460872745a1c969665604e510',
                                        'a622b56b1e94af55cbb5977430d23266d6ec35269dc9fff3bfaf16cb0adf2637',
                                        'f489fd0a92a072d7e29672941887b3307689e4377b9fd2201710623c7d1779cc'],
 'System/Src/system_estimator_diagnostics.c': ['576741cacf93a3bfec7802a6ef3ee62ee874099d76e94c4dfe6469571f8570fa',
                                               '8b603c32695dea023e275cbc44f6dc2ec647162f8737f57dcd1116d319d01ddf',
                                               'f5dc71025a7aa0b4393687b2ab2a9bc3cc21462ec84238d5666d889988552329'],
 'System/Src/system_estimator_profile.c': ['08315d7c03b57d38da9c57ebeac8314cae79b88a2c3957167d57092d46131610',
                                           '7b38dd8887b4de3a20c30ddd83b1687e44328f0b30d113dd17b5de023203c0af',
                                           'f0aa2ccef5891d16bd9118bbf3b5ac89289cefa45b3a7ba99c34c4e7002e5d7f'],
 'System/Src/system_gnss_quality.c': ['6ac29107eba2e5d85557d6f9c0a671aa75941fa241f5b63803f574620f92fed5',
                                      'ab732f8d31c2e16c63831f2cbda71bb95322e91a55cc3bd2ea92d61920e0d217',
                                      'fbc5d3f8abd0885c7f7fa9dfd1fbf224cb89d7eb7ac14c6244da797308b1d5ac'],
 'System/Src/system_health.c': ['37e539c8d4c94b887fe1e02d17f5fe013dbe2141d13cb210d59ecd8c6abd17ce',
                                '40ebdcb022378a7d2bc47b3a6e4dfe84609db3fa0d0028067bf49bd523115031',
                                'c93e6b579454149d78276c38c8781ccbc2d9228cacb2e6dbc3dedb2f88dd397f'],
 'System/Src/system_log_policy.c': ['904d8022d1566bf809e91a4075d8fc881411a023029c64de59c68fdefe0535c8',
                                    'd7e49d7a7c593f3e2a61f31f5213ddf7cfee792461803a71115615b683cbe8fa',
                                    'f68c24b154abc5470f10a67416e852e946597b9e3c1b233b9f6a3409b9db7d70'],
 'System/Src/system_navigation_health.c': ['049eef77fbe8faa779a6316ed4efde1f31e3fb47f2028f814fa12d45b30c975e',
                                           '341e72b5abd52b292f16d5e003d74684cb8d7a9577a7ee2d636ca799ebf143a8',
                                           '86c6b57889a35e738c77d1addf6786a4208e3d3afba6b74721ce6730bd9b4437'],
 'System/Src/system_navigation_profile.c': ['7f04def08c7fd6ca0e481f47275ed026067fb2374c1e7fbcfab87658d62fce93',
                                            'c06b1ed631869d338b766b49b6a3fdc83301c11481da0fea1b3fb6280f7a64cf',
                                            'c766d4ab895b729faf4305b05801c1a67e14b154a4544b627d4bf13544b251f7'],
 'System/Src/system_profile.c': ['226c58399a328b8a1f8bdfd87f0cb4ef857f0cd8aed5e533370e5f6d78e2b604',
                                 '4bac6a2591f5c3d470b04ca333e7798a0ab56dcea06d5e86ed8c707dcf656fbb',
                                 'f5a70e89e3d51d99ad8c906e00c20ef5a1e8011b0deabeaede5c42b4661cb98a'],
 'System/Src/system_sensor_status.c': ['0efa9ab88cea735c57957d4bd9e33599cbb6d00c6a41c549a2c25ffe19195c95',
                                       '7e5dc76df2a0fcdc71aca81ca462bfbd6fae11f7eeebeb562ae07f44097613c6',
                                       'c0bc8d8f8aa095326212d415cae1c29e396c69fd9cf7814a154f198b45b2210e'],
 'System/Src/system_source_selector.c': ['664f4c17aa1503387a8e317d7f3e17525d835ca046a97eca37bfeaba0ffd4acf',
                                         'bbf01ac25105408bf8d816ac0a98e2f608ccbef4a9b19c98aabc153f6340aace',
                                         'e3b20c527239d8d5c90749968da19fd5c7013a2eefc79bdfa5b9d1580b8ee1f3'],
 'System/Src/system_startup.c': ['162374836a9680ff81e517b27092a52a25374a2b6777471bcd80e746f10a9f09',
                                 '6ca1010d3dc317fc2d88c536c79c266916df7894a85860a0f3617496c4bebe6a',
                                 'c662cac620259c6ab6a2a5867cbf659013b37bf44930a656a07fbef85d25ead3'],
 'System/Src/system_time.c': ['8c7f7c13b24e6a1d6649a49bc4d9f1716703034b085c95f56a186811f114ba76',
                              'cd2543a72d54794a3c96c95238c9e868fc75eba1f3ac7ac24b9b9100cb7d6d40',
                              'f577f0d297f2b368fa709d7f8729995b0eedfac7601a15945c7dcd93bcf8aee1'],
 'System/User/system_user_inertial_config.c': ['43bfb46b2b0bc262e4bb8a10021d58196a892f97044aa347fd5c3456342ef031',
                                               '5a8b98d4f96a3d0f5ad6f881f98216d0c395d49a3ba42bc6ffd1dd7628e7467f',
                                               'f3644e0e03e220bd0ff77a8986f2d0c93ae153e6f8a7001fbe5255f38a431333'],
 'Targets/SilverStar_F103RE/Src/freertos_target_irq.c': ['0b146a3b233fdf724e42750ebd60eea6783f4c63d5f80f20b52145b0561b4e53',
                                                         'ec3718406322a183732069ed22fe33b71b4f5b35a2949c0e6f3f8b9c51d35c8d'],
 'Targets/SilverStar_F407/Src/freertos_target_irq.c': ['ba54de9352ad2edc316f6463c75b82940e2da19af6930ce8f1f2507d6882770b'],
 'ThirdParty/FreeRTOS-Kernel/list.c': ['2adce9dae033201899d4675349c526107c3b160ee4f5e0dee4c7ddc88e599101',
                                       'd8cd521d6464beb5f6528f22fc8e68984f8f1c2ed42a3b83816fcd089c3a8033',
                                       'fd3044467ea39fd94348e0fff2bb4ace89216522974ca8196cb2cba8b557a7f0'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM3/port.c': ['430e0973263f9ff3826287b9c88c9d85df09048bfd238a84c3fca5b0c35b80e7',
                                                            '4e342aab2c5c797040c7d001d30e2bba7e5e0b434e4476ee208665765d5bff10'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c': ['e564a8e75bf6202708ff8ebded2afcded56d16842f7fda0619adb7e23a6be3ca'],
 'ThirdParty/FreeRTOS-Kernel/queue.c': ['4386eb10bc762b508b48e5da2f133823545414526cdc936f3e7e399885654c1a',
                                        '71c294667fb83f03a330133ef91d4ed6d009f96a8fa090c860cb3c81c436e4cf',
                                        'b11a83221d4d5c69734fb25b4a1e50aaf795018e9b2331b3caaf349fd4f7cc9a'],
 'ThirdParty/FreeRTOS-Kernel/tasks.c': ['aafad50945a617c22f323562999e03a72bb923f2c8d14e4fa37484391324b8ce',
                                        'd625727778b6c6e34c0bc65251da622a685a1157991c638858d14308c075bc83',
                                        'ec22d5fe3221580f9162f3373ea4864d8b4b4b930797add3675d7f1489ca632c']}
BINDING_TRIGGER_V2 = '\\b(?:SystemDeviceStartup\\w*|SensorImu\\w*|SensorRegister\\w*|Mpu6050\\w*|SD_Driver|disk|Diskio_drvTypeDef|Disk_drvTypeDef|FATFS_(?:LinkDriver|UnLinkDriver)\\w*)\\b'


# Reviewed MPU epoch product revision. These exact whole-input/compiled-graph
# variants supplement the historical V2 sets. No generic acceptance, source
# coverage exclusion, callback exception or stack threshold is added.
BINDING_REVIEW_REVISION = "navigation_horizon_20261016_v19"
BINDING_SOURCE_EPOCH_V3 = {'APP/Src/imu_sample_bus.c': ['ee0e7e802d34a113b53b066c81223550e597933a2e1d90c4b84424b25e1ec1f9'],
 'Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c': ['c3b492c44a5d98fc53da74e6b3f9479c82a6bda9f7a4e4739324f3e50d14ed1b'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c': ['b477e1565cd8a7286e540497734936488104028a7af4b1da46e9ee76de9e41bd'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['ccf6921227e4ac4f5dcdff8e83b4ea9aa6a26a1a703b5b539a7cc1632b862a0e'],
 'Generated/Inc/project_device_build_capabilities.h': ['735917000047491122185cd40353c2fdb4b0aac4636968f51ea233ba4a180bee',
                                                       'b1536905635ca1a834d2ccb8e325974c5fc6c5464bd05984565c8cf55b7d7d28'],
 'Generated/Src/project_log_decoder_profile.c': ['846e9c62f0bdf67ffe1a2e0d3f356ac2f9c3e5117423236cd6911b98fbbc7157',
                                                 'da88bc144e2b104a0d33edd94d379a0e02080569fb01b0c61a4a898bf2eda588'],
 'Interfaces/Inc/system_imu_epoch_if.h': ['3944143b9c6ee9f33ec285c73898d97f888d4f25ad2f880ae7d5bc8e445e3755'],
 'Interfaces/Inc/system_imu_if.h': ['efefd3aedc6fb2251ca3b1d2e4242f880b9ea91c9bb11c5cd0b2c1e9ef2f0fa1'],
 'System/Alignment/Src/system_alignment.c': ['2db8da27d84f16828c3c5cb556f1443d1ba747caf3bc83d2155cc7a680cdcf1c'],
 'System/Calibration/Src/system_calibration.c': ['4b4c10c67b032e6d41ddc1a89f63cc74e388848419e193d7b9ee46765cd3eb9d'],
 'System/Inc/system_lifecycle.h': ['e8b0aaf198029f4dbe5d4bebe8fa773e883b79b55ec8e3fa9d0487dfb3653a54'],
 'System/Inertial/Inc/system_inertial_types.h': ['1b91855baa6b5a5661dc0972a90bc1f0b0166fdecac848cc012c90b51ab23150'],
 'System/Inertial/Src/system_inertial.c': ['649e2f37444852de691020c8ee4d69da9035f9f28dd82602e1700058d8fc9595'],
 'System/Src/system_health.c': ['f62884116ef6c73aeae4bae66fc17dca0c02b0dc325adedc3e7f02bfef12c982'],
 'System/Src/system_imu_epoch.c': ['79ebd07987f82bf288794345807125c9f533ec4f62044c1bc302a713067d64f8']}
BINDING_DEPENDENCIES_EPOCH_V3 = {'APP/Src/app_tasks.c': ['1051cb567cd811e03c7189628b9bf09b6bbf80c060675abd66995123f6474758',
                         '9d2d194bea0ce0bb19d013bd47c0e7f0605a22d07dfb024c144ea92b290de8c5'],
 'APP/Src/device_native_log.c': ['2e8f39d4c025b2bfbd060afd4bdebab433b2c96e0b34f2654d7712028d4b60ff',
                                 'fdaedaff55d149c7847d23d9e52eabfecbca6dd10d06983d0395e19eb89acb6f'],
 'APP/Src/device_task.c': ['4060176ff18c24a217d3fb145661d64a18c1869b6337ebde91b4c9a530d85044',
                           'e49ba0ceea42788bddfbf3d737ba7763ca4c3f3b8b93755ed3cf14c7dd77fe46'],
 'APP/Src/diagnostic_log.c': ['08e8847e93407bc7dfb57e5f83f04a3a69be8c48a4d104713ac94777952d840d',
                              '66d3e6dc0943689b3133de3b348a0616ff7ae737850adaad4a13a570ca41aeb4'],
 'APP/Src/estimator_task.c': ['78d14c9b794bc65bd4c52b07c23c94f9d004bea581ba5cc0e8c5a827d8a869b1',
                              '881944994807edbc8ba39b11230d593c6e3bfec1e1e3cdd7835b276ab716b415'],
 'APP/Src/flight_task.c': ['05175bd2a95bd9410574602376217efec76bf6a0d17f22c1e9b3049c6b370c29',
                           '70500d2e822dfb289a56ef9b00a74437aa984214b8440e7c268b128d052443ce'],
 'APP/Src/imu_sample_bus.c': ['6ff8359d6c69539f070aab10e79572ae841c70a54e5833dcef57ea1af722a52c',
                              '7ed9fcef9096dd223b08c377682360f8846d346ea74d14a5328ebce4107d7eb4'],
 'APP/Src/ins_task.c': ['8dace54a0ed13486d28a26eb4bdcb5fae5871a4f271f2139b6173586375a674f',
                        '9d1a53f803e7ebb157a0c6d685eecc648838638a518aca75deba7e526511d7da'],
 'APP/Src/logger_bus.c': ['08492839826e343554a20aacc8dfc730553f748cf138b27c4fbfd162e88f54e2',
                          'ff3641c074909d6d2d610905ff613f09f72616b7363133d2bde6641e9c980c6a'],
 'APP/Src/logger_task.c': ['07b08fd7ef89f2269004dbbf1d19e0fbf4282382ca0385f65d2a988d3f981098',
                           'b6e4f154df409c39cf60ab6523ece2e3d9ee6e87ed8341f9248a615f2ad74128'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c': ['249c80902303ae2b1aef4292d97705ef3704718565939fe1f815e130e2c4f890'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c': ['811b4eeb5d8ce42db9cbd6ecfd17a3c5fe8ecfc0784ae683b64c4b1a929aa566'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c': ['109c2a54486588f83d4e38ba16f0996d45ba3c138d1ed9791461e1bfbc56b8f5'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c': ['478f6f9874ddcb45f8a9a6de2ba7f20957279bad8cc0815efd228fe93dc129ee'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c': ['0a788908c6647320fe4fc203ef307b9f24696e044d96c0d81421e2107fdd5449'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c': ['27d8d2629357a0010252fd41922bacfc8259a46552f772546fe9cf9e76fe5ef8'],
 'Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c': ['718cbde74c90da0ac211abf7d26ab92ea8ddd9b7206bf39439155188463be9c9'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c': ['3bb0ab76e4ea8d22ebb34c12b36cc9438a089dbc1eaedd2805d9fb4d93ea2dca'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_spi_adapter.c': ['e892790c2c7a43553ca6f099a37b10fd65482bbee115dd2d309eefe8712e5de5'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['75988e78ac2f15f441e156d3aacfcce6e4bcf84917411543a9ecc551372f7a06',
                                                                       'f6792491d0aafc0b375bf6b462a289e59d4f87505367d0923cea9077847c578f'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['1eb7fcab4a6e2ec77cef6d4504e05e37e4290bcf18ec76d5b064b17e233bd21a',
                                                                'e341f8229535e663fd68a29427c51ce5d8cec55b12391896974860df02ee5ed5'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['3cff9d6e6012b3554e8cb91c0ad81473531175aea1a40bc69bbaafab6c977e03',
                                                           'f9074032fb4e3f558d49395c3dc0105fbcb98c4b4144a9e09ce27bc0bdd2cc3b'],
 'Generated/Src/project_device_instances.c': ['1129c81717c0c4626a63b70e09e0fa52b98c76369b1f6817da92546c97b2c092',
                                              'b6fb6e74a3f95368085fd5d67e0470c646ad47fcfafe745b26f6cbddbe6e6e73'],
 'Generated/Src/project_metadata.c': ['f88993dc45952c3061e006891e2e986977bf740911e9ba51643ca3b7fd8575af',
                                      'f9d40c8aab3ad551f34dc6919c3489e48771bb30ca985004c0d345bcf98a1e8c'],
 'Modules/Src/telemetry_service.c': ['3098b138fbfe0507fd9c77ec6eb7b7916f0180e149e93a3338604b4b2d523d60',
                                     'c761f60407370a41e18eef24a3cdaaef58fa7e212ad717d961929d4cf394b5bc'],
 'System/Alignment/Src/system_alignment.c': ['98f9151fc3f161aaa0079485051d6841a338ed08ab4347fdadffc61b38fd29c5',
                                             'd9a070e7aa387db8e513aa16f4aa68a49c97da3c17e0e06dfe6fd1cb32cb8457'],
 'System/Calibration/Src/system_calibration.c': ['7f0b0f92f78abd13865f48aa7d8137ae6a354f9d484ccc46c5f51efce6446cc6',
                                                 'e9551f30eca744c94673cca5b6fca39fa126e49a71a55536751ee9afd591a398'],
 'System/Calibration/Src/system_calibration_correction.c': ['00e0661d883bda8481c5596c061e148e6c8ea3b3a1f13938b811f85ab160c725',
                                                            '0c7ebfbb9e4c5f857c8ddb2f3d48c1ecab00cf14e1feeda416c93f6a6fdfe252'],
 'System/Calibration/Src/system_mag_calibration.c': ['a47addeb4fd1f4ee4a610ca2b8ed3369d321b8db175fd1c2d7a40579c953775b',
                                                     'a539ba1c43158d49f93e93f2a7cb7bd4514073b08421455f180762bb3d2df2a4'],
 'System/Indicator/Src/system_indicator.c': ['841fa3cf2a7c0babd16ebef395684983b95452fe77dd35f827e788fa8e2690da',
                                             'b1c40416c5731b8aac8d5084b6b97c6d54f94c1f9a3ad921ec9e49ad543574ff'],
 'System/Inertial/Src/system_inertial.c': ['799585d06a6d2145c15284459d81293237bc5080701a1f2c3cc19bd5b30cfff4',
                                           'd31ca1858e879782ef135eb42752fc39c247178eba8c3f449a1fc6243d17173f'],
 'System/Src/system_barometer_cold.c': ['d09d8f014bd8cacc7cbfa1b0af82148cfcb2530ce7326b771323f56f06a56ca6',
                                        'd13b812191e189e6589b8d51d7d90c3a6037ef473297857fd9c73a7d6751fdbe'],
 'System/Src/system_capabilities.c': ['15ac15e925d2ec0348460918fa9e130f0165211ed8ee6eea90fd6d1b27c7029d',
                                      '17b0a32487dfd89ef8efb57f5cb38c5628039d9fd464173ec2b1df757c71a142'],
 'System/Src/system_console.c': ['521f179e6d22df4620813e2c78b262cbee54e3064a7a9d3796567ad48b0ee90d'],
 'System/Src/system_health.c': ['3f7a44f0617ba1082fd23598c65de89c5778935725312b29fcce149b8b8aaa5f',
                                'e69b074f16c070be28940c140e45ebcfee333608d8d88e42a67291245f720ebe'],
 'System/Src/system_imu_epoch.c': ['3ab98373ee9f303f1e8301ad053e88cb333287ac3ef5fd8f2e8e15c4a863573c',
                                   '6c161871ddd1c477b0e3b24576a4c3f63ccdad5ba109c389ccec4005be49576a'],
 'System/Src/system_sensor_status.c': ['2e4968e0b903ef1f50fc5faffa92e8a634f1452e72b1a9f4e5acda79d58c3ee1',
                                       '582ae09612fa2676d3e6510fb17b22551bee6142b6fb71a6ad6a9bd1b8b36d2b'],
 'System/Src/system_source_selector.c': ['84d816a4bfd00699f200fe396ff819385cda79480a5cb7d72e3d5c2970fd9521',
                                         'db152a39a3ee860a8598df726d5b3215f3e329fb058bb4929895be3bd7664d69'],
 'System/Src/system_startup.c': ['0fb01b673d88bd874547bef3dd90c526c7789e78212053b9719a29badbd6255b',
                                 'f085bf28d0a728d4b596006b887aa73076630fda27d0650e60da97151ab3c645']}

# Reviewed final-status projection: exact input variants only. All prior
# versions, compiled dependency graphs, callback restrictions and thresholds remain.
BINDING_SOURCE_LOGGER_V4 = {'APP/Src/logger_task.c': ['7ac58b7f478151bb4a90473e1509571aca3be80ba18dd520bcd29432c2e1da0c'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['b986a28d23b4f7c77851e935d1f9f7f51529425f4bc3d5a922e3616bdd2ee74e'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c': ['be5ad9635c6a4177c79e260ba38d92806afa550b42ee203813f574a755e6bb22'],
 'System/Inc/system_flight_recovery.h': ['b156136c608a092b2c1edb8ec54e48f64cb072f003f069036b99ebe1bb989d76']}

# Exact reviewed RET6 NRF pair inputs from official CubeMX F1 V1.8.7.
# NRF driver/profile bytes match reviewed 193ba4c; Logger projection/ownership
# and the MPU epoch contracts remain. No callback or coverage exception and no
# threshold change. See docs/FCCG/NRF24_RET6_INTEGRATION.md.
BINDING_SOURCE_NRF_V5 = {'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['99dd7da212143d9118e235f2118bb42fd1e9325cc90d46e470e468db745076d4'],
 'Devices/Storage/SdSdioFatFs/Inc/mission_radio_profile.h': ['6d7a653a77cb596a1fd7cf7aad895fa7b487e9c5f92eeeadbb1b906ebbd880f6'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['f61c6e6341e054ac4d871b332532f0590b46dc24e63a63da8ed601e3e9cdc3e0'],
 'Devices/Telemetry/NRF24L01P/Adapter/Inc/nrf24_instance.h': ['9caa5b94044846c78ba7335188b2fa21f2fd15aa60271b92939b5336378b2baa'],
 'Devices/Telemetry/NRF24L01P/Adapter/Src/nrf24_telemetry_adapter.c': ['155b03cb3e0d30b3924b30594414ba5caee8c7535d08fb08724e5fd17eaef07a'],
 'Devices/Telemetry/NRF24L01P/Inc/nrf24_device.h': ['2365543f78d5c3ee3b44d5fba4033002907a14a091b910088ede99138f94b659'],
 'Devices/Telemetry/NRF24L01P/Inc/nrf24_fragment.h': ['37c563acb24aada9e463dd3bedb2fe24346f5cc775b71b134974fa167cfd6791'],
 'Devices/Telemetry/NRF24L01P/Src/nrf24_device.c': ['b79ab031047134b4d1b2ec8c3fabdbdcc12639633a74276b8481a7837e68a6b2'],
 'Devices/Telemetry/NRF24L01P/Src/nrf24_fragment.c': ['0069bf6676749bf58b84bb10f771b8b3ec1a31cb9e29adc41d996b6bff6a6cd8'],
 'Generated/Inc/air_link_config.h': ['ff4d4603751facbfa4ed15867461d3248febe21cf823343628e05ac3902b5f9c'],
 'Generated/Inc/project_device_instances.h': ['664d7220314f3c472e52fb636c094f2285c72f43499998fe9900914ea11c14c8'],
 'Generated/Inc/project_resources.h': ['f22690d9df61e355acea7165adcddf6ef536c3b388221a478e2ff3a6cb38962c'],
 'Generated/Inc/project_storage_binding.h': ['8f64ef48f0cf7dd6a4482ec41e1059ef8f21be5b631caf51cbedb14f1ff882b3'],
 'Generated/Src/platform_resources.c': ['45ec326dea074fa81add09c63faf618771fd32a8a27f8158580a5d3677b0f84b'],
 'Generated/Src/project_device_instances.c': ['34732aeb0b8ad57062cc7d4e3c3da529e2a7a1f617626993ef308b0aadde11c3'],
 'Generated/Src/project_log_decoder_profile.c': ['7c009bf90a89987fba8cb1a26fb79e84b7408a23618e3ccc02eab9a1f18e6dc5'],
 'Generated/Src/project_metadata.c': ['133e2cc92ebac7a03fc3809fb548fad8be35f7ab40291358af8eb18f37745e4d'],
 'Generated/Src/project_resources.c': ['8872f6f6763935fa05e44d6f32e68b62733125a97a724143a74b2d47a0a18053'],
 'HardwareGenerated/STM32CubeMX/Core/Inc/stm32f1xx_it.h': ['943d173dc5df64bd0b72f9306e52a5cfb5b293f066fac6d6f2d3c2882671c000'],
 'HardwareGenerated/STM32CubeMX/Core/Src/gpio.c': ['09c52690c726fb243141e00ca64e7827de7aa51b32ce152c5d62f0fb504e1ea3'],
 'HardwareGenerated/STM32CubeMX/Core/Src/stm32f1xx_it.c': ['86af185cead8f077b6455e89a1a747828c25268067d14b49d9445acefbebba6d']}

BINDING_DEPENDENCIES_NRF_V5 = {'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['eabdd31418e98a05b2dd16db9cc0a6fba73458bc4bc08583abd00faa747e6c96'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['4717236750a353bd3265adfccb52f07d4353027e58c46c1f9554868754beeb50'],
 'Devices/Telemetry/NRF24L01P/Adapter/Src/nrf24_telemetry_adapter.c': ['0acda6af79d1195e4c8f7bbc91a76952a41a004ceb719653810ccb99bb5b82db'],
 'Devices/Telemetry/NRF24L01P/Src/nrf24_device.c': ['82da67daad9a3fccacb59a3cb0bd15432afcc50f59672330c30082071a0d9a0a'],
 'Devices/Telemetry/NRF24L01P/Src/nrf24_fragment.c': ['8112748e472b0e6c42b63ea7080bea49118632d7d611bc2ab063d4ad9c11df27'],
 'Generated/Src/project_device_instances.c': ['3adac9864ceeeb0e33b82eb000949db35aa2d101e612c43c26161006919d3b71']}

# Exact reviewed KF6 health/publication bodies and fresh F407 reference inputs.
# Historical core flags stay internal; no new callback, ABI, threshold or source
# coverage exception. F407 generated inputs are identical before/after this fix.
# See docs/FCCG/KF6_HEALTH_PUBLICATION.md for configuration and remaining limits.
BINDING_SOURCE_HEALTH_V6 = {'APP/Src/diagnostic_log.c': ['454d6680c2165ab8adcc974dbac9daaf47e93e8cbfdabd8b53628b0f7f6b7cdc'],
 'APP/Src/estimator_task.c': ['15d51ac42b7ca17c55f40e8594be995bd16ba4cd033a68d600fd3cc289db8d18'],
 'APP/Src/ins_task.c': ['b86c5db02390f31b1833c509b34b8ef3f5740b488870b9bebe038f78b7c65ced'],
 'Generated/Inc/project_algorithm_parameters.h': ['a655e7e0964252a959e23e59369da5bb7d94b8fc70500e6211659ce270daf33e'],
 'Generated/Inc/project_device_instances.h': ['ae8cf72069c44a53398b4c950d0f6cca4d8550a93507644402b8719b2b5e1f95'],
 'Generated/Inc/project_flight_config.h': ['0ed2f76db7ca7b2ca73c7a579008286e1916b2c51cf1418375c93d388722fd52'],
 'Generated/Inc/project_storage_binding.h': ['1cac55d35dbd70bc6cf5305dbf9e7c877fa9eded2143a2d2e31f7652c6f5d3f4'],
 'Generated/Src/project_capability_routes.c': ['3ac6a4b817c2228cf75b782f8ab3737768e2308b174a3cf9e581287872050f3f'],
 'Generated/Src/project_log_decoder_profile.c': ['dec59eb724e22e84329c4ea49e1f569520f592743c903d6e68acf34701449e30'],
 'Generated/Src/project_metadata.c': ['e6405ace3f032bb3d669a91b0ed5d5f0fd1d24fbf314171618ecd2d5ff3c5ff2'],
 'Generated/Src/project_mission_parameters.c': ['05fd966ad4118ba5993e276368850d60b81fd973752e71ccbee1ea165321785b']}

BINDING_DEPENDENCIES_HEALTH_V6 = {'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['3eb8c2bada34803a77457928ec414d08f262739082857301f2ed9e1b4376cb9f'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['3ae2c0b291a6b698c09b90dc1a508329c148f295faae1ec442756bdcd7d0c212']}

# Reviewed InputVoltage System adapter relocation; the complete source bytes,
# ADC math, locks and assertions are unchanged. Only the compiled source path
# differs from the verified F407 dependency graph. All prior inputs remain.
BINDING_SOURCE_POWER_V7 = {'Devices/Power/InputVoltage/Adapter/Src/power_service.c': ['d375930dbb1d1efe7d73640f3e1c9b90b6d862b36b92db39843bade31bc08e6c']}

# The exact generated profile changes only its source-graph identity after the
# adapter path move; record semantics and the selected F407 configuration stay.
BINDING_SOURCE_POWER_V7['Generated/Src/project_log_decoder_profile.c'] = [
    'a281cc86919056bbb6c908fc9ec030844f10e5e4af6dd4ec4125fc0e2d782b0a']

BINDING_DEPENDENCIES_POWER_V7 = {'Devices/Power/InputVoltage/Adapter/Src/power_service.c': ['d067dc025909205d0b9b552e98255781ec94d530c671668321a39cc2aae438cb']}

# Minimal queue configuration review v8 (2026-10-07): the RET header differs
# from reviewed v6 only in the authorized 58/40 -> 24/16 queue constants.
# Callback bodies, compiler dependency coverage and stack limits are unchanged.
BINDING_SOURCE_MINIMAL_QUEUE_V8 = {'Generated/Inc/project_flight_config.h': [
    'afca623011a2d5e7b7adc28d580adca0925b9b701ad0f38d23c71b05c08c281b']}


# RF four-provider queue probe review v9 (2026-10-07). Exact generated
# metadata/log-selection variants and real compiler dependency graphs only.
# All 152 C units and 375 project inputs stay covered; existing callback
# resolution, unknown-input failure behavior and stack limits are unchanged.
BINDING_SOURCE_RF_QUEUE_V9 = {'Generated/Inc/project_device_build_capabilities.h': ['7f969a1acedf4a1eca351a60ee41c8d6630567454f70fc6db1118b15802d5472'],
 'Generated/Inc/project_device_instances.h': ['72df121af9a40f4c619983d20383e613e633daf977cf60a8460b838492391bae'],
 'Generated/Src/project_log_config.c': ['c1c22002eb4ccfebbbd96ac196874700191576fe4b1343811d7e80a3f729a0d2'],
 'Generated/Src/project_log_decoder_profile.c': ['5615b5e0064dbe62054eb54022259de25e7d223a175e3398856ce46682f04e7e'],
 'Generated/Src/project_metadata.c': ['003574201c66f5474734afeeff92701336b186998aa4553b181beec4d2a65547']}

BINDING_DEPENDENCIES_RF_QUEUE_V9 = {'APP/Src/app_tasks.c': ['842fd609200005b6e998abf103f2ebaa9cedf4bb0cb48ca9150899f12f274194'],
 'APP/Src/device_native_log.c': ['fc9a72aaf3a9f48b15c67c7d65e272fe2979bb6aecf1b87c3f2e4ead52457f25'],
 'APP/Src/device_task.c': ['0cee95a265b2cce818a9ddd89997a76c38fd48fe9e8a31384740e2deffa85928'],
 'APP/Src/diagnostic_log.c': ['099cbb888789201c5c0e5f1f9af5acf8a51bd2c4968e6a344c72b505405f8e35'],
 'APP/Src/estimator_task.c': ['fab3463755af1183d0d1342fafd9457824fc9eda073b4a194a5b50b23c0d30ba'],
 'APP/Src/flight_task.c': ['3851d7e319c910ad414e1e969680c1a72cf90cee45c67238d3ced7bc7c37a7e7'],
 'APP/Src/imu_sample_bus.c': ['8d135a1b8d7aaac5e6ff7c1c12147c006789096e4f4c6a827cb8e384043b7bc2'],
 'APP/Src/ins_task.c': ['1aeef8923c93e66e26d6f6e61c97eb58ea036364c5b777a2dc3474d3d8d9080d'],
 'APP/Src/logger_bus.c': ['8befefa13c0bef09d16ad73a7bf2a884018c37d49cc84b281751cfec12e23441'],
 'APP/Src/logger_task.c': ['eab6279364c4a7ec234dc0a836bfc43ac60a5db04295477b2fd065eff6f27636'],
 'Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c': ['936daa462864418ec5c7040a0c632300be3d461031acd320cc0adf944def3693'],
 'Devices/IMU/MPU6050/Adapter/Src/mpu6050_instance.c': ['41f2fff2ee0e96a1525a5ee6c090939051909e8fea943e643e4a66f6d7d99bc9'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_adapter.c': ['fa2a3f64658e88bab96124a28ca992492fd4b87d62cfd8dd25d3ef6fc4484555'],
 'Devices/SensorBus/Adapter/Src/sensor_imu_spi_adapter.c': ['340b2fbc0df37d2015293a524745216189d29b3da61bc1432897aba61aa7b761'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['10a0443b8e725093ad56f0300c460236cbaae5f50bf7cc76c7cdfa0c1a29ea7c'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['713a40c075335951db6114459e5ab7997f8b8517ad37f4cd473ed2257151c7fc'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['46afd7878e6e8dc21916c5e24472084c3b83a4fcefe57debf8cd308f6104f70a'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['13884e7e0e22b7e0f13b724a398539233b5f75fd6d2f44fa6412c88e39dc06a9'],
 'Generated/Src/project_device_instances.c': ['b77022733feb3ea5e34290a7dc0a61090b8a324f26e9a379b8d0b7a2a8b77f40'],
 'Generated/Src/project_metadata.c': ['bb9378e2619fba3e6165d29d63b88d9be35678ba879f396cd7f67c9402188033'],
 'Modules/Src/telemetry_service.c': ['5e6ceb7e0870d7283c7d5792f7484e6312b2460ada2b730e49ff7680c70617e3'],
 'System/Alignment/Src/system_alignment.c': ['df16a01572354b57b80c5f0b58deb954fa3b43b784e04768ff99f5a6ce344808'],
 'System/Calibration/Src/system_calibration.c': ['3261e3db6e416eab70ff66c407ded27774505dfb1d483b9f7ea70510424752e5'],
 'System/Calibration/Src/system_calibration_correction.c': ['79aa948d9df6f9537e8e6ca4980a7a767976600ff91d3ccef1405bacbac67a19'],
 'System/Calibration/Src/system_mag_calibration.c': ['68056caa7118c6ec587f3e67b66019202a3d3cb097dd75986c2d52517383db64'],
 'System/Indicator/Src/system_indicator.c': ['21bfd559f81a23da671031d26b7d2e4cf55555286444a9fa486dc9e9838085ab'],
 'System/Inertial/Src/system_inertial.c': ['a29dbfc78374643b06f345dbd9c2db36bb06bc67305f124f01b5879caa51b95b'],
 'System/Src/system_barometer_cold.c': ['eb3789ecbfdd816e897b93e35c8eb0e949ef5331f9ae923642ac899fa4322a20'],
 'System/Src/system_capabilities.c': ['53d26d70e52cb7a4687079816e0d40dda6f8293405aa6c4874472a98761ff99e'],
 'System/Src/system_health.c': ['68ca7fa310bfa6db792de47cdb221d84be5652e0aba1d9c503f204c732b447be'],
 'System/Src/system_imu_epoch.c': ['7b554c18d71e7cea2306aef5a512da445393afe965abb21a9f7aea77d52af92f'],
 'System/Src/system_sensor_status.c': ['f3b25f0d902dc41ca099646c7ab651008ed0703660150c36ea031643015c3b87'],
 'System/Src/system_source_selector.c': ['eae6c5d03c70dd07d0acab9477c35f76dc982fae5c76f6c54dbda754504e94d0'],
 'System/Src/system_startup.c': ['306f41f9b584d3fc51c7e1f82ca6b300736db37e96a5a390820330a01799ecb7']}


# Exact-source review v10, explicitly authorized by the user on 2026-10-08.
# This is the frozen f045d8c static-bench identity, not arbitrary metadata.
# All 155 compiled dependency graphs match existing reviewed graphs. Metadata
# differs from the confirmed configuration by an identity digest and blank line;
# decoder C differs by two identity hash arrays. Callback bodies, targets,
# compilation-input coverage, stack limits and unknown-input rejection stay.
BINDING_SOURCE_STATIC_BENCH_V10 = {
    'Generated/Src/project_metadata.c': ['ae4706ff828b966e517972f147eee2d5ca938a144ff437ef3b71d32a9f186181'],
    'Generated/Src/project_log_decoder_profile.c': ['e66c2a4581505fdb114a88f7ff65c866c0e2c0b9b4c99186d0922960bbe98da4'],
}


# Exact-source review v11, explicitly authorized by the user on 2026-10-08.
# Only the finalized health-publisher boundary in estimator_task.c changes.
# Linked indirect sites and the other 154 compiled sources match the reviewed
# bench. The new direct getter restores IRQ state before return; push races
# retain their checked error path. Limits and unknown-input rejection stay.
BINDING_SOURCE_HEALTH_FINALIZATION_V11 = {
    'APP/Src/estimator_task.c': ['98df5cb8cefc0a2e5632bf51fd73319cef033d5a7bb511390c246dafb5b64610'],
}


# Exact version-header review v12, explicitly authorized on 2026-10-08.
# Only PATCH 0 -> 2 and LOG_BUILD_TAG SILV0100 -> SILV0102 differ in this input.
# All runtime settings, callbacks, limits and unknown-input rejection remain.
BINDING_SOURCE_PRODUCT_PATCH_V12 = {
    'System/User/system_user_config.h': ['ffb28f9bf8e08e73c80a16c1121e8c37954f7bb7ade95f2aa47a5226787cc840'],
}


# Exact metadata review v13, explicitly authorized by the user on 2026-10-08.
# Only CONFIG_DIGEST A79E2E92 -> 42A4C1C6 differs from the reviewed source.
# Register this complete source only; keep all bounds and unknown-input rejection.
BINDING_SOURCE_PRODUCT_METADATA_V13 = {
    'Generated/Src/project_metadata.c': ['bba3aed1cc73043a10cfd126a7759728a10de53e3769e2563fb209a4b12feadf'],
}


# Exact decoder identity review v14, explicitly authorized on 2026-10-08.
# Only project-semantics and generation-profile hash constants differ.
# Restoring the old product identity reproduces the reviewed complete source.
BINDING_SOURCE_PRODUCT_DECODER_V14 = {
    'Generated/Src/project_log_decoder_profile.c': ['ee5baec0a73077cdafee252ba8715045db8ee39e4b894c6846be3cd059392616'],
}


# Exact integration identity review v15, 2026-10-09.
# Complete sources differ from v13/v14 only in the configuration digest and
# two decoder identity arrays. The current ELF and dependencies are reviewed
# separately; thresholds, callback contracts and unknown-input rejection stay.
BINDING_SOURCE_INTEGRATION_IDENTITIES_V15 = {
    'Generated/Src/project_metadata.c': ['7b76da5ac6c0e615a2c76dabf8bf2a8e674b00ca0c3e4d1b81ecc60a1eaf4d00'],
    'Generated/Src/project_log_decoder_profile.c': ['ec50f2e5db9a0de82b53c77811f99838bb3ecf2b0f7f6dd94ccb632961b09c51'],
}


# Exact UART maintenance review v16, 2026-10-13 development task.
# Eleven complete inputs and four compiler dependency graphs are registered.
# New service/lifecycle/status paths have direct calls only; linked FatFs SD and
# startup callback proofs still run unchanged. No callback target, threshold,
# unknown-source/dependency/indirect/recursion rejection or source scope changes.
# Scope and unresolved whole-firmware MSP/ISR obligations are recorded in
# docs/public/SCG/UART_MAINTENANCE_20261013.md and its evidence inventory.
BINDING_SOURCE_UART_MAINTENANCE_V16 = {'APP/Inc/logger_bus.h': ['077d47330fd6563a410a242864d580468722f8d3f4daae4fc5fffb271c81918b'],
 'APP/Src/logger_bus.c': ['694acdf52db1cc042022cea3fb5c999b305eccb7a3511e24a800788c7dfdc30e'],
 'APP/Src/logger_task.c': ['add1697345162f9174c111c9a63f1f118326ce08df2a3f74fa8ed72333501e2a'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c': ['ddaab372f3478bc9d9a9481d160abe4ca96cd8186a6aae22db52f345ef3c7f38'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['75c237331e402c9e915f9a932401c3bb51206f0ac0c770de7baf582280cad68e'],
 'Generated/Src/project_log_decoder_profile.c': ['5ac6d3e7614214dfd5d38495bab5656363ce42778be6ca1e037781411b644170'],
 'Generated/Src/project_metadata.c': ['272fb367309e246dd49d3e682afa424b533e5e417016925d8b5764d3bfe770c1'],
 'System/Inc/system_lifecycle.h': ['5a08754621adacd292d725a8b8706daf9c6366f942ed127ef78836d09fbab45a'],
 'System/Inc/system_log_file.h': ['8974948a654cca7889378779b8bf2bf2b2462e2a7eba2160af90047393016e17'],
 'System/Src/system_console.c': ['a1a66189ab492fefbef703dbcd193397a78ce700593311f442afbb8818ccb45e'],
 'System/Src/system_log_file.c': ['b525df1b84a21fe1e8d4e0340a35b693a6c879666da9f69c36e6367fa894d3d7']}

BINDING_DEPENDENCIES_UART_MAINTENANCE_V16 = {'APP/Src/logger_task.c': ['7153d872e5f42292aebbfbf99d682b3409cc75e204249de274741c41886a91d7'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c': ['03a7bcfafc90ae3b5185a4ebd5551483cf77b39cee7b215d87c4a97770867c7d'],
 'System/Src/system_console.c': ['fc56d25bfb4fc05211e10b7992cbe6df4247bce497a9b91eb4dfefe96988961f'],
 'System/Src/system_log_file.c': ['ceb89202b09819f0983bb1815060296034f2beb00c36c1a86f33029edbca067d']}


# Maintenance 0.1 diagnostic review v17: six exact complete inputs.
# RAM snapshot copy, completed-write observations, bounded direct diagnostic
# readers and two generated identity sources; no new indirect edges or graphs.
# Existing callback proofs, unknown-source rejection and stack margins unchanged.
# See docs/public/SCG/MAINTENANCE_0_1_20261013.md for evidence and unresolved bounds.
BINDING_SOURCE_MAINTENANCE_DIAGNOSTICS_V17 = {'APP/Src/logger_task.c': ['61eca40601d0bfb437c6d122ad5e5b768a107609bd4e01cc532fc3440b7767f6'],
 'Generated/Src/project_log_decoder_profile.c': ['e63337bc4953694a97766adcd457f2bd384c55b0ea6fba4b3f35b43e4c638ad6'],
 'Generated/Src/project_metadata.c': ['35f6f89681b4850b26ca6f2cd1a958236cfeb635eac3565df029533e20dc2240'],
 'System/Inc/system_log_file.h': ['9ac073f9efed02b70c3ff786f9f02a513c899c8f744bfd11344e0cac968aa8a9'],
 'System/Src/system_console.c': ['0a44e6db3e91e18ce0340fdc80c55fb9c15a459210b10f23eb17a5d46e4e2346'],
 'System/Src/system_log_file.c': ['b6759ba75a08903fbc4a86a44a0dbc3a2b235af1972b7a33947176db19a22bc7']}


# Exact navigation/timing/memory review v18. No new callback or exception.
# Review and unresolved bounds: docs/public/SCG/NAVIGATION_STACK_INPUT_REVIEW_20261015.md
BINDING_SOURCE_ALGORITHM_TIMING_V18 = {'APP/Src/estimator_bus.c': ['33af96d36dd9186c1d5c49cf9a22e40852cf7afcb5564bb9507a0327ae7e7218'],
 'APP/Src/estimator_task.c': ['421ad5e49652acd0704a17ddcfa7e8ee4b2761a6f7e0abdd3379c7cb97274b33'],
 'APP/Src/logger_task.c': ['c811e123cf8d2821721fa0261bed6ccbfe3d816edad303f73f5cbd4c1d3f0321'],
 'Algorithm/Estimator/ESKF15/Inc/navigation_eskf.h': ['9610510fca9205be22c81b6f9aa66e954fef862ea3890af277565f68804738b2'],
 'Algorithm/Estimator/ESKF15/Inc/navigation_eskf_config.h': ['da8c1010754affc87b1f6a4548fda681c9c3cac1e1e95be6a4f05454b99761ea'],
 'Algorithm/Estimator/ESKF15/Inc/navigation_eskf_replay.h': ['a153447cc23aafef71931bff2093424343cfa387532de6bc69aefb5f7e754f16'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf.c': ['6e16cf0476b4e0ea3eaaddeeae311b03515161d099cf6f29231e656fe11daa3a'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['9d3bc27b98edd7872f0a113a079562038017c39315fc8cb608265eaa21cf1889'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c': ['f9013fd0fea2fc60e5292abb94868b14a236e51535a29d090141e05fe80a8809'],
 'Algorithm/Estimator/KF6/Inc/navigation_kf_replay.h': ['e6a2c8926bdf07a2b45b072832a7cb35f41cb6cba800ed7e04e6b38c7075f566'],
 'Algorithm/Estimator/KF6/Src/navigation_kf.c': ['245001c071d53a537c292b466befbbf24a3a70ca464f0609f193b46bdecd9e6f'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['c0944b625605ebca38b38870fe4630ebf0cd42cdc3d645e0d7a393a5f9b20830'],
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c': ['8ef0c64721c02de63f747754744f8144754d6202fb571819e6d158e1d4e7ca9c'],
 'Generated/Inc/project_algorithm_parameters.h': ['6bc155dc5c0cb3ef35394af93de889038294eb2451777b5eeb2a27f33c7a6f4f',
                                                  '968ec29a4a1626776edac02413596e9fcbe5c5caa145a09e03cf1cc151b377e3',
                                                  'ae23cadcdef4fb00070b81c574900746e5a3c14883547a9b61208306ca9990dd',
                                                  'b1c884c973f93604a7fcb1da7ca310d5b96d9e2a2f2c0feb7c09626a5c6cf0ab'],
 'Generated/Inc/project_device_instances.h': ['ca5f4af9207a3815d3426eed5a8c3000469a0c4da69c68282a2817a7bec135fe'],
 'Generated/Src/project_capability_routes.c': ['24b097ce4c2654a6954703e3119ce69109274e5c0f5d913911818ad5dbe752b4'],
 'Generated/Src/project_log_config.c': ['c726766f99a7ccbf1938c163a4fe475b9d72fc380ab863f296069b0ff834779d'],
 'Generated/Src/project_log_decoder_profile.c': ['200874a9601628a778c6f462343eea18b49a1e21f8e1009a6806ce75a64f73fd',
                                                 '42bde4713c7b848a1f90a79c51aff33bb6c41ba5414b07531888b2069a203fbd',
                                                 '438c7d6328e485d8963e913b5f7f11aecd32a2fca859b0e3ae94590474b2a092',
                                                 'b0381344dee2c994808f0b44925d1290bb839f75b163fcb2c8d0653d0202d358',
                                                 'e4cd08ef1280178e969eacb7d0ccee9e5e7d6aaaf385ed882a9afa31793100d9'],
 'Generated/Src/project_metadata.c': ['30b8fcb2978805089a8fff8813995b1bbcb46e3cb8859d866cb385a7f5b4f648',
                                      '455ae2dbc64e3d6aace0068fd322e89c60deea0c96ac104bdba070c181d71ccb',
                                      '60ce8cec6e04c57c9e9443f918d8f12be0dff386d0a65590e6b80f93bb7d64e3',
                                      'be8d07aaecde85d3e1b82b97860474d96e1963a2ee087362e51f0eef1e4a3ecb'],
 'Generated/Src/project_mission_parameters.c': ['24073cda645ae34527d9fa776b92537175bc6be921f2587e7dadc94f853e1240',
                                                'd8c361f1d661c8b7a57b460f053dbfeb4c549dc7b98a9dcc7e98b58c5919bd5c',
                                                'dae33b4df356bed104e1a3f6fa4c557d2c056899571c1c6d16c3d1a388ee1d95',
                                                'f098d748055081b6e7c7bd7dc37cdfa222a9e53613331f96f8d50a00fa9f5d49'],
 'Platform/Inc/platform_memory.h': ['95f8cd499798c1555d1c6a5ea0dec5e02911f01b13e2b2f7c6fb2f306eca805c'],
 'Protocol/SSLOG/Inc/sslog_protocol.h': ['5b4eafac22f85f5135d58dbb42b696b50b0fa583f9b979a6a6b5f7fe35917e1f'],
 'Protocol/SSLOG/Inc/sslog_records.h': ['465817dc1964fc35ad4acdb572951d434c5e6354949c60696ba7ed061e1ed994'],
 'Protocol/SSLOG/Src/sslog_records.c': ['11aea4d69a47723ff4d6c93efa7ae7ec81502620e9680c4e99597e41e0bd64fc'],
 'System/Inc/system_fusion_timing.h': ['db35e6209e7eb292514390b2cb030382fafd7b636cbe5989694e35bc2ed8d3e4'],
 'System/User/system_user_config.h': ['8a853b969d5ac53177ac19dc99779c49702bcbbbc0cb76114b089ef7578a355e'],
 'Targets/SilverStar_F407/Inc/platform_memory_target.h': ['923eef7070b99e28e12dad5510820f309a89c031549a7a379eed972e1be93d5e']}

BINDING_DEPENDENCIES_ALGORITHM_TIMING_V18 = {'APP/Src/estimator_bus.c': ['fc85c37f1fd4c377e0edbfc8ab8eb9098b040badbdd5a4444b495336dd69994a'],
 'APP/Src/estimator_task.c': ['1e0f2e8dccfeaf69e31547159afbfba0e89237866bdbdd28949943f9618f532b',
                              'f3b02bea65db965aaab854eb12361378dc62e90c7aa3e2e46426c868063274cf'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf.c': ['35fa6f69c4614f0d8ffd5a78fdaaf85a6088316291a2a10c91166d361a817058'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['56e387c643f0aa385d1ea57e0bbb0ae002c5c66e3ae0d48c3bded6d16e41e2dd'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c': ['f3edd5e143b7d061ab75ddb1beaadbfb4f1894dfa900ee25c5b3f4ea8995589d'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['435c0243af7ceb7fa45d854135b66d3f5a968f5f226b14d79a2f7250d6f1045f']}


# Complete source/header tuples prevent mixing independently approved versions.
BINDING_COMPILED_INPUTS_ALGORITHM_TIMING_V18 = {'APP/Src/app_tasks.c': ['136329bae6f151cbf3550afa6e9f80279270d4e61e3843d1ca7b3492a261febf',
                         '64e56d767b42f48e8e4e3a6607af6836c9dbae4eab0afa6c4a18e18ada25c849',
                         '7c6543c6f2dee74cc78a80b6cd3b3dc89e881f3afc9575f45fa9bb74ad5422f6',
                         'bbf40bb40fc3ddf7b9bcc4416e890e39cc3900fba8d877616cbd83f66eefbd6d',
                         'dc99990643034f1abc7f2f9e0d9cb7528e9cc51cc93ba257421e6f27fa90d416'],
 'APP/Src/device_native_log.c': ['26b08e966edc64f479da50e5712caed67ca0237b0f806ab89bdb5f0d9881d6d6',
                                 '71ad695ac7a688bb56adad05c8f7aae64250aa131648680b063703590400d550',
                                 '941e60130e06360f03f83f84966bb9ba78b0cd224801cfa55a7dc6db679c04b4',
                                 'c4252af69773b26d8dcb62a74c9427574fa81270b7d590fdbd327d53dfdd601b',
                                 'eac2bd302febefc751bd31aeff434ea365eee2365bddf75e1b8a17e8e4a6595d'],
 'APP/Src/device_task.c': ['2bc32c851353ece2d2e05cad3fc2d8320e62174837606dc99b49094fa99bcbac',
                           '7ae2fec0b233373c21ab5d301ee8234154cf9d97ececa6df66322cb5f761753f',
                           '9e98ef5ddb9b5c5f9e6783fddee739b57c675f7e57d103992cd5870d04d7d382',
                           'c6342de7a673a017b9ff41b1e53f56ea07bc48297d8fc3df0048903363acaf58',
                           'cbc151988b53e2011fc187a97bbf94a3fe49a531ad92b49310f89cfce59fb31a'],
 'APP/Src/diagnostic_log.c': ['0896c770c151a67673a3f44c47eca7d26b8088a4c2c0068267cf95104cc16336',
                              '139d886c2e0f6547265cb3cc024d761912c91111081349668aea069fd4a6c030',
                              '4b1e9ade1632e48675d9c83f1c5ab03fa82a69fa77481e3f6bae9a9ff77b8e33',
                              '55292013815419acfb73feb5bd3fb834d4a7e309e721a058e8a2825fe4e4c3b3',
                              'bf89b4136947885e9589b9f8bdffe4bb81c2a24275d78126db536f266166e635'],
 'APP/Src/estimator_barometer_pending.c': ['1e5a81487f0b45e7df00ace55b7dfc899ecfbe62d98d7d56af592c62fe8ad284',
                                           '3f7487fb78a50510150b2e5972d15a527d4c30d63b4ae9fa3b32acbfdc169bc8',
                                           '4278ae92c98e9c2cbeab286cc69edfc7513de8a93780401a3c1d98c95609bdbf',
                                           '4b917a7d0a6fbcc3d2a64a24271d2b5328a256db1265777360ac78e1b6fc4d8d'],
 'APP/Src/estimator_bus.c': ['23caf36595f115163d8f6969ed5798822b184f7c8e8b2d0ba790dae7836fea1f',
                             '9001d5b6e44974eb88fa608b8624ce76d5b1f58cf97724192521ba110b9339d1',
                             'ddd6b63b834db1dc131744381565f3046a44e8409143440d3a19ca3872e62ccf',
                             'f032cfd9beba878a0b988872a278c4fb8daf15cea260f09bee08f466e18d037a'],
 'APP/Src/estimator_task.c': ['36c4d4d4e50e4becea505601ccb25c7a32f41ae661ca4b7acc4e1fa66115a8e3',
                              '8deb1c3da3e8430b2c557d7ec56c93d88816432e3afda9bd4062688acfe802ee',
                              '9d1470b5ac9aa444318d9b3a8344dbe2ce8f494b62f9c409b2346420ecf8c1b9',
                              'e593b471cdd412690d39e0249e50dc952723e301bc026725b4a5859010aa148d',
                              'eabe26e73c37921695609f2a21e8048c1b322cd95660d18f02af792b53b48bee'],
 'APP/Src/flight_task.c': ['44bb000ca2455060535218b58358dc8a5731ea3423d6d1e3349d658888c16d04',
                           '657d0ff39d7af4296b48a5edb1cd260f99682304fe8bbdb724a4b3d27b6c12ca',
                           'a1e2db9b505431452d084aab0928073f1608a71ebb232c1cbcbf7888b3ac0f5e',
                           'af10233a322d73837e6cfdaf39a22370df3d8867a0a2107693ff522b59e2128b',
                           'cb85008dbe404ac4db161199143740819eb5e72ccdfe5e24ec26e5a4577bac61'],
 'APP/Src/imu_sample_bus.c': ['01b40c233781bbf404929e57d54920f699382a818dce5b871d6f462917a2f7f2',
                              '39976a34648d1831f9e13fba60e8f7ba2e74c921663e348b5ed72e719dcd52b0',
                              '7ec5b7aa93c2e3295b5175fc1144911def198b638a65f089ad8e339a8cb26c03',
                              'd12ca8618025c213673d6a7ac9a192538c437d4190a0d1408b4b022f04304c7e',
                              'f37e5bd009d65d4951a4fcafda16dfe98d322dc0cb472c0376996128b4312a9b'],
 'APP/Src/ins_task.c': ['24b2b3fad3875b0e7f52c3fc535f0929fd2add52d180b32c4123e65f62cc393a',
                        '3fd06d0d0f8fbb5e7074c6da73079449f9567e19b30d1df8214672d7478cb3d6',
                        '4a1b2abbcf08e55771ac1d2e69a1b6a180f7600fc27b9029e5015f0764a43bc7',
                        '672802a81815157103e368f2f88da1726d3c9f5fa17bad732fd0626cf3e941e1',
                        '9b7d1cf2a8bfc5b7c9e2275202c13d15cae04be514fc6febb24059c3c083593a'],
 'APP/Src/logger_bus.c': ['4c1f9f4653c924a4c36f354cbaea60f1e234a5ce01e1e5a4688889263eeebcdd',
                          '4c38600411802a6fc3d28e3b5dba4ffcc5c9fdaf9190db84ef4eb0d30c72ab19',
                          '6fe07c6903c8ae051e0a7fa8ab9bf30e43be2c8287c4345032615ffb4901a11b',
                          '84664a9a42de7084da3ccf671c5afd99b65d8762f51261e20062818ef29fae73',
                          'b36d960e939e89f3ff99a43d91c2b6d743cc3a30e3e8463174accc615dbddf19'],
 'APP/Src/logger_task.c': ['1676704d8f165f318e851e0cce783517080b85c9bd8e9983f98c6f6f08063ff7',
                           '37f2ea6c4f5a96e2a80b9b27c2d73ae8b0f09c8573c85fa4475b2029ecbda1d2',
                           '53c26b97f7c09da637d73639b4719f1964c3f4c36fff4c42a45a4d6774e07d29',
                           '8c4e1d54483aa20f630fec42bdb16a80dec010e8a2465d8aa611a72dc6c6d972',
                           'cf14a90c8855be4d0ee2741112231a36f49037e044f46456ecf8173074f397da'],
 'APP/Src/serial_task.c': ['08eaa5506b58e9a175952f8c87058a8b9b8983f100f7b409c8d58a3768e6166b',
                           '1bd93d1d2035298b6a87c34cb2ad29ab3cd0e16bab518b1f1150f16e96e96464',
                           'db7865bd207e490ff6752b2eaeb3170c5fc7ad01919cb97a498e05cf0fda7ac4',
                           'eed23e88b67f9f6ec417c50e8098e7673ead1b93913872f8e541418441f2c58b'],
 'APP/Src/telemetry_task.c': ['2e663ac4bd6bbc61b7fa4b1d7c493d40e806af68d88f04f8da13302cf9592cc6',
                              '4a17b0de8e69958e08fe63143593fd1ba8aeaae8a3e1664c1fd3987542203cca',
                              'b49252d10c2597ce918e8f64d2bcbc1b9775d97b18163f115f5b12e82099a2fd',
                              'd19cedf9dcc79042eb1d13131e9685f62e37b0e59e75edebb80f62af6b9bb3ee'],
 'Algorithm/Alignment/Common/Src/attitude_alignment.c': ['19c5249c9286bedc4c2bce31893e593c2ce023726545fd61ca806ce7471ddf33',
                                                         '594dade164e57ee68141b9adc417365aa528ff7513f1d00fe9009c370ffaab4e',
                                                         '851247917a7b7f9010554e2e77230d42da60dc583c0eabc0dcedb180c2eff04e',
                                                         'a514b119a339e88688d25fa520b00858d1a579c72db156c4149b0df90bc26d9f'],
 'Algorithm/Alignment/Common/Src/attitude_preflight.c': ['0ff8a5379eaf10ff1b44736ab412582903d3b13bd6b23fe61901b0dbc7b15060',
                                                         '80455977bcbe7b41f81b789cb3c8aac1843f23d1fd1abd27ab14a67612acb2b9',
                                                         '96dd86c7a101194eedbc46c10de6695bfbeeacc69dc885e43f5df012dff3250f',
                                                         'b593b59922bddd3f3379e005f6b290ca9637abe47343873737b0cc85309cfd27'],
 'Algorithm/Alignment/Common/Src/vector_constraints.c': ['128a7831902323c12b6fccefed5ff70034cd2dcf793cea091a221acf59d5474e',
                                                         '3c81c2f69becc54286e2268c093c3c6ef0e1e2e25d473b233731130ecda8539b',
                                                         'b1fbf694286af4839517e3f6ea18c91b37b8fb1b0c053287561a8a1e3ae02aee',
                                                         'bc486e4924647d114f0287d1de2f85b24f78279a7e5dec7876f9b56382e2487b'],
 'Algorithm/Alignment/VectorConstraints/Src/alignment_strategy_binding.c': ['33b90adecf42c25278c2e2dddeefd23876443bc9aee2a10978ea73ec224e612d',
                                                                            '5737bbf000d3c0a0f6b115c0bad9a624abe74d2a5b05338c5d3ab8ac798716dd',
                                                                            '7af0c32c89aa650c5543bf4afc5a5ddcd2648bcda740b453f3026771973b42b5',
                                                                            'ff24a0f65998fc388a402c98de498aa6a072c27e249cf768754deb8a34fef678'],
 'Algorithm/Calibration/Src/imu_six_face_calibration.c': ['30a33355bc92854c9be1b86db257710e125d27d1d48b75f08ec38bff34f0665a',
                                                          '904540f0adf4640444c8bf8b31f24e84e7a88e9d403d1672b013458b2c78b6a8',
                                                          'a9cd74c659c482e2248865b090aba5bfdd6ddb283da8d0a2d5ba7f02504800c4',
                                                          'ef3059f0e36ee2d1b174600b1662321549347e72fcc0e81d23f092d394102956'],
 'Algorithm/Common/Src/attitude_frame.c': ['119586d1f218a6189492f85443faf0e8f650b79daedf5d80d0ef33a95a1f9927',
                                           '7812d069936af2aedc3e47cb1fd1ec65e9505ffbdb6d5154f0d7f34b5f2ba00e',
                                           'aed57dc1c7b3056fa7826e1b0361df7d4dd69182a435904cb08ca1789d714812',
                                           'e8f70b2cb29b6fa9a3ee0494b895fbab16e181a76631bb5a74d4b48e116f128d'],
 'Algorithm/Common/Src/geodesy_local.c': ['2f4ed55e5b730bdb5d8c853b276322da8ba6af46ae5feda683c48253c825393c',
                                          '48ab67f3432c077a4e2a7a6f4ae66f7c907c2a9b74615d5b0f09abe9bc05b535',
                                          '6bd2d5443c6fa2486556e3c4383ecf71ee1452a81be085a228baff8322dda8b6',
                                          '7f9e5bde04976d677e868ad04929bda87000bbfa3d3ee204645fc820ea92f57c'],
 'Algorithm/Common/Src/navigation_quality.c': ['02af9003ecb142d33e28c22b5860bf328360d396362179c99097a53905f7f708',
                                               '70472bf5ea7d781fc61af33ed0a5faf62c66e8f3ee33e1796096b1f006f7f5ab',
                                               'cc16f30cb84264c880005346c91f98a9f5a26ceb87c97198a68ecf0286ed540f',
                                               'd3186deb1144178d635ba790d38d013c62a7a5e85a6b36880f999638be2d5ad2'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf.c': ['071b0cd2251a2f4a5f1749576d4a43803a58ab7dd6e3befe86ca6875bd4ebcc3',
                                                      'b7f290f200862018fa0bd433c7be2d4c0fd9af8cd8d29c8620c4a63a4a703470'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['6f19b115ddc8c8872ef4d0f1a6b425666369630bfa2a7c1de70a3102dd0c827f',
                                                              'cdc2e65d2019dff4fc4e6a6cd9fbfe0f23ba579baf323417609e04dcb117dff1'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c': ['2a208abf2dee3a1e8f59848d221d1f6cf5840f4b5cb55b36b77b89c069527e81',
                                                             '4c3bd9d97f60ce5d0043e7d4a3db3cb17bbdede775c70a49bd1b5e225a0cb9f1'],
 'Algorithm/Estimator/KF6/Src/navigation_integrity.c': ['046db79843259ef0bedbe6bb4deda21e99036ab1769bd650e425929647f12a14',
                                                        'df946250d0064e9677b99fb5e374b388bdeec625032ecc5726795c9e52ead38b'],
 'Algorithm/Estimator/KF6/Src/navigation_kf.c': ['c528902989cbe837f333dfc74e11a673c232e963786d3e2d588763f8194d73f6',
                                                 'ebd9ccb465f7973467cfb52c537141eecff1bdfcf0307a464e117ad4c5ac1a24'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['489af1977654671d4b3dbe6d69e9b40329ac860885c9ec3c3c34f1250c24dec1',
                                                        '7c2e15dc2d15ec724896319a49fa768c4bd0c01cf3b01121d1304ca958900826',
                                                        'bb79deccf73d714d20b2b021ba29a68bbd6d8ad2b09834d032625c122b67d3cf'],
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c': ['1bf5d5d4991430bef01d9095854dd8ea5fefe93a3b8f8b7d230c514c4e971333',
                                                            '85441a7a63582ea41d8402faf40578307686e9274c704ac7a39db1f94264fd41',
                                                            'c01041441a44b59f98006e27c635efb0f70c68f553141d1bfad8246d7da1a4da',
                                                            'f7aac59cd9f671fa0009b20076a5dea5933b629a5ab84fc87abc47a8f894adc3'],
 'Common/Src/common_format.c': ['3c8783e9af61fc37fe1d2ba55b7ac855a40b9a93452cae0d3aa2ad8d832ab8c7',
                                '5766b4f8333d3f5bf8f8dab4ef8ec5db7ae0756e40f666a82921c0ceb7eb5796',
                                'cc6aa8605f7313b87567d5a8c917a637a3e2cb2d50199865f59e277d54ca70e7',
                                'df7a0106df0de961beff4295617acfaa2bdd2552df17b92af0b7cddc6444365e'],
 'Common/Src/common_ringbuf.c': ['0087bb321c34d25c95bc3b7be127089f5c62193cbfac7584da70a2245f78da1a',
                                 '914da8f177cb9cecde244b8a8beca62a7273e2109a7b6ddb7bb64d080eeeeb92',
                                 '919e237d4f9f5748dd8e0fd7135abde287a0572db3c0f59a033f3b197f022a81',
                                 'f996ef2581f86b2211dbe920b764002a66b0d1ac9dcbd136c576171644a24d56'],
 'Common/Src/common_spsc_queue.c': ['8ae4ba5bbd46c52e83fa45420e45b1beceb906b348529f822c51bf425eaf16d6',
                                    'afe43fef96a4cd3cc475be0966a54264dd0df95ba98bdc7f04f741ebf871fd9e',
                                    'd1b18f84754dac039b33d396c99dc8ab140e8c222a6628a09a3839fe9d397da9',
                                    'd7b93bf307fb9fafdba48e457ff4bc6aaeb8f10c39611230252b53d5ba899892'],
 'Common/Src/debug_log.c': ['25fcfc5dbd7ef0fee917bd2ef2ec46a72d17bf6c88b9d9eb705019ac7933bae3',
                            '550d8fafb2bb5df6e675fbc538f9a7f91bc864e01e3d0c9b05ee94272854aec2',
                            'd043156f5596564a6cfb76a61e51169688cce88b2915120b2f8a76a9a66f8c5b',
                            'd3e269d5dcd2520bd409563ea596a0fd8c2fc715469fccf3b6c399c73a626e9b'],
 'Common/Src/silverstar_assert.c': ['3c730432879771f956b847fcc8c31b29d20f9acf7dbb88c2e18f5a47e6ac1c60',
                                    '7566a07e509d46dcadd758999f9c96e9a4960f7516a7bde44ad04991045fc82b',
                                    'a1d7e6c82a42ad4c347249118ee06706979c301cd81aa4acdc5eeadde9eeca5d',
                                    'c9d2869b622e255d7c8dcd96c4a00c90130e2eb0e265ab6c2a3974769d79929b'],
 'Core/Src/adc.c': ['342f71ae5eacde32d11acde4cd4b21df9735ab97458947363933deef0ea0040c',
                    '3c72ac6bcdd55a3e08e10f2ea1adf3316c3fe1484f71023437d0fbef701f0194',
                    '5a849e6c845e42c9e9b023a5f607c99254d5046ec79c60908b792460e9e8bc67',
                    'c170f04ceb79448faedb5fce1caeef9f8f7e619fae8eff7eebd81743b32ba4f9'],
 'Core/Src/dma.c': ['5ce35a3d0c5f9b36397b279e722003307875977b1ee0a28a85649d9bc6921903',
                    '693c82bc8518a85fbdea5ac0f9ddbe75b4db5e98e83ce85c8edcc733e7f150b3',
                    '781c2af2c54129895594a04307e742ab0966e2e01d05d4f85353e8e9752de8f8',
                    '8463ea7cb35276c16f74b28a09f625d7d5839b350334141a43d034de37e71495'],
 'Core/Src/gpio.c': ['12b3b427aaf2f873173cf59c9e1e27a9b4d4bdc6a2f6d998bceb6c8dd1432236',
                     '5367d687525275383e4d50d6f673957e352856e99e3b62b1769902ea52fb556b',
                     'b50fd0d316797ba21f1c99ae4319b1f255f27391f55811dfaa020a506b2e49f1',
                     'dde6362ce05c63a1c11b1969b7060b99c7b311d221682d6096da882bf6a39abd'],
 'Core/Src/main.c': ['79a875a2a448d920ce7f274596ec03fba1170fbc7978378c5db20d7a6ae5b93d',
                     'a356c477ddc47b1791d8e7460f76fe7e0116a73e6519394c97a9863aeaada9ee',
                     'a7598fd316364045b426bc4fb50dccc7178784dd566d74e4edb38cbcc99a876c',
                     'b5706811e14155b8699446eb6ccb9850424ecaf07f1bab6bb2f4379f7dd68b5a'],
 'Core/Src/sdio.c': ['1d0c045731a0d48af11484743bdb2e96c118f46e73099faeb3048280fe15208d',
                     '29c9262d7bb40b1c8c0575ce5b989213cbd13e3e1f5a01d77e7cf3e32b941522',
                     '76692f62a5df542b6d506070c6398dcb4571bd69e205d7ce35892f9213276c3c',
                     '7ede29e1b34b59a7afa6a59e37830a26c4f4f60aaab7cbc690346a1a8c8e8fb7'],
 'Core/Src/spi.c': ['4fc511a5d0029f72cad90d27d2b3bd96115e8aaba7b5b241f6deb8d997ec3c8c',
                    'ab05bf6c87e5e2af5cc890e06a7da577e8d30ca92c75da618cdbdd5a3c583f88',
                    'b146f4c63b9527aa8480bdffedd3bfd39a1aa778f6457053f7277e0b2949db41',
                    'e048ed3638126ab4bd936ebb88784093b2771f97504e2e5aa06187ebfc5cec34'],
 'Core/Src/stm32f4xx_hal_msp.c': ['84dfa32eadbe5c54c03062a38e5489a6ba983eac53d83da3aba81ab12705d70d',
                                  'a9354fb31df9af354eca86cfac0787198b7874ae47ae862a7ddb18ad6a77fb84',
                                  'd4c5013dd57aa77d5e6e8d2b9cc0d8e5bdeb1492a24a158ceaaa13546caf16ed',
                                  'ed9f7709ef98559993c92e4583bd62bb18e1ad6f12f0ca62a15939ff045af81d'],
 'Core/Src/stm32f4xx_hal_timebase_tim.c': ['44f59fb25c10d7f0fb7fea76ef5bade4a52c84d4c344d574984390afafd8289e',
                                           '5a6d0b6862a2e6abb298837bceee085df9c28d5a8493930acadeef6bf151e554',
                                           '841f473181ff0350a2c245e14aa09467ef37c7cf88e4468d4c71d282fd1bf709',
                                           'b9314578598d215e00c0d7ab1011f13159e5984a42193d3536884506d63916ff'],
 'Core/Src/stm32f4xx_it.c': ['5ff63252d723cfc6783963783d7670e8cc5495cb568dae7e348bdbbde9fffbcb',
                             '75ddc9b704c0057314d9c0f0628a003bcadce32dccd2b6a56d4a07119e53ca18',
                             'c6ed86b03ea91624dae74e0705ce5c4b49dd1bff874cad61276f91d0cce8c5cb',
                             'e99b7eaf2368f6699864614f6e56c55c2b7a44e428f3a8d70a4acfbbcf920955'],
 'Core/Src/syscalls.c': ['6467d0f71b9966ddbafbd5043bf25b1fa1cb45e7e68cbde979dda4524de00d55',
                         '6dde990275d8fa993d7b2d8f64df170fa59c0003aeefbdddb32df0f5a6549927',
                         'b243dc9beea3c011e93b59892783cbf32bee1e4c94b74c93a18a47ab921a8944',
                         'e6cc6d70e8a1f6de72c52db55885a018a9b9efabd37e2c5081e887d861293f70'],
 'Core/Src/system_stm32f4xx.c': ['20016d84fbf4863d3542c322c70035fd432a8813f986af87b1f16e8d4b95dc25',
                                 '6022c9ea7aecbbeb1c7b2217c9351f9b51d73b8ebcca950dff89a832c3bc0ba9',
                                 '93825e8fba07a1a0e2c4c4b194be1761d7f87fc51eca0a038fcd314e8fdd00f7',
                                 'ad6c43af918809ea962c337396b08c72f19ad7317132601737a549df895b4b22'],
 'Core/Src/usart.c': ['c2f76ce29fc7880aeb527401995702558b2acac0a83992fd9680fa044ddd621a',
                      'ca82f5a103fb58277d00c9857b5aff9cbd01bc24fc273ac346eb7062d5e1ff0b',
                      'e1d3910c2ef88540463cd043fefa11152026558a76f6564cd35924e9b137a037',
                      'e488dd8069bcd34cc6364acb1edb291096a59534e1ceddbd99af39087df7847b'],
 'Devices/Console/UART/Adapter/Src/uart_console_adapter.c': ['2204c7b9c0c981f5eab62aee27cf87aede5e9770e958c513a2dccb76cc06acf4',
                                                             '26a915eda1a4b76d86196ae8e3f792b0718286d2da4aaa3d3c493dffe994f161',
                                                             '510404c4e30e2b70a76bb687db0f6234a50f78a81de7a4be80e1859fb23ae768',
                                                             'b4e913db9b7751b9188adb05679788274f423854e8ff8ba4b73033b9a1a5a750'],
 'Devices/Console/UART/Src/console_uart_device.c': ['29c3c178f71327a52267e41bea8c36b1a29633f3fc0494eb9197afe98f3f3f0b',
                                                    '39a4bb842ed2c7ccaec7e1b80b0347f299c3c2bf6528e67d3d99cc70ab20943a',
                                                    '4c6edf3d8f476e85b486f9d32cbb0542ab0e055d6b63ae5358ee2d9039deaef8',
                                                    '9d2c6b0640677db33c3a72a5d19baaa7612020485a3dab01e1af69fb6f0446c3'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c': ['757a56cbe3810bec9c9f68808e664d96f04787b3fe6e698fba750a7c6387ed09',
                                                        '9c37bbff75e9bd5b044ae050460b5cf83af0cec89ca8f1872802dfab093284da',
                                                        'de693c67fa2b3484830b05e64eb7fc2faba96d38dee94a3f7c0bd07cfa6ce06f',
                                                        'ff3f52d8843dc4e7dc65d38730159ec32c6fdd1e95d49f0e580122d63b17193b'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_system_adapter.c': ['1c3503d4db3767484d3daacc07e3f8f10a205a8f4e7dfc29ab6341e4db208c6b',
                                                               '485f7ff6470f36da13264d603a99ae06e4df4681dd3a59e10b5b8b9ec91eeaae',
                                                               '784013598e4c44d54e4da992d7a47a9c2e0d78f79de3fa50a998d184d01bb623',
                                                               '8032fb6d0c56f45c666856d45277a3f4a0424e0190a5fcf9189845e0f401b40e'],
 'Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c': ['23edbe6bb772eead96b8f3ca3cb58d8d124bc2a6ab704cb9d5adf2fa9af18482',
                                               '4dbb8e12f94b1a3765e9d74f67276ecd0989f3196337aca6d2d4480318f49d6c',
                                               '66f3a4f904d002060cd51738b14594d1342ae26f502ba3552030281402763990',
                                               '832ceda048d3144af2a8d69edebc5d17aef2952785d9234c67377ec9151f6380'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_barometer_adapter.c': ['1f947fecd57172ee72e5a7f4b4b668129a40fea5a848fecf9de1395c31367548',
                                                               '9888bab7dc91718f349883606135455328138fe6af96f1db807147c34204a440',
                                                               'b30077fd67d82489be2c0c9e522eba59eb72a4b38519af807d9eadbce17b03eb',
                                                               'e902fefe0039f8f4c5ec490e85e7bfc568e4c27d9a6eba10300978c653e77646'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c': ['29c5f203e59b7a94341432ff470f53e2fea450bed2443935d11a524c0742b689',
                                                         'a716bd2d00b62a527392937fe06bbf9bd5179995fbf9f04eb0fffff5f1706f06',
                                                         'bcd504462fac3a4e4a62ad7dda6d4f6bb230a7eec29d3e6b793eafa0c336fd70',
                                                         'ea13693826d8be07984d4cdeefbd897b00a4675b0bb25625d2e2ccf87a490891'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c': ['5633524e00e796c9467aa889637269320a2180658cf0dd61f3978817f526d42e',
                                                                  'c5baaeb8f3a324baf64ffac5c5e1972d84fe4d8a46c23c1be8e998c51ca358af',
                                                                  'cc0970bea24433cb97d0ecaaabc467a015f716227aa04d1dc38aa02be381ec6f',
                                                                  'd2754f73967fbe051a702ec3dd165e020a0ce065b7a39cbd5badd01739442364'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c': ['22229ebb24cffdb8da97a8ef5eee7a65122052ad9d7be7e325d108740f136b2c',
                                                                '4baf56ff06328e177f026af561c8a0adba0ad786ebfd6e480f2d421bcd98b51c',
                                                                'b987581f8f7bee94db5330436d01a42b075ecdcb39509b01048bbb3d07599cff',
                                                                'fb479622942a91b2f92906368554ab3ec9a354cc5f387ed16819b3f2bd065fff'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c': ['2f52749d64c6874f0f67a79c99db300352219a7df4bc7b90248a36d00c4bff32',
                                                            '4361e8c85da31b4520da53c722f88ddbcb5bf3af8b2d984748084befa5532916',
                                                            'ee1a01c1d8e10eb064b4a861923a2993cb4c80bbe10c0ecbecc15cec993baddc',
                                                            'ee7473f1111a858c7b1afb4246e4c29b3c21413bcc9433dd2fd9d3a31fa77e2f'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c': ['60701d4cf1bc4f9c03d0af75ad53e1c64e41939990442743368f8f2dbf83557f',
                                                     '9bda16ca72eeec9cd1a12904d61e036514cc2076ae768cbb772d1ec2e041fb6a',
                                                     'a0003600169f208c315784ccfebf1dbed5ffdd0a46360d93936d7bbf174b1bd6',
                                                     'ec0a0c8e942b52a3d4a7d0b6c177537d33701e06a4792c071acbf4773dd8a6cf'],
 'Devices/IMU/JY901B/Src/jy901b_device.c': ['1d4d5675354e6986d126756c30870ca1a8431d2b1e118bc9da45c433249d2a94',
                                            '22fa7b96bca25f48602ea5f3c3b25252a39ea7945519a9a621c47a052d5f08b6',
                                            '498106ae99c4c2dcf7180ea2963575187f9eebff8ba69f58eb53e3515348b3f2',
                                            '8ac2b1e316700a587aea0c9de7b4859a662b1d760d382d4af56664e31df7e6bc'],
 'Devices/Power/InputVoltage/Adapter/Src/power_service.c': ['17fa7ab6f0ec6e7be52a935755d767391349ba9fb46e45de729b486f180c229d',
                                                            '7163e7eda85a7b5c6c28a0815c918ac4b4768d551b5bc43816d36e537f4f6911',
                                                            '7586db522c4ac767b985fda83c9f048514244ab13450d6f31e0a63c6edda6ead',
                                                            'e33869278431aaa3758a5b15c2d5816b3403f1859aab425b175fffd06ec1f710'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c': ['02e7444db1d5aa900ea3d5318912fece876f24cb23d3d7d428500f66ec7d702a',
                                                                '155e0d7a19d79843d09fdf18ba94fd4108a675921464d2e01da1b5f32741c53e',
                                                                '4a617650314f1eda6cec19a8f8322baa5361dbeff9c5228038b1468ca7933642',
                                                                'c951f56abc665625ea2d15016599d5483afe46ac6ec1946dce5b543477664674'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_sink_service.c': ['120ef33b176f3af4f4f5ef741200dc527de3d1578ee9842968d90c1bde64cb9b',
                                                                '3c2ee12e46560704926d984a721edbb346aab617fb8a2826ca373d3ad15c5819',
                                                                'b1f873f9ba4ac9137ed39c5642508b267091a379e0146566661a37ba50160c58',
                                                                'b84bdc4688923d92d9ebc9258253907e001314b55040ed02dfb8d62daa9dded7'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['36766c683ff40358282a9b3559fd550dd31b3953583b37f4ea5da6efb0d5852f',
                                                                       'b79bab8d7725fc4b447944ba4ff70488ab8afdd605bbe7db805fc808ca86b51f',
                                                                       'c5a6ecc9c2485591e5107e154eef8198d0cd14318efa121525f9d0f80c7a49b7',
                                                                       'eddc7123c315c5858cb4381edab207e0a9a0bc3c9046e7c7047ad97eb175860a',
                                                                       'f4c4772f7128e91b6968c70295356eaa11195db707e3417bd2888838de215d8f'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['0cf56a3ca9ee059de8e08d3a5c98f09b2ca7cd4778c85ec9be8ce62f8e6c86e3',
                                                                '131b84ea11d96f57109127c1525e8b79de54cd6393bfa57f8371716c5ddd1229',
                                                                '9cec975c2e4816c09272573a9eb369d77ac883b30c1432f1e9d0a5719f6bbe65',
                                                                'd1e299e106f1eb6fee6fe8082ba805c3010cc095cd36b0d987ba9303a9da8d78',
                                                                'd7e1c5a1f5c0b63c49718839765b3215cd6b682ba12afcc9cb7a62f678925622'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c': ['7afbaee17988968d6326b4ab375fd5387c0138ab1b722a4ba6cf677eba789ddf',
                                                                  '9253b01bc3e48ccb24c8e0a609d5f3977f4888cbc39c55e919350f23ec531d35',
                                                                  'ac6ab267115354226baad9e9763a03222ff93c698748825791bf2a5947899371',
                                                                  'bcb99aeb2cc8249080b513fa187110a832cacefffca104ec2498dc2af8493776'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c': ['329a76689db87ee019310c8a92154ee153b2ae13f4c96a5893cd4d5bc78b51bb',
                                                               '3d2c7fde6834346bf31e60aa41fd04777d7669cd8d4defa9dfadc796795f746b',
                                                               '469ef7be0695b8a38951251a5dd85b0b858b8f09dec7f9adcb2283ceb21ae4a9',
                                                               '5fc5830d253903707fb86176e62e206b8f7acbea86042ccb605020186a21290c'],
 'Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c': ['2f89c64b176e5193b3b4141fcf0b4d36d91227be4ee0d2f8fbe458383fd9f52f',
                                                       '3d22579be10e39319c52d03865a2b1d7018bca145877575ff9a2955a6ee436f7',
                                                       'b89a3abbe0155c6b50eb15f2f114c474c77f3289801ff528137440f98600bcbc',
                                                       'f267479828a4d3e2581989d395ad157e403e1bc22312b371b9fe5c573cb8abaa'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['1bb4f636731caa89acd908d31c0771d0cd6718dd47ae2e10a34495e5fda8e9ef',
                                                             '41f93711a1717e3a45c807bee881f28609569c3448801da017c148382d6b778a',
                                                             '5539466114e86c276132a1c1c2933591b4f4e494efe7a8cc6170cb9be283b4aa',
                                                             'd07979b12a2625c5b647cbdea66c1cfe24c4b2523f4f054ca2bb3c8a99aee399'],
 'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c': ['18773018388f929afceb0f9b480cde0d999f78a587fecdb78c391ffb1a0b99fa',
                                                                     '278e39c02264a770b8b0fe47e78eed0355540db13b5222e2aa758e7d3e4061b1',
                                                                     '4df59114a8c6b573ca926d7253cd54f1af2398f56258f91c9957115eac153b95',
                                                                     '8e63bccdbc4660e6ded67a33df16045821c858b8b965d08813b10a9b17dbb2f1'],
 'Devices/Telemetry/SX1281/Src/sx1281_bus.c': ['28ac365344540d40a57c1ecc58a39de0985792658d5c5e1b87d544db0aca2d65',
                                               '428b062e6b391d5403609c2c5651b568b1207a537dfd07be9b6fbd7ee056ed55',
                                               '51e93fa58750ac5eaa89977adacebac3a6575ce85c7f30fcc42a4d41270d729d',
                                               'a17707039f0b714efd2254795dc5f7c8bd1fd946e3d73e044d297b245ca7a9b7'],
 'Devices/Telemetry/SX1281/Src/sx1281_device.c': ['126988aedcc33690584e4d13a876b02f2bed311cc2cab0675e20a2e647e09091',
                                                  'c5b5d4b310e9fabdd03a5775aaaf5bd018751319fc8145d4b0531007d742c87a',
                                                  'c6b5edd611593b5c85f9b85126dc7fd3cc050048e1f042a8b1b548ab38a9fedb',
                                                  'fc043030c79af75c436b8c324e34518a538b3702be50da5dd6bf2cc15d46aec6'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c': ['1cab60a51e051d2a6b71f492c052679e269cbe0f7eeb6427e1129672c289a363',
                                                      '2602c7c54715bf126eba6b22a249e7e1b6a9eaaba8208353f07fdb1a6260f558',
                                                      '8c35a248ac1b166e06635fa7326028221986efe480d45155bb2a98c64917b86f',
                                                      'a8a8b17be325e4aa06d2fed4fa6b9d3f0af0ea7e25f0d3e69505aa750ada3f95'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c': ['4819a3eb00b9ba4ff1e05a09b1e0a9791b23c15f74498d2e7a5b98427906739a',
                                                          '885dd78af7b5bf618ae842c0b9a97b1d6e65b49576c8e77e87df00c3c15b1cf9',
                                                          'ba3cef7139e31b83edc559ff670670f9021a03ff11cfeb4ec07dd5a5cf3cfbd5',
                                                          'f290eb04d104d4ccb95d5bfe0bd626cf61177d1d7f585e754bb66de661d323a6'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c': ['3cf1bbe1f276a826d76c4cf2208629e4eeae0294325d48d1cd0bff5b42929c16',
                                                             'aab4616fa7cfda6a7326dadc4ad99281116758a37e9bb710076691ce629bd456',
                                                             'b87b8843398d0802bd4bbe6c224022d463f75ba57915026a19c58f8326edbc5c',
                                                             'e5c5a200b46ef520518d7cbeeb61e8e5636eb9b30bc2bae94046a6e75c6f6c71'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c': ['3956e9d13b3cfca43142752067122b51fb83320d2ee661f710d9eb4bdb21ad04',
                                                             '4f84dc7c42041e5546f03a6d7f6f25be66a08b4787db68579ebdaaa8e62f0889',
                                                             'ce6ff2237fac64a9b3568e4eba244d943fc4561f24b3e5d2d59da8c14fd9a308',
                                                             'e6f80d451916ef67c5a84ce0c090525f79d67aff8b5ba801312e3eccde73ed6d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c': ['33c5617605ac783950d0099b488971c83885cc2e6ef45450fd5f90f2671d3aae',
                                                          '8a3ed521d36eae8a8265ae63f6e3152b4a0cdf3ee5796c1500d3705f9be123db',
                                                          'e9f0209e92cda15efb0cf11ade2978c262114248b75901dcec5bc3203f14afbf',
                                                          'f1e56c5045c92c389a5b3297b70647929aea72aaa80949752b1e1c24a3c80d8a'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c': ['29556f252d9075355cb623db3ce3e4d33b0caa0912b40395ebecdd1399d4f7d5',
                                                             'b222cdb50efea51d83e9a3102ec695bdd1c882b691eb2c8a5e64890c41660c16',
                                                             'efd9318fba28ccff504f1f6cabe53279d7e33be50cacf58d1617e3a0c0cf4e9c',
                                                             'f2859e19f549ba4a63c4d69fb44c0a696ef3c167838e9e9498c9aca5ec91ab63'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_exti.c': ['5f8be11041253332322691f402888fb4fecdd0b29fb5c33fb4efcfaf2cd6fef6',
                                                           '983844d57f4f2aa19464ec5630511bc5bd903742ad4e12f87b99884ff40a520b',
                                                           'c9ef05a0223537ada9b49894f78ec56da91bed55848b30b215d6986969f7b7a7',
                                                           'de6401940b59985462e1c9f4528e4a9b047dd0281b035a20c97f0ba4e6b7367d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c': ['637db9c17d05478838a89234a3885ce05a6c2a8190f6b069bcf933b91c3eff51',
                                                            '6c7ca4f56081abcd877ee769a1b6a56396040ea51e4721559b0c593b88daf563',
                                                            '96e7e86c706b8dfcef534d4739e59fc4766b5772a054aad635a67d1527c9aed6',
                                                            'fa77d96f5bc16dbc134de01ed2e2f17b73aa6dedf53031a77c2d439454bbbb8c'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c': ['6aa959aaaaf214c7f1b03caaa79f7d77b4ffdb18b78e8d90c520d2695af67079',
                                                               'ae2e09edc940d17b33832207c2dc4eabf7bf98e9ee4000f345b408831a0b6068',
                                                               'd791cb4c2027465581237d9d017792f4a2916ebb4d328af8b86235e7489006f5',
                                                               'e584adc8175d42125ddaf84f6aca36ad4d378cb3141d61a2b67e107b28f3f069'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c': ['40f76ef1c4fddbe809daaf8dae26b172715f87951e6fe82a4e591f169281c949',
                                                                    '8b763bdf943f04d7af392952956b57595a1d0c843435e58a89e3e8340633d9f9',
                                                                    '99664be99c1c9d18d91715ad7cd4da5bf587dacdf429caf2a7b59a01c53b3e77',
                                                                    'cf17de4233f7680c429a6dae6389c16b55a93bc767f137d7a9d558d19a606a2d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c': ['32ab41dd3ac111bcd187c27be7e32f46b4dd677b9a63a8e08634ae9cf31b9b89',
                                                           'd5061d3d851c6113db79aa9f1ca4aa8a6e9ba205265427d500422fbabec4ac92',
                                                           'eabc3e9c68f6649f1e9906f8042bb427bb1f91bd5e3b81a631dddb8d8c1a4d9f',
                                                           'f14dce0772c9584533d89371cbe6df1d93a6850ea565b8382373e5e79bfdf5a0'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c': ['08b3ae7c3e865283e5f0ba7a0ad0763446f712f97924c89e1e68d36211221f81',
                                                          '912da7c47212e8d5f99aea6efe7a14541a6077a501146c973a6964ea501aed11',
                                                          'd8d3c2a7216a6866383891cc7bcf0be6494cd09be14f644a85d4c811f08bdef6',
                                                          'f6b772deb56d4ba4923aa0876f58c415b98c96d71e5547faa157e5e0f038b506'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c': ['2a2c78de5f58b543542c2ec5a1f0b7c44b24a4bd0fe6872f117eca01f310479d',
                                                             '885efa072016ba695d8f6da8fedc742960c407d9e02249a764ea17dd951b5f30',
                                                             '8b5c748cb4e35b755189401bc1d79492978cb54ba3f5747ec27584b871be7c08',
                                                             'f4c5e25f5f259c7bb03de897f1fd37791242840d40f32c41dacfed0f4fd57f18'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c': ['589a2955876620ca2b274aad066574ac274c897a72a768d0b085d8a8557678c2',
                                                          'ae0e2d309447f9138a5219117ead9028aff769a12ca9fd13d6edbe18e640e9e0',
                                                          'dc854408a04afd61668632f694683f92afcaf8692fec4c37369717759230254f',
                                                          'e33e5e14005fda756d907534dbc670ed0b30c47f1a1e01b9ff6629508783ba15'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c': ['29587e4cbd9cb5b838c0319ee22c926ba9d1bd67398250722eab524c285f1e54',
                                                             '39274b00778a5c38685cadcbb9dcb50d7e264679bf133716684db9a2328ee5fc',
                                                             '768180fe52f6682499ae47e795448c2bc17aaf3a58a4a41acee0a7205d9ee93e',
                                                             '835e150e67f441fc198b07dfbc4c34154bf45803c40403cd448e9bcccbde150d'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_sd.c': ['23c18ceef1905124f72368feff233d74179e5c2ff8a0a472f5d95ca3a3cd6a22',
                                                         '7aff9ce12b77a13baf2a08f7b867ed1e689fc821578850d88540dfba8b368d28',
                                                         '9603242f4b3ef03eb322209e436c21a72fa82ff9420fbca8df1f95f764e4e003',
                                                         'bfd613195a44a618677049b7d79a2f196b8d3d7067a35a7885ce1cb49a303fa6'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c': ['59dcaf4cf727c2b1b657e9984abc647e6edd35eec8cac7fc46829196dd4f91dc',
                                                          '5b3cd636e7c60abb853aabd29299136d59b59893d1c7e4914cd4667c54c390ef',
                                                          'b07f5a76309a1547dff90d4ac90116a0ed42e47c48b1bd742d678e9fa2a2b00b',
                                                          'e6fa155c08f3051598b0a14b633f912d6bc831732ea3e5922fe7c0a2b03123e5'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c': ['8004edb5017ac7ec9fb17e98f86603e29ff88553fbcd838327a9890ac027f75c',
                                                          'b18bdd7add93d137e2574474b639d5b04fd76c2ae9a79ea5c3c0babf40ef615e',
                                                          'c46e71767c95301ed4206a2426571f039d8722db3412115524116238415f086e',
                                                          'd760fd327c582a6d705704dff3e20f39c06c2aafccbb5fb493c719df855633f0'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c': ['38c61ba5d6ca05add7f4b18e2c9221dd2c81528176570df9b2a8255ea7601682',
                                                             'a60b1ed034ba5199b7b597c3a73adab8fe39a9bb3644456d018ab1da31bee89b',
                                                             'd98e3468c29a183031de24d0e0741e1479a6268fdfc156ade1f9496989ec2f03',
                                                             'f3565dfe7e4ba8334e48a976a6ea1a45ab34b124dacd9f6bd82c81f69ad57a2c'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c': ['7eacaa9f8d46dc418eb7d59fc9b95dc81c157481e8464c50d844ee2f8dac82cc',
                                                           '92d9c4e208e3f56af4bb307f4dcff44d2366d2b3859aeac48447092ecaee7e7d',
                                                           'b81ce1daa8c5e40bed990883e24ef24e4a7f87352a84070a462428660a008271',
                                                           'fa1d24d8ee8eb3246c532e9bfab637d2bad98cb5ddb18b20d4479698a6cf0843'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_adc.c': ['7266de2cb9b96bbc080e6a205d722d6106e184ea95e02975137a434a10712126',
                                                         'bbcc84be929286ca42352884c1842148b6f6841619d6586b294dd6e8399689f4',
                                                         'd3b48f33f885657a887372bdda048bfcaff66970286baa9a67d00cbc899a0d10',
                                                         'e5f808ad4d84c93956e90ed934d342d1eee6592f6a0007ec4609e63112da16bf'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_sdmmc.c': ['09662cdfb032a42a51ff528e7dc3a4112409db1321611d118b5a6a75609b57b1',
                                                           'b9384b8f683586baea3b16c9d7eca87a4f55cf524ee9bc00c2b0740d99a2303d',
                                                           'd289a7d0da07fd52fc5ae355191c6070d71d5a599af6f3c000eed00f7fe6accd',
                                                           'eb34ba30fffeda3478c961400728cca9c7938e73d445cf909893e1798f5d8c93'],
 'FATFS/App/fatfs.c': ['3c31dd76d078c39dd9379a3a6b1d1af74732b5a13fb1d8ad19a6df5063ce3503',
                       '3ee3d18d380180c41c70021658c5af7f0b83fa123a315d2338b371446bc0b071',
                       'ab199bb12ddbc44e1f30fb6155c7d1e2722fc5dd6632457b508b38fcea6bbdc0',
                       'c084753cc634a150a9ab0ce232087c7dcc9635dad0ca981ffd2418dc67c7b131'],
 'FATFS/Target/bsp_driver_sd.c': ['59c42a409bd9f25d9cc24254f6aaefb2f1d1d42d0d4ce057416b21be65c1063f',
                                  '59d150fc2d48a1392f87da9b7180bb39ba5a5d97af1645052c10a62c76b2e50c',
                                  'ae5007d3debfd7779b84ac4c153eda93ebf97dbd3897a5c4029072374a290dfc',
                                  'b814018a00d37f9a844dec029c7c7cc9f9af1281fcee028df193f8e651fa9718'],
 'FATFS/Target/fatfs_platform.c': ['5ab74047ffe4b87ed4d6450615ce129cc46ddbfb6b8d4c9b9b1899cb4aae668a',
                                   '8df12984f54080a752f4f8c51d7326025eeecf152c7f772e5b777f0dbf458f2a',
                                   'b996bef864be1d4f3a9aedd81af88f6c3c7178c7a510ae5571b2c95038d12228',
                                   'c24bf204b27ffb6c55acc9f7fe686b19cc64a7ab21a55eced8bd385a14a0e7ad'],
 'FATFS/Target/sd_diskio.c': ['27deb995b30675664c00db329cf0c51511d885dca52c3bd0d9cf6ac508940453',
                              '51f9619830b9c3060b43a2359f1b75d2602af80555c2e8f86e982e6ff1610784',
                              'a5f9e04038ca7a241df5f879950fff928b0927cc5c410d532583338433149a18',
                              'b714c480e10ec7a3cba236ad187cd4016a70f510a506d2cbc827d3920c29150b'],
 'FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c': ['3dbd5784bd1b1d95afaf7a1bc68b34bf8e83793683537b14ec98d421f6fe47af',
                                                                 '712f587e217ad7b90773437c94d7336533a850c717bdfeb24cc4c989dc44d265',
                                                                 'c01129c5c15bd656f62cf5237fd8fff8c7c23256f7a286205809512ad8c4c63f',
                                                                 'f2e814805f869b4775718a908436b0ec9d43e1563aa61d65adb03889c659ce21'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['5799a5d67849d134cdd113f27749121401f4686bb1e0b162b10ec6970150ec7e',
                                                           '6975fdf66deb8740642535d001d706824f17a5c6a5405e21b3c83d32fcaf5efc',
                                                           'eefcbf40c640691bbea6629aae575d736b330bc4411bf81d8962d9a3ed19b04b',
                                                           'eefcc9c11cfa9390302352845f47c94761e637089f4a66fc7d6dbdb6734705e6'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c': ['07e7dba487bcd6d1530f3665a3ad6e568c6d562c77fe448092598d54052ba9d6',
                                                              '3913549cb25ca7c44ab3c487c3aba4f9fc91215b7b189f1562eac5ecc2cb68be',
                                                              '44b77b2a25c86e4e7df4530e2b844ae3ed9fda191f36cc75b79600c7aad2788c',
                                                              'c3fee572b52d1f6ed8a5a7edc2720b9478b0b45a113ca16aed0c5a31defe78c6'],
 'FlightLogic/Indicator/GpioStatus/Src/indicator_service.c': ['06783bf150dfe51f3348afc33f01751fa7182d0726a87163efdd9fb88916da30',
                                                              '13fa639665ee3e0e79768ec1d180d861f35236ea396412ceee1f44aad4a7a31f',
                                                              '9b0a969b8702c570bd637665fb83ad28032fd7ad4ad01dbbda720ccabd43376b',
                                                              'affb2e9de51efdc88ec383fda410320a8057fbdb5baaa5dae135f69e090411a5'],
 'FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c': ['0c7c2561a06fcabb84f246830078a5f27ab1a1753a3d5a23f85144fab2c4f394',
                                                                 '1c4876c46111cbb7bb24a811d6116893d654f37d95df657690ae239b0112addc',
                                                                 '4805756dcadc54aa70fe94243ba53c26fa1cff80079315a61c16112b5cf535de',
                                                                 'b8fccf5d3fb2c733f035c527b73b9063bb6ec2cd11b5e635c6ca86f1d9a9ebbc'],
 'FlightLogic/MissionAction/GpioOutput/Src/mission_action_service.c': ['04a55dd7fbed79cd957043df1bdac52c50656a688fb8906b1bd64a73a26ddc8b',
                                                                       '7e35dccfc35b646d4e1d223b907618b79bf399e62e5c85a0543f05a834f9e471',
                                                                       'cf4618ebe513d12d9f8a22e48b184e5dc92cb48209693f1987f6138e4d24a645',
                                                                       'f4b22a32faefa5dbd8d18c28f0c99cb77e0479ff960ec46cec184e7f5416a480'],
 'FlightLogic/MissionAction/GpioOutput/Src/output_service.c': ['5357154efdb15f0564db754ff5f2279bfa2b851843f4bc654e99709f8c97ca22',
                                                               '7ca68d0dab053235ac94f31b8bc98948e292118d25b245a4d73a95f788f442f1',
                                                               'c6acf968e01407e35319e69fdfeda87fd1fc82accda38e067155a36b909e754b',
                                                               'ee82f0c23c92db01d4ad879e6afe27803a21afd9d0a6f58eb16e1b7af1e29eae'],
 'Generated/Src/platform_resources.c': ['4ab5948f5460596bc803952d7cd35f1045ae17c705db8f58810fbc9b4b36539b',
                                        '5d98146879136deb3b7144253074b7d7d81f5e2c868f91431bbe4314abde5310',
                                        '7b551a77b78926f6af21b4d8146092a014685c6e7596bcfdfe09b4056a51a2cb',
                                        '9677be8a20866f3a744eb2a28e1a98c466e23e12da208fdee8c478de1b521c76'],
 'Generated/Src/project_capability_routes.c': ['af0761977957712c88e093b1e8199e2c9f6e615091ee7d83e05334a2e30cb0fc',
                                               'bf2b78ed3646daa8d18a750fa8b8b3beb9dad68c4ee39fc6088db2ee2ea75f41',
                                               'e23b6e8270ff828b6fb2589dd614f220584c300b2f4a69d1afd3cc907c2ae3aa',
                                               'f28477fc94e422ecacf7ee58d3a1dcaf814601432b1d2f522a1f5844c090b8e9'],
 'Generated/Src/project_device_instances.c': ['0f69f47852c18cbd0e664a57c23d4da7a04cb3df303d5a92b541a5de5c4da995',
                                              '4d9e7e2b75afa83dc0094bd9bbb06cce67f0d3d85095b1872ba50d73390c3425',
                                              'add0c633588803065efed18a71bba69ca2d6181f27968a2b742457896fecb2e9',
                                              'bb534fb39b37a3666ff30c6e242601829288611a16e2a2fae36243802dc1a709',
                                              'd2762a842db3f899b614b6ca2d0464566df5ade15aa1bb11e6fc785cd723a0b5'],
 'Generated/Src/project_log_config.c': ['2a1d78c42670e7c4062472ba1a3beca378a77298565f3848a47fb28b428b9427',
                                        '3ed5799b9ae16ead9528aafb2d824f3805fdd5545c430864532ae285e3e156eb',
                                        '7a16164e649b3833878e9f3b76557797bc60aff059750ec25040fbe7cb627902',
                                        'e8bce06d51705cd6c8703f714ce71d3a34672fa89255eab09df95247ee05bbbb'],
 'Generated/Src/project_log_decoder_profile.c': ['5fb2f79c4041b0582d1871593b837ab51c457bb05502d072a68e34faf443dac0',
                                                 '5fbfdc0dd44b001fcc13025cf0cb7b5f7cf6fab67afb3c40394ed11298630bf0',
                                                 'd40b03a314e1ad6e92afafd4321139901664e5dc1e55b72e32c0fae6d865d979',
                                                 'd8a459c258667eef152c317a214354efd7ca5f2b19ca9a5699d9373487c847f1',
                                                 'f356883e5b40a4fab6538c6220b305fc7ba041fda169be58aa04f12c5f6bd55c'],
 'Generated/Src/project_metadata.c': ['01b1de30ad23bd9c139d2f0441b849f6a18a658fed30734bd8cfa478b82d7a14',
                                      '5128cc3384cb57f7d0764c7110d77c7ce372abca34daed3eed4ecb2da4e0737a',
                                      '9cd01649b3753efa88a91c59c34152b74e506c4877fbd859add3fdeceeb2bb2e',
                                      'cdf0237a288c8dae650ce6952f654a6a897374c596a3a3b20e46e4f8be1f9f7a',
                                      'fc4d5afb112ed166aee3cfba034513a235dd8629d8594c691b8680a86d91ca21'],
 'Generated/Src/project_mission_parameters.c': ['0a831fbbd42b3ae953ebb50a47a0bcccec687e4c88f8194a61695d2a01366dce',
                                                '3017dd6cdeec985a4b7c2cd7f5894fccd39b3d87e32536fed95d42f443b16137',
                                                '892b9a9af750e88e47d2a528a5dca746c76afab9eeff609a10292565c4f5fc60',
                                                'de8216430150c108b34f64cb21271d18e4ded8e7b54488e181f10bdb9a3b9aa5'],
 'Generated/Src/project_resources.c': ['108d7ddc046f131a1ded3f0599d3e36e85bd9a84575a0fe64bcf2fc7d341567b',
                                       '2c35803416d335e25e4b24da6fe31f3131bea814fa049f2defd99937545527d4',
                                       '47eeef00e89d82a7859f4c781610f3beab03a3cbbb8d03bcedcaeb87140c19e2',
                                       '701b57f80b999092cfff7517df245c55430930feb70fcb8859d9815b653359fc'],
 'Middlewares/Third_Party/FatFs/src/diskio.c': ['426b4cf83404d8251adafd4aecc0ea5281dee2a255d3c9cdea5dd70ffc77aa59',
                                                '6a85341aec8a67ca8a0a9f5da4b48b5de39964fd138bec68a45ba711ef0dd773',
                                                'b0e8169b0162d2a92788e11832782bc8c6220beaac5f377c0c8cd8eb8252dd6f',
                                                'fa540eb5555a425d310bf205e0929de275861167b74cd71b949ddffeca484880'],
 'Middlewares/Third_Party/FatFs/src/ff.c': ['05ce1355a8bc351ff535756bc336c11e2ed3db22d08eb92eb19eb2a82cae7982',
                                            '297e1ea74b1140014caa2e67e2625801a5f5154cd5b3ad5a5e929d8aad246f05',
                                            '8e1083d8598c17aa7f15c83bdb3745c84f3421ae6d80f99b62a2440e682db98d',
                                            'b16d079de9e0aa1383e6d3c67bcd31b334a34b39a8559c9c2468847a86865b24'],
 'Middlewares/Third_Party/FatFs/src/ff_gen_drv.c': ['0d9f685110713946230588a487b4a97de899c67f19ae50a2ffb49cdd5e38f269',
                                                    '4ab92ea676bdaab410d373c5630f07f8e3d99f2ea50dd5899b827eb49c5a026c',
                                                    '9adafd82898742dfe4ed1aedc7d349c4a910e9af9c5ca8f56fdf7a11a18896d6',
                                                    'b3d9f88bebef774dfd03460d9f8d755d54345548df3d5369279d651a2e5b9090'],
 'Middlewares/Third_Party/SX1280lib/sx1280-hal.c': ['6c3f74b1deb06adc0d78953ce119358a8a6a8579f96d4e446b4786d452c91f2a',
                                                    '6fc018b3c2b7031c7455b73f5658b76a484fccb3c9c5b156244ce91fd9bc3633',
                                                    '96d89ae40c734086ee2344296812d0a6b43ac962ca51b2110575798d112983b3',
                                                    '9a4934e4a4aba1bf5f2dd9a985c2a64386fe8ef644bd589cec224a7052652b5d'],
 'Middlewares/Third_Party/SX1280lib/sx1280.c': ['3e2952cfa83ba8b19312c11eb82407430ee000ba1ce42548a294153629f2170c',
                                                '56ce9d58d354dc9fa8fb44a21c89279f8240657f06b7924b84895464ace00fe0',
                                                '96a5afb857adbb3f774d3359af17617d6329f86d7a0deff081939a1029e8228a',
                                                'dc1f970d4492ceada62b9f6e3939526be8892d7e1098039b65b6a3c41ac5311d'],
 'Modules/Src/telemetry_service.c': ['4216370b4f1f833162a48e4221cce9a1a376152d885ddc17d1e1f67805ea82a9',
                                     '87faf2674f4aea0703ea29d7e0a058f063a09059aed85614f41deac6d30595e8',
                                     'dd50a7537ec9050b247bba4d2709b6ae33ddf4c81fbc9185e7cb53826792c5d7',
                                     'f38d838a3a6fb9580c8b6fe6b28edfd5d99dd07fcab74c244d7a0e2ac8945c50',
                                     'fae1f76b558d835db19f388491b25bd5450ea84604099f5aad3a92cdad70eb89'],
 'OS/FreeRTOS/freertos_hooks.c': ['0314774cd6a0f66339eccbc3c410bf050b466b30509bac6fd97605f43bb0c152',
                                  '0f99f752b1caed6da019a3b63da9f2d5c9e4e30e04975f43d069adc2c032295c',
                                  'a1236ab525160e6711df7eb2a6847c0be87a14661616e604fd05703a29585255',
                                  'a68792930dfa8054f6545da397e9866ccb0d3b27e8bf19152d3876e3e56afd5c'],
 'Platform/STM32F4/Src/platform_adc_stm32f4.c': ['3048907063a07818e24ae3e9857ff35d93178cc8a6d517a3ec0b8b90700df82b',
                                                 '4f192e5275c44dc037efcfb70f6c7eeffc35a0fbc7830fc238e11a78f97a22a8',
                                                 '5d81f30163c4e4469ed471ecc9abd51ae0e5143d6ebd3af2135489c9fa5e2136',
                                                 'e6c4f62f5916b1818b31d5092ada5aef718a8832cbfc32c6710a94338ca1343d'],
 'Platform/STM32F4/Src/platform_critical_stm32f4.c': ['2f28c4a938c2bdab40ea87aef7815104b3899a589cd5cbb4ec7b039771853d01',
                                                      '71fc5316300e5607e51f30ca5104cc8e946a09cf7a19bba6ba0ffe857694fa0c',
                                                      'a8feedf0ad8dab3a3c124e2c92e3e22961a1ad7d6174d4e958af457be466c9e6',
                                                      'ee8b35c6bb1654639774efb532adc0deb8c9af554a67927b0754bd3a26bf3695'],
 'Platform/STM32F4/Src/platform_gpio_stm32f4.c': ['29d94ccd4e3dc94e86daae26511803f33ed3cff54aba1f37a3da6747cc8caeeb',
                                                  '76a3252f6d0e4882e8cb3b7b25c01f047633828aca019dce7d5c9259ef6fa43a',
                                                  'd19c7a24873315dc25248e176bb52382359f0f4dda562a89dd7c82811b8767d8',
                                                  'ed5b2ce6ecf3a63c72b1c52860e09cc0483ba473eb537301d2f0d1ba4ab4b449'],
 'Platform/STM32F4/Src/platform_memory_stm32f4.c': ['79a9221888ff1fede869b2f388b7a69a78c14d0b6548ced862c7086728d97c8c',
                                                    '79a9230de7b337d6ffd15eb527302e41e71aee816c9d81184ce72e1f96af51d7',
                                                    '94b71a51ed6d17718f860b34de8668a2e232b34da7d3c8b208196805593e62d6',
                                                    'fc0502bd63158e03d010fc98e1769bffe536c95568f518cf46bdc2213cfee51c'],
 'Platform/STM32F4/Src/platform_spi_stm32f4.c': ['4b5c86fbb42f151a5b99544cd575a12ba44a4b1ece59bc4540e9c9a0500b7c71',
                                                 '60e6248aad8d63ea19ae7d75528d8c9fe5e328816a361ec9808be26902b60862',
                                                 '892222aee2054dd4606d862f1987c88d1d1d219f3e70628aea064458a37db3a1',
                                                 'd7ae7c269d817202ed6b6e2913a89849cf7d38422667a60eba7ea37acc2dafe2'],
 'Platform/STM32F4/Src/platform_time_stm32f4.c': ['19a75eb992a50d88970f54cd8cc39a34e0556cd0c15c45a9fb53a4b71f596a5a',
                                                  '6a9178c7c28138f6a97ed49cd68dac3e2b433b8892c2a618d75690199a931f69',
                                                  'af4fa003a0441736e1fd09441c8c12b29d24f52393b2818a9e1cc09a88fc41b1',
                                                  'd6f6b6718b227dd65bd615b7e2692835180de5800000fe27aa5840cc0b4ec611'],
 'Platform/STM32F4/Src/platform_uart_stm32f4.c': ['076e5fa88eee23e042b5997dbd6b56a2fdff81d86c863e0ca766c4cc6c653902',
                                                  'a0841420a21d68bfbbba83b76a4f49d1e4eaecdcc1e84ca3e092313f2a42bc0c',
                                                  'cdd779ab3a80157fa92191553398456853f3acf3b998862bd0217fe0206b1d0d',
                                                  'd2eedd045ef5de8284c82d60d3df11cb14e90f7c57b00e32eea699221b917809'],
 'Protocol/SSLOG/Src/sslog_protocol.c': ['5199307ccade947bdb972ee888d1f945aaf793d756c8c518189fef9d75152972',
                                         '85603e758b3fca947f2c2be97d0f7fe61ee8fc9d9d31caafc85b4e9888c4202d',
                                         '972d870a3210a04721988a82ff919ffb4757351e29d2c3e1c1bd1514b66e704e',
                                         '99fa961f8725355380543289dc4917681cdcadaf95b79a3bb6b774c61da2c9e3'],
 'Protocol/SSLOG/Src/sslog_records.c': ['6a749163dd275bb39752983acb06b2337cb87fa34a50d11e50e2c94893bc2cf6',
                                        'a343bdb7c96cf2cf2bc35e80ef2425f7667369cd514315924061e9ab22cc4fe0',
                                        'd91de9f33957f2beef83639f9eb0349f650a5dba5ded698634605d730f96ce78',
                                        'f005bee0c5a76e39e5f145db724722fe0db91d92a7336a7d6a013874e20ecc04'],
 'Protocol/Src/air_protocol.c': ['5eb43a1831bf933c0675e4d0d4031db375fb1a37285b2e999ac83c823d4813b1',
                                 '6457485ca0371104545f243df4785eaf339b0a1b10504deb48056fafd7729e29',
                                 'b6463ee4ac743bf34d3b857a5943e00bf8a58feb115b4b13fd109ae7693cdd91',
                                 'e06d9ee8d1bfa7d35756878fb3403ea873441166cf9ef2d894e73c6a9f209f6c'],
 'System/Alignment/Src/system_alignment.c': ['0851764caf3b2d40fce51e380aaa47acf170993f65f25166cb984cf694239422',
                                             '0c9b34514f197744ebbdc360d4fd10f603e4bcc9f72f254b14da69d5264af29e',
                                             '9bc62280db0daee6437e8f2941e19c061e4cf97dbc8ae96fc2e233e3f4d7788f',
                                             'a8d7ccc34da0dd35c5e28e2f4182fa62dcdedabd2a420457b7acd015bd311ee3'],
 'System/Alignment/Src/system_alignment_source.c': ['633e76909364638ff702c505d0972a77466c8dea9c34dacac0cf00004221dc11',
                                                    '6f28313d93a77c2009e3dd2cb09cdda736c440f2e2d6e622f1cabe1b7de867e1',
                                                    '7804242c6da55b9508857b7a0453130b953850b44702750e9202fc3866ac32f4',
                                                    '91a46742c4062994920eb21424c007da14b6a4e1930ad823787332f558b62fd1'],
 'System/Calibration/Src/system_calibration.c': ['274b02d426a35f1a01ffa3508a94b8950b79f67eebdfefe2053ab17e36c2902c',
                                                 '4b99f1c5c539ff77f19502cfc1bb3d8f94d0f4685c6cecd8a38c9354458d398d',
                                                 'c309b4156f5867431df8bea5d40eeed58f299f3121bb7b8967c9757d50e716fe',
                                                 'cf17374533cd4d7a0fe70f0d4474db881080179951e31487b8a0c3a8c9a8690f'],
 'System/Calibration/Src/system_calibration_correction.c': ['5d659ed90d5132660464c539e897fbb0f8db1d0cc7cfb278797fa41e3b46ab2b',
                                                            '65232db7f7d151ffe213857ced44f79494bc1bf9eca812c8ab3e7a4439c62c83',
                                                            '83358d0d2980097101c555c9e8be064f7618503059131711e4f3fab83926801c',
                                                            '94f4736675a9a957bac56cc6a7989aa446567a40443e5c93760a3478a1a29add'],
 'System/Calibration/Src/system_mag_calibration.c': ['580ae77e3bc17b725a122bb89960e8efc5272ff4d44c20023367286b8024a098',
                                                     '5841313c02862ce07edda2be92d38ba56bbc96c0de214835c88b3380104c7c6f',
                                                     '5d5576308b3e129b39e04829b283269ab119c17c17806b31398c462850f69ba2',
                                                     '717b669ef44d019535f2cc89d7ed0c1835878d3a3c90c478a8cce03b5a07fb12',
                                                     '895d88c788564ab64aef62565d0c14dbc0d7adaf44e6c3ac20ff89e59d10e373'],
 'System/Indicator/Src/system_indicator.c': ['2f780a5c98313449138db3b94c47d5a7a9c87e4139c659d98a2c39263377d7fb',
                                             '3e4aeeca6f8d490ae5c0c181c99b1a7c1ccf2a2cd64ed9f2d5e4b1e86c6e60ce',
                                             '555d3d4edf340ef98eebdf52955b6ee1fb36fbc0f78ccd54ac066fd9097abeab',
                                             'cefccde9c47457fa7862957bdc3a9e5cfef76f6d21c3bb9dd4a600715c8b613c'],
 'System/Inertial/Src/system_inertial.c': ['37e83ff7213ceeb142b7141581ed6831d154f7c98cb56535a982686ba98e8216',
                                           '4a4efbebbc20e74b1c86fd7e2ed5d04d0ef08fba350ff13ff650e809f902626d',
                                           '68472643a447c5e26e9fd159a456ad836c69843c382ed15f7050d7605b2fbfd9',
                                           'a3ce29757773c16f6066b25b0f4297d56837e2f7d735526c3877b0e346609eeb'],
 'System/Src/system_barometer.c': ['09129c648cf7d808e45b96083bb4d96db40fbdd2d6ff94f85276c8ce22c5e613',
                                   '3d230ea5b36161b4654d175fdd098b3f9e0cad9d133811466a635b363b15b67f',
                                   'd7cbd54c4349804bd92a3fe212f94b9199da6c18ff2d9bf0d234df9464158b6d',
                                   'eb13a0ba9043c2748b4d893cb9c86e8c011cd426bd29f217e43a09f8bd10d799'],
 'System/Src/system_barometer_cold.c': ['1a64adf7541517b4ba9e7b4f4d00cfcb75dce5bf92e356902bb3c1bd2f1c3963',
                                        '3f3d32f429b17abb5512c8df0af4d12cf5032ee873325d43ad67a67b775e5648',
                                        '9dbf56de66ace9746ca00b685ee791d3eea086a06af64fd8bf5879839399b9dd',
                                        'cb699407eb98efb38aaba9a2a0de123d347a2c42d45abe38a679eb80b0e32f1a',
                                        'f0083a7e7f10ff92372b81f9ca3799b1e2d34105ec5ae08446461173891d4d4c'],
 'System/Src/system_capabilities.c': ['0acbf4c317087f60b5aa367b15140d70ca65ba2721ad060e7b1445ab52b58ad1',
                                      '185380f83e9179b12d6a107c746c81e95e5542425434c759f228103cdf3d1c7d',
                                      '6af44323f0533883c08e784bbdf0d7303e93180057ce5a4c97db78bf0c54aaa1',
                                      'df5ec4cd3cde091a44b15f435b3826dab66ff1d885d44c79ea9a454fac81a9dc'],
 'System/Src/system_console.c': ['1788af08f15e38668a3e1b7601705b734edc0ae78b22348075543ac09d116c92',
                                 '1cdd72b3873ba5db96e069bde1cf0a77acfed97c07f71e9a8ce313185437786d',
                                 '7c2ff7a0b468723e0500d3a61736d32b77d3420c0bfbfe04ffedf8cdac738c7b',
                                 '9a012bec9146d19639e677384ac979adf2518e149cfa95b1defbd4942b49d3b2',
                                 'acd7e905c09a687a237604977d2939c11546076dce74dee52f34ac510a76f0e0'],
 'System/Src/system_device_startup.c': ['05b13776127568086ced76921d2f9200e405efa2c0372c0db972722213e2be66',
                                        '72cd9f153f761e82f3d0aa751353cc824a45f46784acf2c6e31a476e27141244',
                                        'e8c7862e10c31c0d0c779f0187e12b5d5e8baa549adf25f6a312515f675c6f22',
                                        'ef4175c202786ea29639771efa5f0bc31d9e1035c733f2addc444e2d252282c3'],
 'System/Src/system_estimator_diagnostics.c': ['1d3b93b95f70afb3afc50b364e7fbf16b181919039beac2087cf5a5332eafa4c',
                                               '21a78891472195ab3e4b586f876b01252a88cfa00e16b724667b5f19c0fba5d8',
                                               '8af8a33fe5a93fb60e2fbf1f0fce2b67959695c1a36c554efa8870caaaa15930',
                                               'eac372c10814b5f7b36472ae6e4e855b9536550147533189a75a50772dac2db7'],
 'System/Src/system_estimator_profile.c': ['19a248babf27d93db1c0bb2fbb092444d8e7dce9bf0e3c29ebf544395e88034f',
                                           '2f5b1a99ac3ce8718d3317de645a6ee088255feb5da17e72bcf0dbb580254b5a',
                                           '9028cd714b823770eb8d2ec82e96ea9e92e3927cf766e4d9c9f04fef1dafbe59',
                                           'e61c3e7adc453ed3cbdc1a40b274ed16af6ddae557f40e6c8736752eed335c41'],
 'System/Src/system_gnss_quality.c': ['4cf93907e6683f7d62041c16db93e29b27735fe791745dbdc0e149f0647b6544',
                                      '68669e943b75fa89435568a3d68c47bacf4e9259f3b2c3f8c93a4ca663fa80ee',
                                      '9090de01783b886bece573448d375e5485730bd07ca610cd7515db88b272b940',
                                      'b9dd971cde365c818e55bef9e3526537537fd0993ff2c47ee0abd85051bcc296'],
 'System/Src/system_health.c': ['0e040ee9fe648e759287ab80a4a25c597d146a4c0afc2f8adb7d7fa20c1d00bb',
                                '3520efde29e4326b8b770b7a3a92b9281eae67506a821fcaf954054dd379c754',
                                '7c674eee5a282a4948f1103d75c59a1701e36752f8d2ffa58cbe5678d2fa7771',
                                'b42ecd7d9c62256a4a309fcf2b49c2525db4e99d1abdda217a6720814ddfd8c2'],
 'System/Src/system_imu_epoch.c': ['33e4dc700945ba2f2548ac77f4430d15b70f157e752a254089f14d31b3572dd6',
                                   '77fa64bb9ff8591c448d8ef4e82982a80c046541ea767bc80407c1de767bbe9b',
                                   '85380c22608007cd9eff6b8676212584c4cab6e6f1aaf137d64dda2bee2de49f',
                                   'f299eb43005cb48afb7a47ede3873bb6ac6118e27673181be3c674d6fe73c560'],
 'System/Src/system_log_file.c': ['3081eed752a11fc570c7886396516d4fd9700611318612ffda7b1ed260ad9c8c',
                                  '35567ad68e754f12c37a5e10bc5ee55062b264d415b174373c4b9ead98591455',
                                  'a0589f877f419b08526c083691ff74a0b70d23fa0e3ee6a4ed142cd348f8bef5',
                                  'abff85874473b293fcdddec195e92a407c216cbe0f0422cabbd8f84abb17becf'],
 'System/Src/system_log_policy.c': ['3532e407563501f20509ea2d81804c6377008e74ac61cb143fa8f24d31ccb09e',
                                    '45677f8448d645db638d6a9cb29cc1807d212cc3a1b9bb217e37eb501455e578',
                                    '6ad94f63151dd4c05e905107b9f6e78be1ff9008648babced9b7d99dcfb6f8e0',
                                    'c3fe8a560b187174a3a518c2d08e8b31047c04fead87998cdcd8da4b1eeb3562'],
 'System/Src/system_navigation_health.c': ['23aa83eb2973458cdc8986d51996fc941862e5172e25df98898d354e319c8e32',
                                           '369c24d5f0cdeb428bbdaa188fc90f9c631294d225d35dfc6719f95b806222b5',
                                           '5a77d2fae7b22a5fd8ec5cf62df51ced068d682f220c22751bb904822e7dee0b',
                                           '618b354181cd2b059560b1ffbdcc66040d0fc643188a89fbe2e0e49105b4fc9c'],
 'System/Src/system_navigation_profile.c': ['b1e0fb287601da23c5603b5a0e06b0c83147b33f944728221bcc383b86ff93ef',
                                            'd8c9185441305aba78ef09e91f4aacdc661dc048d8b01d185fea04e92583d95f',
                                            'e5f5a48a4c146d09484b6599cddb51abf936699a8cda367114ff00fa45a429cb',
                                            'ec68f68351edb6efa8b6df7eed2078388984821b8bd472c869bb8fab5d32d22c'],
 'System/Src/system_profile.c': ['8e263c0d0458fd76b67a10080ce4bb215b4355ec3aecf418310840dd40a132ce',
                                 '9019eb69987a8c49f53522db664eb55937345975a6847c3cfd0433ba3c23491d',
                                 'f3e06852b6f5676bea1998616c42ac8ed53a0da1dc6a31cdcd8520a9e38c4335',
                                 'f499f30d95ef9078dc61d284c9cea41297dfa788c801e70ee48182305595637d'],
 'System/Src/system_sensor_status.c': ['1767633279100e4dea88aecc28d63cb5de833cb574e10acb34ab6d7039564fc4',
                                       '3f07a64ca04498741ac49472508c215969e67ecaba4f8953c4560aba10e59e7f',
                                       '7db82e427d40ff3d66f6ab76d89e5a8405499c18654dba38ef0b150689409fcc',
                                       'd14d4e810c6a02244c0c15dc5f3d06b6ab46729d3ac6c3d736943cdd72d7a4bc',
                                       'fcecf7fafd39bc4596160bca19dc9a1f997670be67a84e65ec10625c669ac6ad'],
 'System/Src/system_source_selector.c': ['289b791a1f77a41a522f0b92abcacc45162bde466c5a04f31b64968ae6144130',
                                         '3bce6d576ee429ce4dddbf4e10b51f28819154526a769f46786ec2b9ca96b7fc',
                                         '6d602cf12f1a26894c677cc4d3e4e146d7819339bb5918fafb016a0dc2b98c51',
                                         '711cb57815cde7bf84fd92aa6003bfa49ed494318f6df5759bd24e3cc828d7f2',
                                         'a5698475aa080ccf700abfb142b3b39cbef84f2be7f3b1733caaea8e764076a1'],
 'System/Src/system_startup.c': ['73beb9920721edb669ec0d6c7f1cc1803ae657e675cb408c7a9999a483d02f4f',
                                 '7fbc11598f1f4a9b511c9f7f742ad63894357fa1c1bd50b304423a1058378e37',
                                 'fcacaa0ea5f864ae6d64709d309af263445ff79cba87d6f42e90796e650f8aaf',
                                 'fe17d6764550ba12b49d3562a9fe04d323e31df05f44cfb8f144da48408fd033'],
 'System/Src/system_time.c': ['98e228836ebb9845bba502feb758b13081c77b7aca60551eb8b632072a1a458a',
                              'a2bf1304961339a32cf914a2a5a60cbda03d759fd71b8e3a42e00f5b8649ba1d',
                              'bd51c499f2113bc8d2803ad559fd72d9d6f3f8e1c2fb547ea9f3d96bbc849e44',
                              'd8c911779f363cfd047b8cf3e5e42a6951b3a862c815c7c0fbe11aac889df83c'],
 'System/User/system_user_inertial_config.c': ['04ae0af23fb19836e157eaea59dc2b4959d74a363a694a4ec10813fe4125a96f',
                                               '6dd89c024c23ee3299ac3c6c7fbfa2f39e0831072ef0cb00b232f947886722d4',
                                               'ab3ac896cf2e786884ca1fdd520dd03e2ed19cb9074b266a3a7075b27a5d7880',
                                               'edb649ff6e2399536d8af84affc6af73f584de4ff6993b69f3f10934e15c07cd'],
 'Targets/SilverStar_F407/Src/freertos_target_irq.c': ['b02a01080303ee51bb0bcd350649a54146621957b5739465ab151421c1e8e376',
                                                       'cbae18601e8ed0e7fa2a62a660dcc18401ed47875983165127c7359d5e797aa0',
                                                       'f1d6d0dbf65ba2b5a308ecc4b2d05d92a84740d71955a0a028203dc9df9a2b4b',
                                                       'f4b201fa053cff4615f75cda90a97690ce6aceaf81b0e1227a1fb5ce2d0318ca'],
 'ThirdParty/FreeRTOS-Kernel/list.c': ['18601d24e074ed0184ceb75a372bb933daf06eaef8d9103da5ba56e91442ced9',
                                       '76fd003a5dd62100248427560b3a6a742eb1161c3bf69c0899737c9cc5443873',
                                       'bd3310437ef91a1f847d16522f93e1ea99e2c76a2d6cc420577cc77562bd3d41',
                                       'c471ee8d955351b51bea961d143bef0ce56ea874c13bf6d07da9f289bdbe929a'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c': ['935595eb92e6f0660f61cd15b99b646b69402186b815cf05b0cf21c118d11574',
                                                             'b49af3a04dbdaef122ac552b81f47ee9aa197f66aa21c2fdbe674a9e67455812',
                                                             'bb9e575f07da2c0f05cde5feb54b2261e03f6a18deaefc04a7e908a5ab754546',
                                                             'c441982dd9cf4dc9be2a2ba60041a741f78a7569f19bbdb4e0c0ec39c486844f'],
 'ThirdParty/FreeRTOS-Kernel/queue.c': ['320d7f69a4d032348410375fd9cbbea5e8f400bafbff2e96126446d721f66603',
                                        '5c64cf1e8d93a215aaca2be48d3a0b6a3b1d828157deaa0f18006210dbd7ec87',
                                        '72a55a9721508cef82b9698ff633bd8b7f576aec3a8b6a65831b4407a7bd6c29',
                                        '9afe21cd36ee64517d19fde070897fbac9f7a8d3895e9a5ef2858baa02cb5f35'],
 'ThirdParty/FreeRTOS-Kernel/tasks.c': ['3291fd218f79014a61fe7044821c3ad3ecc04165790626a8f1b7086cd8891f72',
                                        '9bfe7b54438fee225a52f7174ceeeb0837c2ca18a618af36fe313df254d679fd',
                                        'b5f8cfce28a34643446bc2f63d69870e3d0d8fdeed922fc4a90fe85fccc6a12a',
                                        'e6251fa6e14edcdcb3df053ff20c18db1fad9939279593185b30b4609e473bf7']}


# Exact reviewed mode2 inputs; see NAVIGATION_HORIZON_STACK_INPUT_REVIEW_20261016.md.
# No callback, library, source-coverage or stack-margin exception is added.
BINDING_SOURCE_HORIZON_V19 = {'APP/Inc/estimator_bus.h': ['ecbdd96dfdcd7138e1ce92e224201aea0691d239cbd094356597e686d85a9239'],
 'APP/Inc/logger_bus.h': ['9952577f50635137a5d8d6ae52a1c0fddee60bfd039092cc16bf001f933579e1'],
 'APP/Src/estimator_bus.c': ['bba108ad306dd9602b2ac95448757ac71544d68d7cd9ea86e3ecca2b88858dd6'],
 'APP/Src/estimator_task.c': ['b79c92a70b02d6f024cc848552b267f89a59da49592c94261d380ded964fbb5f'],
 'APP/Src/logger_bus.c': ['f99eaf4e9ff590a9f0c5cdbfea55aaa575e5b09d71fde6841499a685cf92568a'],
 'Algorithm/Estimator/ESKF15/Inc/navigation_eskf.h': ['62f8330a69150520578dda46067113a52e522a4ab12f22b484dc05742660025d'],
 'Algorithm/Estimator/ESKF15/Inc/navigation_eskf_horizon.h': ['3326f3ce4507ebd7da1a571bcc99e91247423b77b08c0fecb1c755713cdc9e8d'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf.c': ['57d3ec3ff092a9b0f9455aecf52a2dde238b74b23463733450e391763a840c6b'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['bab2c68254fb4095e6a0c8712aaa8ad18e330134edc85af1f5b3ceb114f15c28'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_horizon.c': ['86eee0a4fe3435e9e74e6d05daac1775bba62db806173fb9aa8810ede10e4bea'],
 'Algorithm/Estimator/KF6/Inc/navigation_kf.h': ['4d3d5b93f4439d763199ca4f970c2d7bd436cc09cc3a92842ad291b7cdc5e6ca'],
 'Algorithm/Estimator/KF6/Inc/navigation_kf_horizon.h': ['49a821c7dfaccb2cb00a0a4149a300613f7bd24a9d9c9e343fba8daa87048ca2'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_horizon.c': ['8149defc8808392273fbc228d7627f14b398d2289fc11e2684817e672913bf38'],
 'Generated/Inc/project_algorithm_parameters.h': ['5ccae4a0711c7b73d53cc1f5087477a9d6f446fbe43803611119a5c42d4e2827',
                                                  '8ff6aa5fc7f06f096ba304b705284ca70a5d2c25c1ad4b2f6ce24dfa24713379'],
 'Generated/Inc/project_device_build_capabilities.h': ['69341d89cbfae446b4c605f126e9af4d0915c589c2d91fd83ead47a276f66cc1'],
 'Generated/Inc/project_device_instances.h': ['c0c379439e99c0712a7ac6aac01284797b9e11a7841c48858007c8c359c78e43'],
 'Generated/Inc/project_flight_config.h': ['ec40f9047556612ecc800d71fca189a99749be9441d9b676d4ffc51656656a2d'],
 'Generated/Src/project_capability_routes.c': ['210be6384195ce535339121f4899eeb2e019d24e049599ce4c2b122a3133d1a0',
                                               '81a4df8e6cbc3054b776fb46dcb64fff7d0648c8153908c43e32818c798fbae6'],
 'Generated/Src/project_device_instances.c': ['7f5af8bdcf2d5803b91d40facba49d85e3e61fc99de68293cfa06495eea4fd1e'],
 'Generated/Src/project_log_config.c': ['e61303caf403145eb8fd8f7df7cca74fdf50c68c845439b373d2f631d7df7d33',
                                        'f0564831bbfccd7725e2b3cb104fda3e32d7db829c51e3a4389416182a9e74e8'],
 'Generated/Src/project_log_decoder_profile.c': ['139a27723de59b5ca4f13148ae72b2442f0ccc990b830430a831cc6f0af1f040',
                                                 '5c8f6ed55a3e7d8712ac6b8ed8d965b0e37ce769cf72b7751fe3d0ba189ab925'],
 'Generated/Src/project_metadata.c': ['056773414ff24cdf08c2b0f9406c5a60cab479ebde186292da070219fbf1e402',
                                      '1381ae8fb70328fe855b1e924a2e20d4425ac7bc1aed157983b8f82eb74b26b0'],
 'Generated/Src/project_mission_parameters.c': ['310a448eba7192684685da57048ff20e76e1382a782b352fe116f7e44c28ba68',
                                                'ffffed88dddb40f2e36d5095fb90199525eec4f5e69738eb533c94822bc23133'],
 'Generated/Src/project_resources.c': ['bc9f692d2a78c78e66d17348d044f221e0338f40abd627bcca8fe4a42a768224'],
 'Protocol/SSLOG/Inc/sslog_protocol.h': ['c3591ea3e416b69041ad0ff00b96816ae5be35b731d9ceed2cc336bfc501000e'],
 'Protocol/SSLOG/Inc/sslog_records.h': ['f0d2a86be076e4a9c7096fcc7110b95e35f4e3dadd062b51f7dbfde5e045640e'],
 'Protocol/SSLOG/Src/sslog_protocol.c': ['db9d4619d6fb5ac1b3c06d06931a5252c2026e1e0310e0ba6326bcef604c30f2'],
 'Protocol/SSLOG/Src/sslog_records.c': ['3bae566234f4650d2b86ac513d8b45f3a70fa99eead67e0b3e4394d6a29ec508'],
 'System/Inc/system_fusion_timing.h': ['e5db6c2056f9b289a3bf8c32959b345146087ba249a09aa6711cca6e772d96ef'],
 'System/Inc/system_navigation_health.h': ['668f01a4fcc984d4dfcef8559491a28aa3f1093fe1d1454b78a17dff20b57bce'],
 'System/Src/system_navigation_health.c': ['cea3cc4bbe7f63f69a557e13bddebffab876c5f22efe44f6783c23b814d8a75d']}

BINDING_DEPENDENCIES_HORIZON_V19 = {'APP/Src/estimator_task.c': ['510a3d15f6afb8196273248b515254e01a965fc13895695c4cb8eb1098bfe752',
                              '8c2e87a8c46383b5bd8f257933b5180d625399bd41154ac2bd724a0333632247'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['6fd28677c25a84a97d0bb093510d5dafd755bcd7e42c9252f0fa571f493916a6'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_horizon.c': ['2037f780052a4f66cd2a51330e77af2c9866337d52a655e442d468f976a8c6a0'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_horizon.c': ['65f211ea13e27e03a3292123b618dd34298a2dd76899ace1ad26159a22540d40']}

BINDING_COMPILED_INPUTS_HORIZON_V19 = {'APP/Src/app_tasks.c': ['d598a92dc3452c93384c17ed8cd2e39462ba226e813558891ae8282c1dd30185',
                         'ddbe99043592fcc95d75c85961efb8806dec714a94ef178e18e2c0d0ec3d4163'],
 'APP/Src/device_native_log.c': ['18155fbd1ad6b56dab9dba201ef41946d4a0da9279e99331ff0667e337125eda',
                                 '30eb0a951140498da24209ec4171febb39ca4909d014a1a51c1bda7e2e3d8e5a'],
 'APP/Src/device_task.c': ['a9a263db9f542ff99d41a755c9b5a6f7a04dbac4c808abaaf6c1126ae3915ea4',
                           'e8631b1744e5ba49a00440d9413808d8b2911535a9418019708e71c7e9385dfa'],
 'APP/Src/diagnostic_log.c': ['2bab643fc9009d0b464f93b46afb0c51cdeaa54d76d5ecf5ca4c70cb42da27ca',
                              'c5afed2dd5e708e3a131ee4649e086a6fed77f5efcabf8b17c3e8f3bb5fb4b4a'],
 'APP/Src/estimator_barometer_pending.c': ['301bad9416748d48b49732846a70fe13aa5e96b13187b91161a0637a9f2fe830',
                                           '788422f87d5a54131eaa98961cce403521a98611cdafd06096c6a7423d0965dc'],
 'APP/Src/estimator_bus.c': ['7d2c9fc6c84a565fedb91c67068a4f427b3cf00f4eb4c42c2f96a61098e8b30c',
                             '84376bde173d9f2763dc61633ff3ab97d6d2531e500c7a941dd7a3c4586d7dba'],
 'APP/Src/estimator_task.c': ['6c13a39e099c0fb7082dce704958f24677303c4a7f58a30c06f34222e2688fd0',
                              '85490f5aeb725c330fc20a6e7d130c3f084a50490feedcbe22440fee3134af26'],
 'APP/Src/flight_task.c': ['69289da47a47787b9cffda710cd3b3fe647bff3fc40154286f8be588dd291cbb',
                           '766d614234e7922eb5c89fcfd4e5cdc5f21fa5caa9b187d95f78af4056f27e97'],
 'APP/Src/imu_sample_bus.c': ['3535553267dff0ec9ffc6cad23d8817bb5e550da52b78b05ff7beadc7c3ec976',
                              '89ad43f3ea9206b2a7c5779ebbf3aae895e4b61f01f2544a5efa895b301f6886'],
 'APP/Src/ins_task.c': ['87e42e5fd58b20d91c57a5fb045196af644570c98a7a305b6a4c300f972f9d4f',
                        'fc5502c7ad8eb5ee9f3034faf0f850c10cf0017a62035dda11440b795931f782'],
 'APP/Src/logger_bus.c': ['346ba68a4a1671066b3388030b3685c9050d8a4a0b0663d2a989b1683b27c88a',
                          'fda5951702f535c34095f4d10569f3fee4507daef1421ba715f7d23b8c6b4856'],
 'APP/Src/logger_task.c': ['c4d632254007fdc93101b8352fd30a9665380d78d2bcc760ce6a3cc956d90d73',
                           'ddd73546cf925cbef30c60f5988647e445531742f008b4c9b2e7d29d6098d995'],
 'APP/Src/serial_task.c': ['d0a84b2c72c88d50faa229fdfab940c138ad38587f02e0a1c8c16c64fb0fa2b5',
                           'f01d807fe9e7e107ce974d479ad3c164a0c11731f694d2022a3d94fa0aaaef67'],
 'APP/Src/telemetry_task.c': ['196693337ffb7738ac84ae3e769768cc93136a2042313bc45372f7550160aa44',
                              '677cc87b5f8ac38777d3e8c8d9917fe80106ebef85964690624a21126cca5aed'],
 'Algorithm/Alignment/Common/Src/attitude_alignment.c': ['388dd2f17dfcebf72fde5ddad209dddcf950c68a0714bd081192a43ab6927910',
                                                         'cede3264d2e72922593893d7aa830e61843acc79892e1b47b40823979c608f9a'],
 'Algorithm/Alignment/Common/Src/attitude_preflight.c': ['d1c2e47497f8a40b23b642c9085f8e9a3595f8cf61d1456a72643106ca4fea7e',
                                                         'fb479cf9c487679c1812105bf529b7f1319d4894b3f25322601730f05575c7c7'],
 'Algorithm/Alignment/Common/Src/vector_constraints.c': ['893aa6aceef4ef92694eda321f8256057bbc92987559b42a5bf96827043a6d56',
                                                         'c993a6e55ff77eef0a5e4494ae5f9e2e238188210eb147df3d4310ee08c39b0b'],
 'Algorithm/Alignment/VectorConstraints/Src/alignment_strategy_binding.c': ['6c120e6651e8d8234da14993ca680329bd4c79a31297d6cc2869e198134ee7b6',
                                                                            'c932fc700e59f1cc6ca6938102c712a879f9080fc41c3af76ef2eb47a37843bf'],
 'Algorithm/Calibration/Src/imu_six_face_calibration.c': ['dd6f02f64c53c5ad45333cf6b99bc36726c71b6dde8cdad89a6717f0439b24f7',
                                                          'f695cf214273a38cf2ce2c22d52d8dc9477694de31e7429bef17e9ceddfea6d2'],
 'Algorithm/Common/Src/attitude_frame.c': ['7941bff61149dbc4ce0f3dbe567b829f9706e33efc1abde47dee2b6912d9c7ad',
                                           'ea02d9ad02eea5c2734c2a8ce598e264b6adc3361743fcdf6b9f71cd9142117d'],
 'Algorithm/Common/Src/geodesy_local.c': ['6442b7dc658d605e298a6c2d3feb63c5f97a03871cd09030bc5f903efd98395b',
                                          'd0d354d86925c80c26d6c796e875fc6041bfd6d8eb2146a7af7037d3b9a477eb'],
 'Algorithm/Common/Src/navigation_quality.c': ['a4d45c19c5e7b152fcac201d77d977127e31bbf9460303eb5f0dd6bc8d1f79df',
                                               'f237cc5b137afb23859eff5870fa7aaa19b296a8fb83b38ba1e4912834fb29b1'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf.c': ['c92f1cf130da5fbd4ed6299a42b5ccb4dedd567de50909d9410955e1db20d25a'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c': ['a1e8a8942dc05d793f2353081e63018b872a7abfa9a1658f1807fe420b617307'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_horizon.c': ['140b07da63e264fef2c550d5f9460dfbe8809847a54f02788013512c88e594c8'],
 'Algorithm/Estimator/ESKF15/Src/navigation_eskf_replay.c': ['1daf003db60062b0bbc819e3a58579e6513af05725ae9ae3f597d4d4f5ceb034'],
 'Algorithm/Estimator/KF6/Src/navigation_integrity.c': ['89fe2de980153929ee2f675bb2b9e76d35988fac7b94fae8baac8ba495535a69'],
 'Algorithm/Estimator/KF6/Src/navigation_kf.c': ['1f565291e528b8e7fbcf1c81f30ac3d2c218456cd48b2d286e31fbd9dc231e1a'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_horizon.c': ['7aac57ec3409934e3c309136971e05d9084053a1d75317e161ee0c9dadb84c58'],
 'Algorithm/Estimator/KF6/Src/navigation_kf_replay.c': ['0551be983ce5d904b4c8cc7968b3e2f2693a856c1328fbe535dfc2c3136fdd9a'],
 'Algorithm/INS/Coning2Sculling2/Src/ins_mechanization.c': ['4478bc98679cd4d42f3babb8ee05811bbc4af10bf9c9a3487bebad7e109a47c8',
                                                            'b6a7c7357911a54a9a60d91f9b2c8e3a6843aa4bead8c8f528815a890ee5cfc8'],
 'Common/Src/common_format.c': ['0a029e0652ddba099fcdf9d700a47a2eadbbcdea98277c0a2efa08f470385e75',
                                '46e745a65baefaeefe1d5e22ff88ecf96358d44d88574e97cf9adde2d1ba1491'],
 'Common/Src/common_ringbuf.c': ['1b2d5b9bc3f6b899bc9e9d09941b8336f0fd32f5c4605660167e03aa7eddb585',
                                 '298739e52ba18207c4ea1eac8b1dd19f0497b9a6b138998557fe94bd5f80fe65'],
 'Common/Src/common_spsc_queue.c': ['befda23f3bd6f00046bb4c5fabce09dd787094bc64f4fb4744cd7a722f9035f8',
                                    'ce0be297985571472d805eb8d43ffdbfcf9549cdd7ffc025f4ec24018f12675a'],
 'Common/Src/debug_log.c': ['d39107913c42afc251f79e584acbe9c4b1c9fb866d48c83692874032cf68b818',
                            'd69523a53993dcc1e45a51507ab9ab87b79737d08255a3d6407723c4f4c21b23'],
 'Common/Src/silverstar_assert.c': ['0d1ebc9cb45b5f591ff0046320d84193eec4c41db4101a79120dc8ee8a922a26',
                                    'cc3e467b8a0c58b353f5103e6c28079016785bf556f2e2b65496d2cb0bf5dfd6'],
 'Core/Src/adc.c': ['02349519d9307e0a0f6fd289afc60240de62eb69bfc551968ca0b48c3fa3a811',
                    '5d0c0ac2eb3967619317a17fa4da9678f579c696d1b0b8f4eaa7e3ef7acc1228'],
 'Core/Src/dma.c': ['4c076f4392fbf24511991bc5acc9d6a05721386fcf12a631aa916c537a21d0aa',
                    'e69a48ccc022b53bc6d0a649193cb514b81b4ea6e2964f7c80d7729f5f68870a'],
 'Core/Src/gpio.c': ['05ea73b201920e9ffcd6463a68ba8aa784bcea721eb54fde5a2ea77b7db676b4',
                     'bd5bf5cf01bc180dfab93668bd4b948fcba5a52e2ce39dc9f6be5556625f6021'],
 'Core/Src/main.c': ['1e4e576cf3f41ffd1a6b51afee321651b448efde2df41d23ee81110bdc187678',
                     '8f227cc7f0dc8cc58a5ac8e6ca390a67cceb930fde80338f52df041d863a5223'],
 'Core/Src/sdio.c': ['97d0b6132731e2d22316df6a651fe1958dd9de72e47f990f1a436eaf45135b6d',
                     'b608de372cde47e994cf0007283cfc7f46fa044782f48b21ce620bc44e86fbbe'],
 'Core/Src/spi.c': ['06da6fe45fdd4d5f003dbe7b21df4bc124b3350907328e3243ae35a80c1611d6',
                    '8e258453abb0339f5d39a277e114d86ca274458f8f6e6354c6d8d69ab95cee7a'],
 'Core/Src/stm32f4xx_hal_msp.c': ['1e7cc74bad33e202d9fe8a5afb2e408003109dc8db2bdf5e1987ddd46e98df4c',
                                  '60da3b04d0e9497a0026ae0ccd3cf8fc71dd2cd54866b75cce7a54159e2870fc'],
 'Core/Src/stm32f4xx_hal_timebase_tim.c': ['0c2df6777dedb72d75a775ab67327213c1e68ec122b1a4a084cfba7794d88989',
                                           'bd7dbe07a21eae8bbe4dfcfe918faf8ef254332673206acada624e25d655240a'],
 'Core/Src/stm32f4xx_it.c': ['71f4d6d88f0dbc3782619dd73a7c643a40e7fa0ccea937003d836dd1e8dd48fd',
                             'd9a599b8535c240b869d157b80f63a57bcb54586b01546bed1c3c6633c7cbaeb'],
 'Core/Src/syscalls.c': ['77bc8221b2462dece66d1167e478c8a8e9250a51ed647ad6f1dc1530c80a080c',
                         'c5327c01c974ae901a7b3d008a2fc8c496f6e6a3c5ed005ac46d930c0a1e6ce0'],
 'Core/Src/system_stm32f4xx.c': ['3b2004272201d4abb079d056ecfc3d4e9d5bf3c8718c1b40f5ef793c68e0eee2',
                                 '3cad1c63335d68c10d6dd53fa3a77ecca07dfbbbae3f5592cc9d63a669dd7678'],
 'Core/Src/usart.c': ['336b5d81936d024a3893160307d8904732b13a8b80106f7b6a14776f6d358d16',
                      '4ac1324ad61e2a804cbe632aff4c527326f664c77f6c4975fc9a4aca90631f75'],
 'Devices/Console/UART/Adapter/Src/uart_console_adapter.c': ['28db135deff19c834d327ab00d381be5dc9180b2f52135f1deceb3d950eb6fdf',
                                                             'e5b3916881aad4ce0f301bccbcbdc2879cfdb5f6b4ca054b123ae7c6a15b709a'],
 'Devices/Console/UART/Src/console_uart_device.c': ['78749d668c459f353d35d9d78232f242a928e06fcb93804505b3b4eee5b71c94',
                                                    '9b60a68b01b0d0471bfd633315011478e6c19709122f622b6fcaf1bb95cb4443'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_startup.c': ['20af13272d6fc2fcc80e147e68bff7fa14ea008047740b3d53734f5d43e6a7d0',
                                                        '65e322772d004ca3031b387110dbe485552cd48ac9e3296ef822761fa81ca169'],
 'Devices/GNSS/NEO_M9N/Adapter/Src/neo_m9n_system_adapter.c': ['ba00df0770a6884890781a4993ca0a91704a67f9baecf4053f7f85b8dde88031',
                                                               'c7dd904fbada8a096f114b541c93cd06d130c35f8fcd2ae8e66737faca997f3e'],
 'Devices/GNSS/NEO_M9N/Src/neo_m9n_device.c': ['0530ced40396d2da6d5187c9fffd7f9cc0b323004618d90b0e10625a43cd4aba',
                                               '5adecb8773b5be53a2644c5daccd820bdf1e56579b761dfeaafb808ec2082069'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_imu_adapter.c': ['15aa52e0c29636ab1fdc7af1805bf5c621769742d8fe6d00ea4d77298e60aa10',
                                                         '56c8c4fe3f083419f3ef16f8a1d27fe4bf5498a8b6104ceb39ad5ea0e24f8570'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_magnetometer_adapter.c': ['78d4040868f31bae9b4c82b93187816e97fe7fea4983655f1565b75f5509d92a',
                                                                  '84b80837420f6e82db75c195161ed28f1bb241fcd3e71ceda902c176ccd1ba66'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_quaternion_adapter.c': ['7397582a204835ec0754c3dc323d222c52e073a118c24f88820720d58d5eeaba',
                                                                '74162c73bfbd7418a4a2336907d166ee0c4173109b463b6357d81bd76285992e'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_sample_quality.c': ['01a4cfc02045f36590b6d17d82ecfa5fb6f4fe8bbaa0cc240077f83f8a6e2a5a',
                                                            'd2e420887641d75a588672766ec315d6bc6ff1dc1d997dbe03c8670703b3cf7e'],
 'Devices/IMU/JY901B/Adapter/Src/jy901b_startup.c': ['4b617197106f9d69e16d38eee85836d41bf93f0748efa5c41c43589fc21493c8',
                                                     '6290ea7157c94df1268faa9412fe24dbf9cd1fdd7d036612a7fea40e72632b5e'],
 'Devices/IMU/JY901B/Src/jy901b_device.c': ['03d86892b96c8d541bfaa7410cbe65d98f463c5afaf0039c6c67c126edd1bc1d',
                                            'c4f2898363df66b42cb5ee9fa417bd2bac09c70ea6a186c2a997d56ebd75b091'],
 'Devices/Power/InputVoltage/Adapter/Src/power_service.c': ['7157d4487f4e807b884388d98195cfcf28be299da05d46f57a5c9a4281adb9a3',
                                                            'f85c0ff1e59ac5e7ddf06f247b3bf897cd2be0703643a4eeb401944436769292'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_file_storage.c': ['2f7ba4879acfcd855b549d25d26636669802426f5daf2d0372a5011a67f8dda5',
                                                                'b3f0a2f73e45f91a8c99ddfa913c297fa3edf86514b1d0af8a6cc4cc0c654dc1'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/log_sink_service.c': ['4b70fa4f8d287e5f7ebbfcf5c906bd15f3990e9a5edd704456e38179fab0b189',
                                                                'ca8903838dff1b95f846a8564e50a0c15f1b32f5a36716a343161e848ea9de49'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mag_calibration_storage.c': ['a6383cc196c08014f18353f9123b923f12425e5c2306327f3e5ea3cfc177f61c',
                                                                       'fbe136996011400e0884f6ec8768d690ad2d3a25442e452a6f661f26ae304129'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/mission_snapshot.c': ['4586cfa696a6007d4373ea4d269f063b2f7d35d2d69976d4d5a7e3a44f25cf07',
                                                                'abde9ea5c595e1c02436617821b7fc577d86e7846b4e50bb630b86bf96e12422'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/persistent_storage.c': ['152f5f715c86a1fb1d1ebae60e2e2b850bd826a8b0bd2fa0d78e165b0626fa77',
                                                                  'cb672b63efa7b53bb66ddc894106b7e514dc1d21689b6996b37c0ae4daabe1dc'],
 'Devices/Storage/SdSdioFatFs/Adapter/Src/storage_service.c': ['9f5598b785e546a1b9696ca147c13881d62ee51b68abfb6b182630c9777ff660',
                                                               'd452233acc9ab1f4cea55983d5e727b82d1276c24afc873d50be31a2d9e1cd54'],
 'Devices/Storage/SdSdioFatFs/Src/fatfs_lfn_ascii.c': ['024393ce0b7d2e73632a1ec08c2f09a4e6b63e0a1e4f98d00e24590d3c34ee86',
                                                       '236c58fe1bb870fad75836cbb22a1ca621804284ae94d803b6f6dd291d0138b1'],
 'Devices/Storage/SdSdioFatFs/Src/mission_radio_profile.c': ['bedd611a2b69ffc4928172b25b37ee11f4cfe94551240d05e08e11af165ab95c',
                                                             'd0d28523df8b5f45efab0f2123f747bcb74e38bbae1500d7df0883db124c2cd6'],
 'Devices/Telemetry/SX1281/Adapter/Src/sx1281_telemetry_adapter.c': ['1ebec84ee4c449a19bc16ae6a1963cb70d355ea42e7d49b88116a7b2d92205a1',
                                                                     'a2b1815658bdd5cf7f536bec41c990d235bbd4132b456cdcd6014f4159f8d44a'],
 'Devices/Telemetry/SX1281/Src/sx1281_bus.c': ['893b6b262780025d0ab7f3dddba7add39a0739707348df4a2c795c01dadfa2c5',
                                               'b2fd66a1b87e6c30d59f84a657c00b520b5d8c8482e50f829a71f003bfa898bd'],
 'Devices/Telemetry/SX1281/Src/sx1281_device.c': ['62646c287bb5a79b6f28284433afb55216e3afcbd07cb802cc8f189bb3d4929d',
                                                  'e504b1350e9eebbd2658dbbb9c7577af268aca6ed08539f5f398fe87a785463f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c': ['13fee68a5c57923e78b19e2251417aad4f7def9f35d377a3dfd6b7190984e741',
                                                      '2067892db28473e7c1c2c8fa2b3ea517986a8ae4bcf870fe9fab50cf5fe2e2c0'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc.c': ['af045dfe7424c5343bcb5a6aae5fdf90fe3ee4fcba7ac8aefa485028666316a3',
                                                          'ea99747353a32d71b06256e4ab67b5fc8bf4b9604561ff96796db4bb562e26f1'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_adc_ex.c': ['793d8eceed02ea01e54eda9475879cfa8e688dfd672269ab9c6a6d1690499ed6',
                                                             'c900f90d33c64b18615947c03d34818f353f419ecc4d68e441b173d402e07161'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_cortex.c': ['14ad503fb501c17fd5afa9f420fe9e164bcd9ca7a129e8bd6eb7c3d0734b8cb7',
                                                             'f9a70061fb0d63e46f9c1c6bd7bcfeffc3d960a6e29c13743f0224891f806e67'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma.c': ['381c34b396d9f84189d91fb465fdef212351913931513cb07a6a605c44afff72',
                                                          '9897bda5503e969451f94bbb649319a8c240b486f2bb9f0fd46af6981105cbbf'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_dma_ex.c': ['70696bb54901187b990bc981c5210d7d3bb061355f14e9ce15417802ebf841f8',
                                                             'db2c6377ec09b767c5af7f3366aed0877f8e309d774ccb4858cb35eb01e79374'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_exti.c': ['c8d01a5c5252eff30a2c06e3dc500e53e68d489d3216f643b8be5d9f26214319',
                                                           'fce45123a05c71e338698dc85d178df3a4a43d4967d3eae4c393c6d49510aad0'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash.c': ['081370b7b7c16d2ba3e891dec11547ba9fc06eec57be610766c6477614b54057',
                                                            '534958176b6bfaaf39595db496914f3849c8992c95598b5408342ae39e65ff5c'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ex.c': ['45c8681689e4d1301ef36a9be4e773170743ad4675e0b7e019127c6567dbd86a',
                                                               'f12f2bb6f6f5a31511a0e945ea5b03775595d623828ec8a8f443626192496b4c'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_flash_ramfunc.c': ['79a67b612cd1ae7a0dc01f213182c3696583dc50feb334f7aa59777261977738',
                                                                    'cba02afa83418fad0712178321c52316bbf525e62d3a133f8db84a0d05f42eae'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c': ['a2430e8c05e5758170739e4b8cc0f958eae942393de8ef8ef5d2392095242dcf',
                                                           'd33c155ad8fd984154ad7369035b2e04943cc1acc7cb0b15b0fe2cb5f718cc18'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr.c': ['06cc6888c617339854bd20f4820df396b6a1e8abc1a39d6b06dd14ab26ff48c3',
                                                          'c1d74d4be8b8dccccc1028662cca33cbc4eb835c91b8f0cd5f6084ddc704b6c7'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_pwr_ex.c': ['26cfbb560e5d3afaf4efe93cb2daf922ddf1ab9d58ae6161f9e3157d24053417',
                                                             'ade7ab94b5516cb8d7799dd47ad8df416dc5fee9a1fd1cd344e1fed32c46d7c1'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c': ['180fe4e9602ce53776e6d0c79981ed2fbd58699aec7f25ccafe3eabb922d5b0b',
                                                          'a5086d02bc5f5a5a16122821d69398eecc697f2353b73ef03fdc392c8d9f0357'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc_ex.c': ['65d4ef8ffb81f46f6a54cd3bd6a86c06389b9fc80ddc95ef33a51cb3ac1c5bde',
                                                             'c7ac7d42e08b57e2ed4f06e44831f4e454d23e7d8dba2287baf1cd70c1d4cac3'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_sd.c': ['12682b698dfd2b30649396fc6363a981d862d217561f1ec1f5d232e687ead852',
                                                         'b2b53292487b51c10dc728e36cbfb83cbb4bbaf6f33156ab0572347e0a73138b'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_spi.c': ['5de4fe2c329cc31ff9ed36ff7c02fc58ed56bbbb98bb651f0f4e47d7c68d089b',
                                                          'f91f9c0f04371208b6c7298766e2b2020e12debdb52c878e7dcf641eb347b9e6'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim.c': ['02cefbeb82a0b0a5f413af0cc13f7dfe191faf79e913149e0e13703d7a6e4c81',
                                                          '3d0541bc5e24d78c5639c10c0f0edf149c7c9cef40b005a9761da6f5a36b4d5f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_tim_ex.c': ['51ac8a963fdcf8ebc592afd6e8803ce88445982d0c618df21ec0c7bb2d1b43e5',
                                                             '7be558aae516703b9cc0ab2895a4fc241c4f90f84f00265856beb6eed835a7f5'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c': ['863e84e1c16e860fbb7918b7ea414db412d28e15d410f67e9ee1e2488873da8b',
                                                           '9eb02addff1cf5f05719e0b63b6a7a5be9c5b2792841765bd780dfdf4417eb4f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_adc.c': ['37d22c132c0fa1263dc508e8defad74ca0c4e0d799e08f29f03faf7315b4cf97',
                                                         '44b755a92f0cfabe6553a9d748dd46f74a6f50ef74a8ea6998db2ef4e5ff427f'],
 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_ll_sdmmc.c': ['c01fee771113f345f8e9f79976832cb67f5c5badfe2b87d0e1d1b152b9e06e94',
                                                           'f5178e6611758817e7bb79ec4c2bd9c8befd7927346655a19c5b12efb4609b78'],
 'FATFS/App/fatfs.c': ['6ecb3b74e5ccb18b62185939f3d815483fd297f321d313f651b7cb0c82973e57',
                       '7f5e8d876d02548e1ab7e9a68b7745b5d8feaba276fa70b57e5e291bddade5bd'],
 'FATFS/Target/bsp_driver_sd.c': ['1ddeee322233af7d199901438ede3e3de97b9cfff2e900bcfcbf1707521fbccc',
                                  '8a1a6bf569b5b5c137aaa95b468e4fea8859e6a5515ee4f2392895ad8b91dc03'],
 'FATFS/Target/fatfs_platform.c': ['84d61acd2e1890346e293ea79a026186b4a5e23472f98eae3c62a2ccd8db7b66',
                                   '9ce548e95337967d5c20246b4264adfc2b0319fb33ea21f500996a68e11cf154'],
 'FATFS/Target/sd_diskio.c': ['45de110a4fc1303c599448c87d3888f95f25fd3910bcf234a8beee1b552a1710',
                              'f53f726b4648843d1ccb71c1c70c692fac9c281b41ecf7de85e28f22e943a33d'],
 'FlightLogic/Deployment/MultiTrigger/Src/flight_deployment.c': ['3572d5c6bdfeefb073b7c87f37c410d0f142609288433961311f40adddec7b04',
                                                                 '4be75e7656f8033ce058b1321472e5175c630d05b6980cb25154b2057f186ed1'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_cycle.c': ['27b9514e73e14d34bb511df2fe62b484cb009e45430cffba6fbf42d9c6d1a372',
                                                           '2e654900ecb7a4d9fac47814e6b420e42bdb2a24899eeabd07e5e017836f496d'],
 'FlightLogic/FlightCycle/Src/silverstar_flight_recovery.c': ['2df53125d5dd7f0a6142cdd88db9e78940ed42090f6212c103998d273a923c81',
                                                              '82636cee50698d0702b0552d13d6f30d940909d551cc31e6c392662532561bcd'],
 'FlightLogic/Indicator/GpioStatus/Src/indicator_service.c': ['370bc11d9598f03a22eac852f86fe1b60e279caba74d19d17b2eb4e94d832515',
                                                              'e826ef49683aeaa45aa9d9ac2e39e1b360ed895d661b150eb665916980dbdf2e'],
 'FlightLogic/Landing/BarometerImuWindow/Src/flight_landing.c': ['c9533c82871ca1943eec6076d82e3aa38cb3426ff5b73c7dbb3e4b4979d04ed5',
                                                                 'ca2741e94b7083264e505867541895a6f786314f7b3980e64be0e73f38305539'],
 'FlightLogic/MissionAction/GpioOutput/Src/mission_action_service.c': ['058920d61f49d9e4ec992f1664f6cc752440eb98108baaf993e99ca44f85747d',
                                                                       '86831873754be7c08279880fb92d8036e361818990fc774f782b9878d0d4ef1f'],
 'FlightLogic/MissionAction/GpioOutput/Src/output_service.c': ['a7e99458709607a95f24af8a1e8fd196b06a2eab42467012d35063e014a0cbd9',
                                                               'dd7705f7607f23e19c8ab0b79bb63278b2aa6f5bcb321b616a75129aeb11dbc5'],
 'Generated/Src/platform_resources.c': ['475034a14ea9e8c9deef64ad817c97449173f8ef52751f0dbcbef88d32d24806',
                                        '5112a581a3ebfad5b6c511147d42148b6ac6e64f73d0b1e8f78e711354150b7b'],
 'Generated/Src/project_capability_routes.c': ['b415c586a2a2547f9b47c89436e4daa8a6e8127d36d6a29f4063400eb558fb09',
                                               'ffd2a97d0081287bbf0aebc6555d1483ea64deecbb633d15ee717fc60b2885c8'],
 'Generated/Src/project_device_instances.c': ['0aee4cbe0be1178be036bf7936c047e28dfe5ef03c4aa7f6d56a35273e25add0',
                                              '98faf23cc77027805da88684bd0ab8c6a2580438f9ec490bf83c959596af90dc'],
 'Generated/Src/project_log_config.c': ['865518dc18b55e5ad1ba4787a3ee1d8233e053a72de6007e417f6cbe899d8e9a',
                                        '8f5698e83179b688ca8c6cc96a34a519b6e4469d607c07b57c9aa5f87e65552b'],
 'Generated/Src/project_log_decoder_profile.c': ['b9a4f60c3d790928aaf16efdd93dccb9d81ee7227af3c47345850dd557a60d2a',
                                                 'd3c88a649a290ccb1f0e983436e8de324eaec16ccb4637e54931aa132a3e328c'],
 'Generated/Src/project_metadata.c': ['522090b2af13a8db9a37d29e4719233f1b74767cc0cd0c3aa75d22490edfbcff',
                                      'e26e9abf8ac8bba02e7f752cb2cdeec78762fd6cb155c83f32017239fc7664a5'],
 'Generated/Src/project_mission_parameters.c': ['ce5c5647b3d0df34cd02a0ca472cdaa021c52d218f715a05dc9f1bfc34198570',
                                                'd4627e761c989b694b997fe7fc4f5d77e9467d4a03373fc6cbf4c473e431d368'],
 'Generated/Src/project_resources.c': ['6bb8fed51510054e97e0a5afce0d24568c80c72e943480d8676bdd0e166df117',
                                       'e18deb0a6310103cbbaf5cba358217f765dc501e5fd4a22975fb23b9811c1ff5'],
 'Middlewares/Third_Party/FatFs/src/diskio.c': ['1fb33845a6cb716d7b9c04523f18367b6e29da3d3374e87922f12c9e719b9e2f',
                                                '98cdcc139e65923c36612426f6654a3fbefa53355aaf4f10459bf5a1fde80ca3'],
 'Middlewares/Third_Party/FatFs/src/ff.c': ['6c479ef0854cfc4ef91644dffb22e8ec1a89ff8affa9415dd1020d9a42ddcebf',
                                            'ed109136e81612bdf4ddec33e27c08091e592233fc5c25c794f91d0fb01163f5'],
 'Middlewares/Third_Party/FatFs/src/ff_gen_drv.c': ['6a8f8feb4663f01dd6b3f8ce559b8a32b7c4ed4f39dc4c7cb9dddee3e5b8329b',
                                                    'ae5743126177bce2cd7da3b61082d61616cb3b1779f6e91cb09b847171bfb1fc'],
 'Middlewares/Third_Party/SX1280lib/sx1280-hal.c': ['9a46fbab0fd179ebf9f1b3a6a254640b7408f812380473741910b8a2003eeb90',
                                                    'd2b5134c873ae8d3a507e919ee7aa5709a6f9b48454852f104b491d099d5b761'],
 'Middlewares/Third_Party/SX1280lib/sx1280.c': ['62ec23404d9ac7c18a8cd06090969ec38aac905d6acbc7393e3b9017310fe73e',
                                                'eed0522c6b8ebc829ecb46973b7bf53091c61533929c5ede3e821f18f165fc25'],
 'Modules/Src/telemetry_service.c': ['184c30756c670508540cbb92ffdcc2a47a174c45fed71d8938ed572b357958fe',
                                     'ef5d9780faa261a857c770c97c31b7ab5875ac30584bf6d27aa93a0c35760588'],
 'OS/FreeRTOS/freertos_hooks.c': ['52f8268dd504fb191992a33e92acd23c4bb356a2bc9a48157ba89c022523c387',
                                  '9a975a65ae5fb06c7fac5a21d1312ff631513c5943c4f589c110005c138dc9e0'],
 'Platform/STM32F4/Src/platform_adc_stm32f4.c': ['0a949e523da8a286fd2cc25925b5d613f25fff0ea9e143bf9b8973fcd36fd5ba',
                                                 '28dd6066e483e3d4d00c51df9f87c7a20f86091a25b3be47f189b6d0232fe194'],
 'Platform/STM32F4/Src/platform_critical_stm32f4.c': ['3a43fdd1566cb661746cbb49ca54f4faa80e6727b429024354c869c0bf5cd5a2',
                                                      '5df021617a9c884b4c3a5ae7cc5345143893446563dd471fad454bd68e334f60'],
 'Platform/STM32F4/Src/platform_gpio_stm32f4.c': ['d27e9f43220cc44dc696ebdd8360055bb694f3cbc1ac0a5f5e49784683619db4',
                                                  'd5b73d2baddee3960a077a2b58c97589c7f8ff6ec80c5f48d8fba43e7508c5e4'],
 'Platform/STM32F4/Src/platform_memory_stm32f4.c': ['30ae063e26a00cb9cf833f83939d73644cf1f9f3532f034fe905747aff81ed00',
                                                    '4ac1b9fa6204f24f2ecb83728cab66a680cd59560093482aac45ea56117cbbaa'],
 'Platform/STM32F4/Src/platform_spi_stm32f4.c': ['7550e77eb95ba8abf7f32a21b1c3d92d299de385d435d290d0dff60d9a57a5c0',
                                                 'c8636beccc26c24e9e71b4c98fcf0d8f1c828de81bd69055d6174314c4dc2e02'],
 'Platform/STM32F4/Src/platform_time_stm32f4.c': ['3713d0ae0bfdcd6d21e377e95754213c3535227ef7ee92f7d23096f27f36baac',
                                                  'be9d89f63207c3e15451ba0c2cc358bd237ce4dfaaf7e181c6c97d684187b424'],
 'Platform/STM32F4/Src/platform_uart_stm32f4.c': ['276c2ada321ca4ae18fde92174736181d306f87d7ac0231251e3372469cc8210',
                                                  'cd1dbc2cd1b451460285e76cf36a347e3813748b46597957805ad96ba01405c7'],
 'Protocol/SSLOG/Src/sslog_protocol.c': ['5c8fe7ed812c84719fbde2912c647fce9ec5e54261df534e7939fd65bf8903fb',
                                         'ebae35766761815058a7afa851a773c9abc10fb244ebdb8e7e133bd1d376f298'],
 'Protocol/SSLOG/Src/sslog_records.c': ['0dcc536503f27d5c239816118bf40c164e2e45212c50ea1dac81a159cbd3ae61',
                                        '953ca6691902c19ae0ee8a85e994706ea9cbd529364101c0faf130bae5e60312'],
 'Protocol/Src/air_protocol.c': ['7df6fd221d3edfb336ff08c9bafceddfb45ccef78ee211169ce98b37fe297a3e',
                                 'e584566c51f52e09b9b55263cc709c1ee7a3fc5eb02444b1dda86fd42e974304'],
 'System/Alignment/Src/system_alignment.c': ['0c4e8d7fc2e866087e295616619d14ee83db2b1fb00f94dd0187ce643cd59e62',
                                             '8a976e35fd69eff775e815a549257bddf76322a7a6561fb2798e7abd7c3767f3'],
 'System/Alignment/Src/system_alignment_source.c': ['68117e52ea0c9b4fcfd76212b16f27bf308e22596f259b060798c21a32880605',
                                                    'c1a133620f6c67bcbba347ff04429dbfcd226b2526e400406211e3841474545c'],
 'System/Calibration/Src/system_calibration.c': ['23a1c562acf63b74ccbabb588fd91d84f0fd73506af4f2187bfc7c6357761985',
                                                 'bc73b91ae682182a9bd5572205f04e2928ce33bb8a498a44f719506ba744b8bb'],
 'System/Calibration/Src/system_calibration_correction.c': ['5d3a4639fb9f78673a58b54f4ae6f1f48d8e06197ebdfb57fc8746a4ef7da7fe',
                                                            '8952de946066c40ab77867b53b4460ac2334ae082ddcec895300057ac07fd88f'],
 'System/Calibration/Src/system_mag_calibration.c': ['8137f42bccd32d51169123e1f473a81083a34c1b051772c4b0c93f7303946493',
                                                     'defdf2395b22d45b5cd5618c3ad469a73b0cf7e0973f1f3f2fba63003a890ebc'],
 'System/Indicator/Src/system_indicator.c': ['206eca378d244df4fa3fc752f871b5ee9804789fbf032d6433a7ac58ea1f8d22',
                                             'd47ba2d7d022fc21b34194e2f61ad46e822a96bc70dc65afccdf28dc15711661'],
 'System/Inertial/Src/system_inertial.c': ['d5d16f7156eaae52a5304d460d119df739a9333f346d85fd22e9cb2c7b561737',
                                           'f854faeb0ba9d0d193dafb92ca5cb4a8668231f77659bd8ad07e89b8adf55d76'],
 'System/Src/system_barometer.c': ['781d60a21daa28469cd4f4edd6d70887902443e6e8e49f2dbaca52c01d0538d9',
                                   'a0621875a071368c443414d658cc13df77344c5c63948755b3d341a51e5829cf'],
 'System/Src/system_barometer_cold.c': ['6008bf05ed714bf21f5da57bdf43337c1251323212490d90045923298cddbc37',
                                        '91f864c85d4ce6a15ee036cb3fd8edb712a93f914cc6be2064cf7a71e3321e73'],
 'System/Src/system_capabilities.c': ['4cec9784d55b91fd2b8c7d2c0a1e677a821b31dd88d326bedece319ef25cf36a',
                                      '701fdac7bdb66ce5f5554b1403ac3fcefd4c78fbe26a7a68327bbb1825a89b13'],
 'System/Src/system_console.c': ['85a29bf88ad6e57df1952b92a22f77a6634cc075ebef94d9d9313056d59b4b8b',
                                 'd7f67014d9ac29402e439e64aa88e4c15d9e9f2f704e6d479ae168787c2aa106'],
 'System/Src/system_device_startup.c': ['58c6bd765b74659417313d736c66c97fae028ee543ef0195152f75a282654dc0',
                                        '5deb3923ff1debc6f9359e357903ec164aafe1fbbefa8f46d52348141d8399eb'],
 'System/Src/system_estimator_diagnostics.c': ['23fcc2910dba3340c4adb30b4a865ef0fb0a8815c0f917b839739f46ce9ec489',
                                               '4d534d8f49a012d6b66fb3ba5df4a1dee8aef402e79761579dffef08374d22e6'],
 'System/Src/system_estimator_profile.c': ['c53961a14d645bb50bc3e27acdcbe50521574bfefef23738f9766551d0cc0a2c',
                                           'fd73b61e3fbb9ca21634f059ea95df14ec3c10b205ad643e1bd4f74a0a7ee75c'],
 'System/Src/system_gnss_quality.c': ['402dbdb31f735792864b4acabd5eea8a204df6564b8f428f3f74b7821f55aec6',
                                      'ca5c9cbf5acbffcdf2017ec8650afc595afe87a864cf861264e50426e4b18e19'],
 'System/Src/system_health.c': ['acc65014a1f382158a25edf3918f89e26e10aca1640785c6f21a0f5325bc3e99',
                                'd11f9bd66b7ee0e64be8aaffdf3b4646c0288556ba2ae58425a10d13e1c36edf'],
 'System/Src/system_imu_epoch.c': ['8c42e1940c5d57719fa2d61344927f24cb0d85d8971a9ff8a01be1aa8971ca1b',
                                   'b7f978dba0dd59d5b15ac702fba0570533b7f519c81d97017deb73749d3a8734'],
 'System/Src/system_log_file.c': ['0b0847936c47f872907567bacfeaf04a596274fc7a0894761732809fcfd05b21',
                                  'b72443bff4a5c23f57487cc70eb87a7e3c8b4565003a9b91a114dc3c0bd75ebe'],
 'System/Src/system_log_policy.c': ['0c6cebf63caf000485d324edbccc73a5b1f64e41915f125709a6b2e510bb2ea2',
                                    '276d88644b1bec886cb92cf67634f04d101d444e39a47b32423abe1435a8098c'],
 'System/Src/system_navigation_health.c': ['2a8149998c3efa5822aac2015d8cc65a2691aa64378cea20dc8969ed85b8477d',
                                           '50f7ec913699a889178ea1bfceb64234846e87aaeb6d3c0db9d4798a789c89e8'],
 'System/Src/system_navigation_profile.c': ['0f5346c2e17c887733b8c28c1d1dad33dac51178fb10a42b7a16b9c1b85c0f9b',
                                            '495c75b2eb29dcfd2bf599e54bccbb26b1247567378e7dc503ea7a10e6040527'],
 'System/Src/system_profile.c': ['580e29d94608d8a2c34667234ddd7be78d7224174deaa227f581d1ee6dc3d242',
                                 'c582bbb5cef0143bd2d23d3963bbdd3a1c72f44a30f29b5fb0f0d579447e6ffc'],
 'System/Src/system_sensor_status.c': ['11d41f43732452853acf4f60c568a7780433fa87dbdf07bb8cf664d3a5acf48a',
                                       '79c682a90a66e08f5867fd2b18a6eed39578fc6a98a35785946aebf92ff9cf8b'],
 'System/Src/system_source_selector.c': ['046b64beb5012fcda8f3d7c786f024403941785c811982b094c6f57c8e87901b',
                                         'fe2384828a211b7f111e539e9e3601a73e00f6f67fd3ea69489927a82280a7ac'],
 'System/Src/system_startup.c': ['476ab375186a534c9e164106c77ec4087016a1bc200b4d7c52b83ec234ec23b4',
                                 'ba1ef40078989a2822671ef44a0cb0c12ffdc8b17e56bd91e118be3799732830'],
 'System/Src/system_time.c': ['087feab58f8e771e312febe2bdee73258481ee5305b2bacd695bd5fe89859e27',
                              '0b4fa47c3ec52bb79ae776e07bde37477b0dbbbc98b8230522f03b5ec5b80892'],
 'System/User/system_user_inertial_config.c': ['84e346f4e4e23354f8522f50878ca495668f8c4344535799a3fbd885e01aa2eb',
                                               'cc4d041493aabbc878960143a6ad5f954f54ff330b8d480cc934a280fd84eaf0'],
 'Targets/SilverStar_F407/Src/freertos_target_irq.c': ['4eefda56f0a16d25b04e7d4f124c26870bdbce4521304e4f1384a58b11da7650',
                                                       '8a46ff3c2b481b4f66ee175a6a7f3be3f9f9335bccd49fdafc3273f431127af3'],
 'ThirdParty/FreeRTOS-Kernel/list.c': ['1c201989684f4407abe4333d4f34e644cfc53ee40e6c8d5525f62aee13faaea0',
                                       'eab506ab40b3f682ef3870f5c40b5fe18645c1fa75319957a7bdb28802c446fd'],
 'ThirdParty/FreeRTOS-Kernel/portable/GCC/ARM_CM4F/port.c': ['742de5006fdd5b1f61b5413e714ce861b00d70c34b355ac96503eb5b7645dd5b',
                                                             '9f078de8cf519e2fee83a249b2f5e9b1abec282b1d20f1f79499500d5175e64a'],
 'ThirdParty/FreeRTOS-Kernel/queue.c': ['2c2fa83a64a45fcd8337a97e136a85f95ab97ea32d93551ef5e93b8632e116a4',
                                        '526730532997bbfa24fe851a7ac361334f6e1c5b35d64c0ef98cd5a4a4952474'],
 'ThirdParty/FreeRTOS-Kernel/tasks.c': ['c353efd750e7e387baca817540ed35edab18deb9c6d5dac1125f262748730d8a',
                                        'edd593618732e12e99b0e158586a725e55a1bf62f6e6a1c2980f46984d2bc191']}


def BindingSourceVersions_Get(path):
    return (BINDING_SOURCE_V2.get(path, []) + BINDING_SOURCE_EPOCH_V3.get(path, []) +
            BINDING_SOURCE_LOGGER_V4.get(path, []) + BINDING_SOURCE_NRF_V5.get(path, []) +
            BINDING_SOURCE_HEALTH_V6.get(path, []) + BINDING_SOURCE_POWER_V7.get(path, []) +
            BINDING_SOURCE_MINIMAL_QUEUE_V8.get(path, []) +
            BINDING_SOURCE_RF_QUEUE_V9.get(path, []) +
            BINDING_SOURCE_STATIC_BENCH_V10.get(path, []) +
            BINDING_SOURCE_HEALTH_FINALIZATION_V11.get(path, []) +
            BINDING_SOURCE_PRODUCT_PATCH_V12.get(path, []) +
            BINDING_SOURCE_PRODUCT_METADATA_V13.get(path, []) +
            BINDING_SOURCE_PRODUCT_DECODER_V14.get(path, []) +
            BINDING_SOURCE_INTEGRATION_IDENTITIES_V15.get(path, []) +
            BINDING_SOURCE_UART_MAINTENANCE_V16.get(path, []) +
            BINDING_SOURCE_MAINTENANCE_DIAGNOSTICS_V17.get(path, []) +
            BINDING_SOURCE_ALGORITHM_TIMING_V18.get(path, []) +
            BINDING_SOURCE_HORIZON_V19.get(path, []))


def BindingSourceHash_Get(text):
    # read_text normalizes CRLF; retain every other byte, including macros,
    # string whitespace and comments. Canonical body checks alone are weaker.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def BindingClosureHash_Get(source, source_hash, inputs):
    payload = {"source": source, "source_sha256": source_hash, "inputs": inputs}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()

def BindingSources_Verify(root, sources, build):
    proofs = []
    for path in sources:
        (root / path).resolve().relative_to(root.resolve())
        text = (root / path).read_text(encoding="utf-8")
        actual = BindingSourceHash_Get(text)
        if actual not in BindingSourceVersions_Get(path):
            raise ValueError("Changed or unknown complete callback binding source: " + path)
        dependency = build / Path(path).with_suffix(".d")
        if not dependency.is_file():
            raise ValueError("Missing compiled source dependency report: " + path)
        # GCC -MMD output: first continued rule, followed by -MP phony rules.
        dependencies = dependency.read_text(encoding="utf-8").split(":", 1)[1].replace("\\\n", " ").split("\n", 1)[0].split()
        expected_graph = (BINDING_DEPENDENCIES_V2.get(path, []) +
                          BINDING_DEPENDENCIES_EPOCH_V3.get(path, []) +
                          BINDING_DEPENDENCIES_NRF_V5.get(path, []) +
                          BINDING_DEPENDENCIES_HEALTH_V6.get(path, []) +
                          BINDING_DEPENDENCIES_POWER_V7.get(path, []) +
                          BINDING_DEPENDENCIES_RF_QUEUE_V9.get(path, []) +
                          BINDING_DEPENDENCIES_UART_MAINTENANCE_V16.get(path, []) +
                          BINDING_DEPENDENCIES_ALGORITHM_TIMING_V18.get(path, []) +
                          BINDING_DEPENDENCIES_HORIZON_V19.get(path, []))
        graph_hash = hashlib.sha256("\n".join(dependencies).encode()).hexdigest()
        if graph_hash not in expected_graph:
            raise ValueError("Changed compiled callback dependency graph: " + path)
        compiled_inputs = []
        current_review = (actual in BINDING_SOURCE_ALGORITHM_TIMING_V18.get(path, []) or
                          actual in BINDING_SOURCE_HORIZON_V19.get(path, []))
        for dependency_input in dependencies:
            # Included .inc, .c and other suffixes can change executable code.
            # The reviewed compiler graph, not a filename extension, is authoritative.
            digest = BindingHeader_Verify(root, dependency_input)
            compiled_inputs.append([dependency_input, digest])
            current_review = (current_review or
                digest in BINDING_SOURCE_ALGORITHM_TIMING_V18.get(dependency_input, []) or
                digest in BINDING_SOURCE_HORIZON_V19.get(dependency_input, []))
        closure = BindingClosureHash_Get(path, actual, compiled_inputs)
        if current_review and closure not in (BINDING_COMPILED_INPUTS_ALGORITHM_TIMING_V18.get(path, []) +
                                              BINDING_COMPILED_INPUTS_HORIZON_V19.get(path, [])):
            raise ValueError("Changed paired source/compiler input closure: " + path)
        proofs.append({"source": path, "normalized_source_sha256": actual,
                       "dependencies": dependencies, "compiled_input_sha256": closure})
    return proofs

def BindingHeader_Verify(root, path):
    (root / path).resolve().relative_to(root.resolve())
    if not (root / path).is_file():
        raise ValueError("Changed or missing reviewed callback compilation input: " + path)
    actual = BindingSourceHash_Get((root / path).read_text(encoding="utf-8"))
    if actual not in BindingSourceVersions_Get(path):
        raise ValueError("Changed or missing reviewed callback compilation input: " + path)
    return actual

def IndirectSites_Get(rows):
    return [(op, args) for op, args in rows
            if (op == "blx" and "<" not in args) or (op.startswith("bx") and args.strip() != "lr")]


def CallbackSlot_Get(rows, index):
    """Recognize only the reviewed straight-line load/move before a call.

    Whole-source/ABI contracts establish the table's provenance. This checks
    the actual linked call register and slot, including tail BX ip. Other
    compiler shapes are NOT PROVEN; this is deliberately not a CFG analyzer.
    """
    register = rows[index][1].strip()
    for op, operands in reversed(rows[max(0, index - 5):index]):
        operands = operands.split("@")[0].strip()
        if op.startswith("mov") and (match := re.fullmatch(r"(\w+),\s*(\w+)", operands)) and match[1] == register:
            register = match[2]
        elif op in ("ldr", "ldr.w") and (match := re.fullmatch(r"(\w+),\s*\[(\w+),\s*#(\d+)\]", operands)) and match[1] == register:
            return int(match[3])
        elif re.match(re.escape(register) + r",", operands):
            raise ValueError("Unreviewed linked callback register write")
    raise ValueError("Linked callback slot NOT PROVEN")


def TableBytes_Get(root, prefix, elf, address, size):
    data = Command_Read([prefix + "objdump", "-s", "--start-address=" + hex(address),
                         "--stop-address=" + hex(address + size), str(elf)], root)
    if "file format elf32-littlearm" not in data:
        raise ValueError("Unreviewed callback table ELF ABI")
    memory = {}
    for line in data.splitlines():
        if match := re.match(r"\s*([0-9a-f]+)\s+((?:[0-9a-f]{8}\s*){1,4})", line):
            for offset, byte in enumerate(bytes.fromhex(match[2])):
                memory[int(match[1], 16) + offset] = byte
    if any(address + offset not in memory for offset in range(size)):
        raise ValueError("Missing linked callback table bytes")
    return bytes(memory[address + offset] for offset in range(size))


def StackReport_Build(root: Path, config: str, prefix: str, memory_layout: str = "legacy") -> dict:
    target = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf-8"))["build"]["target_profile"]
    if memory_layout not in ("legacy", "eskf_window_sram", "auto"):
        raise ValueError("Unsupported memory layout")
    build = root / "build/FCCG" / target / config
    if memory_layout != "legacy":
        build = build / memory_layout
    build = build.resolve()
    build.relative_to(root.resolve())
    elfs = list(build.glob("*.elf"))
    if len(elfs) != 1:
        raise ValueError("Expected exactly one linked ELF in the selected configuration")
    elf = elfs[0]
    disassembly = Command_Read([prefix + "objdump", "-d", str(elf)], root)
    nm = Command_Read([prefix + "nm", "-S", "--defined-only", str(elf)], root)
    sizes = {parts[3]: int(parts[1], 16) for line in nm.splitlines()
             if len(parts := line.split()) == 4}
    frames: dict[str, int] = {}
    unbounded: set[str] = set()
    # Consume the resolved generator graph, not stale objects left by an earlier
    # configuration. Every compiled C source must supply GCC's own frame report;
    # disassembly fallback is reserved for linked assembly/runtime libraries.
    manifest = (root / "Generated/project_sources.mk").read_text(encoding="utf-8")
    block = re.search(r"(?ms)^C_SOURCES \+= \\\n(.*?)(?:\n\n|\Z)", manifest)
    if block is None:
        raise ValueError("Missing resolved C source graph")
    sources = [line.strip().removesuffix("\\").strip() for line in block[1].splitlines()]
    su_paths = [build / Path(source).with_suffix(".su") for source in sources]
    for source, path in zip(sources, su_paths):
        path.resolve().relative_to(build)
        if not source.endswith(".c") or not path.is_file():
            raise ValueError("Missing source stack report; rebuild: " + source)
    for path in su_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            location, count, kind = line.split("\t")
            name = location.rsplit(":", 1)[1]
            frames[name] = max(frames.get(name, 0), int(count))
            if kind not in ("static", "dynamic,bounded"):
                unbounded.add(name)
    instructions: dict[str, list[tuple[str, str]]] = {}
    for line in disassembly.splitlines():
        if match := re.match(r"^[0-9a-f]+ <([^>]+)>:", line):
            name = match[1]
            instructions[name] = []
        elif match := re.match(r"^\s*[0-9a-f]+:\s+(?:[0-9a-f]{4,8}\s+)+(\S+)\s*(.*)", line):
            instructions[name].append((match[1], match[2]))

    edges: dict[str, set[str]] = {}
    indirect: set[str] = set()
    library_frames: dict[str, int] = {}
    for name, rows in instructions.items():
        edges[name] = set()
        frame = 0
        for op, args in rows:
            if (
                (op.startswith("b") or op in ("cbz", "cbnz"))
                and (match := re.search(r"<([^>+]+)(?:\+[^>]+)?>", args))
                and (match[1] != name or op in ("bl", "bl.w", "blx"))
                and match[1] in instructions
            ):
                edges[name].add(match[1])
            if (op == "blx" and "<" not in args) or (op.startswith("bx") and args.strip() != "lr"):
                indirect.add(name)
            if name in frames:
                continue
            if op.startswith(("push", "stmdb")) and "{" in args:
                frame += RegisterBytes_Get(args[args.index("{"):], 4)
            elif op.startswith("vpush"):
                frame += RegisterBytes_Get(args, 8 if "d" in args else 4)
            elif op.startswith("sub") and re.match(r"sp,\s*(?:sp,\s*)?#", args):
                frame += int(re.search(r"#(0x[0-9a-f]+|\d+)", args)[1], 0)
            elif re.search(r"\[sp,\s*#-(0x[0-9a-f]+|\d+)\]!", args):
                frame += int(re.search(r"#-(0x[0-9a-f]+|\d+)", args)[1], 0)
            elif re.search(r"\[sp[^\]]*\]!", args) or re.match(r"sp,", args) and op.startswith(("sub", "mov", "bic")):
                unbounded.add(name)
        if name not in frames:
            frames[name] = frame
            library_frames[name] = frame

    callback_site_bindings = []
    sd_sources = [source for source in sources if source.endswith("/sd_diskio.c") or
                  source == "Platform/STM32F1Flight/Src/sd_diskio_stm32f1flight.c"]
    if len(sd_sources) > 1:
        raise ValueError("Multiple selected SD_Driver providers")
    if sd_sources:
        sd_source = root / sd_sources[0]
        source = sd_source.read_text(encoding="utf-8")
        table = re.search(r"(?:const\s+)?Diskio_drvTypeDef\s+SD_Driver\s*=\s*\{(.*?)\};", source, re.DOTALL)
        fatfs = next(iter(root.glob("HardwareGenerated/STM32CubeMX/FATFS/App/fatfs.c")), root / "FATFS/App/fatfs.c")
        if not table or not fatfs.exists() or not re.search(r"FATFS_LinkDriver\(&SD_Driver,", fatfs.read_text(encoding="utf-8")):
            raise ValueError("Cannot verify the single SD_Driver callback binding")
        # F1's R0.11 ABI declares the table non-const. This is a fixed selected
        # provider, not permission for another registration/callback registry.
        table_code = re.sub(r"/\*.*?\*/|//[^\n]*", "", table[1], flags=re.DOTALL)
        # Existing F4 glue conditionally declares the write/ioctl ABI slots.
        # Admit only those exact guards, with their targets actually linked.
        for macro, callback in (("_USE_WRITE", "SD_write"), ("_USE_IOCTL", "SD_ioctl")):
            guard = rf"#if\s+{macro}\s*==\s*1\s*\n\s*{callback},\s*\n#endif"
            if re.search(guard, table_code):
                if callback not in instructions:
                    raise ValueError("Missing linked conditional SD callback: " + callback)
                table_code = re.sub(guard, callback + ",", table_code)
        entries = re.findall(r"\b[A-Za-z]\w*\b", table_code)
        if entries != list(DISK_CALLBACKS.values()):
            raise ValueError("Unreviewed selected SD_Driver callback table")
        registrations = {caller for caller, callees in edges.items() if "FATFS_LinkDriver" in callees}
        if registrations != {"MX_FATFS_Init"}:
            raise ValueError("Unreviewed SD_Driver registration caller")
        if any(re.search(r"\bSD_Driver\s*\.\s*\w+\s*=", (root / path).read_text(encoding="utf-8")) for path in sources):
            raise ValueError("Mutable SD_Driver callback assignment")
        if sd_sources:
            # R0.11's writable table cannot earn an immutable-object claim.
            # Freeze the reviewed registration/dispatch implementation and all
            # source references, then verify initialized callback pointers in
            # the actual ELF. This does not prove freedom from RAM corruption.
            reviewed_fatfs = {
                "Middlewares/Third_Party/FatFs/src/ff_gen_drv.c":
                    "36679af13a80db6a2fe0fb27918a2e420ad662e28f9491e59c91c2931e75e609",
                "Middlewares/Third_Party/FatFs/src/diskio.c":
                    "b70fbf239fe462cb5f1918f77d04b7d68cf8f71eadf3d9778e7e55abecb75fc7",
            }
            if not sd_sources[0].startswith("Platform/STM32F1Flight/"):
                reviewed_fatfs = {
                    "Middlewares/Third_Party/FatFs/src/ff_gen_drv.c": "0fc75735ced23deb5ba70713ec41bb75883a886deaa2bbabb7589e2305925bb3",
                    "Middlewares/Third_Party/FatFs/src/diskio.c": "77ac8b08957b2c7b3e4f9401c37727c87a660ed589f0ce9e6520faf6ab91a574",
                }
            BindingHeader_Verify(root, "Middlewares/Third_Party/FatFs/src/ff_gen_drv.h")
            for path, expected in reviewed_fatfs.items():
                if path not in sources:
                    raise ValueError("Missing selected F1 FatFs binding source")
                canonical = re.sub(r"/\*.*?\*/|//[^\n]*", "", (root / path).read_text(encoding="utf-8"), flags=re.DOTALL)
                if hashlib.sha256(re.sub(r"\s+", "", canonical).encode()).hexdigest() != expected:
                    raise ValueError("Changed reviewed F1 FatFs binding source: " + path)
            if FunctionBody_Get(fatfs.read_text(encoding="utf-8"), "MX_FATFS_Init") != "MX_FATFS_Init(void){retSD=FATFS_LinkDriver(&SD_Driver,SDPath);}":
                raise ValueError("Changed reviewed F1 SD registration")
            allowed_refs = {sd_sources[0], fatfs.relative_to(root).as_posix()}
            for path in sources:
                code = re.sub(r"/\*.*?\*/|//[^\n]*", "", (root / path).read_text(encoding="utf-8"), flags=re.DOTALL)
                refs = len(re.findall(r"\bSD_Driver\b", code))
                if refs != (1 if path in allowed_refs else 0):
                    raise ValueError("Unreviewed F1 SD_Driver source reference: " + path)
            extended_callers = {caller for caller, callees in edges.items() if "FATFS_LinkDriverEx" in callees}
            expected_extended = {"FATFS_LinkDriver"} if "FATFS_LinkDriverEx" in instructions else set()
            if extended_callers != expected_extended:
                raise ValueError("Unreviewed F1 extended SD registration caller")
            symbols = {parts[3]: parts for line in nm.splitlines() if len(parts := line.split()) == 4}
            if "SD_Driver" not in symbols or symbols["SD_Driver"][2] != ("D" if sd_sources[0].startswith("Platform/STM32F1Flight/") else "R") or int(symbols["SD_Driver"][1], 16) != 20:
                raise ValueError("Changed linked F1 SD_Driver table ABI")
            address = int(symbols["SD_Driver"][0], 16)
            data = Command_Read([prefix + "objdump", "-s", "--start-address=" + hex(address),
                                 "--stop-address=" + hex(address + 20), str(elf)], root)
            raw = b"".join(bytes.fromhex(match[1]) for line in data.splitlines()
                if (match := re.match(r"\s*[0-9a-f]+\s+((?:[0-9a-f]{8}\s*){1,4})", line)))
            expected = b"".join((int(symbols[entry][0], 16) | 1).to_bytes(4, "little") for entry in entries if entry in symbols)
            if "file format elf32-littlearm" not in data or len(expected) != 20 or raw != expected:
                raise ValueError("Linked F1 SD callback pointers differ from reviewed table")
        for caller, callee in DISK_CALLBACKS.items():
            if caller in indirect and callee in instructions and re.search(rf"\b{callee}\b", table[1]):
                if len(IndirectSites_Get(instructions[caller])) != 1:
                    raise ValueError("Extra indirect SD callback instruction: " + caller)
                site = next(index for index, row in enumerate(instructions[caller]) if IndirectSites_Get([row]))
                if CallbackSlot_Get(instructions[caller], site) != list(DISK_CALLBACKS).index(caller) * 4:
                    raise ValueError("Wrong linked SD callback slot: " + caller)
                callback_site_bindings.append({"caller": caller, "instruction_index": site,
                    "slot_offset": list(DISK_CALLBACKS).index(caller) * 4, "targets": [callee]})
                edges[caller].add(callee)
                indirect.remove(caller)

    # SystemDeviceStartup has one immutable operations table per linked device.
    # Resolve every callback to the selected tables, taking the deeper
    # branch. Refuse new callers or tables until their binding is reviewed.
    if "SystemDeviceStartup_Tick" in instructions:
        startup_callers = {caller for caller, callees in edges.items()
                           if "SystemDeviceStartup_Init" in callees}
        selected_startup_sources = [source for source in STARTUP_CALLBACK_SOURCES if source in sources]
        if not selected_startup_sources:
            raise ValueError("Missing reviewed startup callback sources in the selected graph")
        expected_callers = set()
        if STARTUP_CALLBACK_SOURCES[0] in selected_startup_sources:
            expected_callers.add("Jy901bStartup_Init")
        if STARTUP_CALLBACK_SOURCES[1] in selected_startup_sources:
            expected_callers.add("NeoM9nStartup_Init")
        # The reviewed M9N recovery reuses controller.config, including the
        # original immutable operations table. O2 inlines RecoveryBegin into
        # Tick; Debug retains its separate frame. Admit exactly one of these
        # known caller sets; keep unknown callers/tables fatal.
        reviewed_callers = (expected_callers,)
        if STARTUP_CALLBACK_SOURCES[1] in selected_startup_sources:
            reviewed_callers = (
                expected_callers | {"NeoM9nStartup_Tick"},
                expected_callers | {"NeoM9nStartup_RecoveryBegin"},
            )
        if startup_callers not in reviewed_callers:
            raise ValueError("Unreviewed device startup operation binding: " +
                             repr(sorted(startup_callers)))
        if config != "Release":
            raise ValueError("Startup callback Debug binding NOT PROVEN; requires a reviewed linked shape")
        if "System/Src/system_device_startup.c" not in sources:
            raise ValueError("Missing complete reviewed startup controller source")
        BindingHeader_Verify(root, "System/Inc/system_device_startup.h")
        callbacks: set[str] = set()
        startup_tables = []
        for source_name in selected_startup_sources:
            source_text = (root / source_name).read_text(encoding="utf-8")
            tables = re.findall(
                r"static\s+const\s+SystemDeviceStartupOperations\s+s_operations\s*=\s*\{(.*?)\};",
                source_text, re.DOTALL)
            if len(tables) != 1 or len(entries := re.findall(r"\b[A-Za-z]\w*\b", tables[0])) != 7:
                raise ValueError("Unreviewed device startup operation table: " + source_name)
            if not re.search(r"config\.operations\s*=\s*&s_operations\s*;", source_text):
                raise ValueError("Unbound device startup operation table: " + source_name)
            if not all(entry in instructions for entry in entries):
                raise ValueError("Missing linked device startup callback: " + source_name)
            if source_name.endswith("neo_m9n_startup.c"):
                recovery = re.search(
                    r"static void NeoM9nStartup_RecoveryBegin\(.*?\n}\s*",
                    source_text, re.DOTALL)
                if (not recovery or
                        len(re.findall(r"config\s*=\s*context->controller\.config\s*;",
                                       recovery[0])) != 1 or
                        re.search(r"config\.operations\s*=", recovery[0])):
                    raise ValueError("Unreviewed M9N recovery operation binding")
            callbacks.update(entries)
            startup_tables.append((source_name, entries))
        symbols = {parts[3]: parts for line in nm.splitlines() if len(parts := line.split()) == 4 and parts[3] != "s_operations"}
        linked_tables = [parts for line in nm.splitlines() if len(parts := line.split()) == 4 and parts[3] == "s_operations"]
        if len(linked_tables) != len(startup_tables) or any(parts[2] != "r" or int(parts[1], 16) != 28 for parts in linked_tables):
            raise ValueError("Startup operations are not the selected linked read-only tables")
        available = {int(parts[0], 16): TableBytes_Get(root, prefix, elf, int(parts[0], 16), 28) for parts in linked_tables}
        for source_name, entries in startup_tables:
            expected = b"".join((int(symbols[entry][0], 16) | 1).to_bytes(4, "little") for entry in entries if entry in symbols)
            matches = [address for address, raw in available.items() if raw == expected]
            if len(expected) != 28 or len(matches) != 1:
                raise ValueError("Linked startup callback pointers differ from reviewed table")
            init = "NeoM9nStartup_Init" if "neo_m9n" in source_name else "Jy901bStartup_Init"
            words = {int(args, 16) for op, args in instructions.get(init, []) if op == ".word"}
            if matches[0] not in words:
                raise ValueError("Linked startup initializer does not bind its reviewed table")
            del available[matches[0]]
        callers = ("SystemDeviceStartup_ProbeTick", "SystemDeviceStartup_ReadTick",
                   "SystemDeviceStartup_ApplyTick", "SystemDeviceStartup_Tick")
        # Reviewed GCC 14.3 Release inlines all seven source callback sites.
        # Other shapes remain NOT PROVEN until separately reviewed.
        if any(name in indirect for name in callers[:-1]) or len(IndirectSites_Get(instructions["SystemDeviceStartup_Tick"])) != 7:
            raise ValueError("Unreviewed startup indirect call-site coverage")
        slots = [CallbackSlot_Get(instructions["SystemDeviceStartup_Tick"], index)
                 for index, row in enumerate(instructions["SystemDeviceStartup_Tick"]) if IndirectSites_Get([row])]
        if slots != [4, 0, 8, 12, 16, 20, 24]:
            raise ValueError("Unreviewed linked startup callback slot sequence")
        for index, row in enumerate(instructions["SystemDeviceStartup_Tick"]):
            if IndirectSites_Get([row]):
                slot = CallbackSlot_Get(instructions["SystemDeviceStartup_Tick"], index)
                callback_site_bindings.append({"caller": "SystemDeviceStartup_Tick",
                    "instruction_index": index, "slot_offset": slot,
                    "targets": [entries[slot // 4] for _, entries in startup_tables]})
        for caller in callers:
            if caller in indirect:
                edges[caller].update(callbacks)
                indirect.remove(caller)

    callback_bindings = MpuCallbackBindings_Resolve(
        root, sources, instructions, edges, indirect, nm, prefix, elf)

    binding_source_proofs = BindingSources_Verify(root, sources, build)

    def Closure_Get(name: str) -> set[str]:
        seen: set[str] = set()
        pending = [name]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(edges.get(node, ()))
        return seen

    memo: dict[str, tuple[int, list[str]]] = {}
    def Budget_Get(name: str, visiting: tuple[str, ...] = ()) -> tuple[int, list[str]]:
        if name in visiting:
            raise ValueError("Recursive stack path: " + " -> ".join((*visiting, name)))
        if name in indirect or name in unbounded:
            raise ValueError("Unresolved stack usage: " + name)
        if name not in memo:
            children = [Budget_Get(child, (*visiting, name)) for child in sorted(edges.get(name, ()))]
            count, path = max(children, default=(0, []), key=lambda item: item[0])
            memo[name] = (frames[name] + count, [name, *path])
        return memo[name]

    tasks = []
    for label, (entry, stack) in TASKS.items():
        if entry not in instructions:
            if stack in sizes:
                raise ValueError("Task stack exists without entry: " + label)
            continue
        if stack not in sizes:
            raise ValueError("Missing configured stack symbol: " + stack)
        count, chain = Budget_Get(entry)
        estimate = count + CONTEXT_BYTES
        tasks.append({"task": label, "configured_bytes": sizes[stack],
                      "call_chain_bytes": count, "context_bytes": CONTEXT_BYTES,
                      "worst_known_bytes": estimate, "margin_bytes": sizes[stack] - estimate,
                      "chain": [{"function": node, "frame_bytes": frames[node]} for node in chain],
                      "passes": sizes[stack] - estimate >= MIN_MARGIN_BYTES})
    init_closure = Closure_Get("AppTasks_Init")
    align_closure = Closure_Get("SystemAlignment_Start")
    checks = {
        "indicator_in_production_init": "SystemIndicator_Init" in init_closure and "AppTasks_Init" in Closure_Get("main"),
        "alignment_start_deferred": "SystemAlignment_Process" not in align_closure,
        "flight_processes_alignment": "SystemAlignment_Process" in Closure_Get("AppTask_Flight"),
        "communication_does_not_process_alignment": all(
            "SystemAlignment_Process" not in Closure_Get(entry)
            for entry in ("AppTask_Telemetry", "AppTask_Serial")),
        "all_enabled_tasks_budgeted": {
            name for name in instructions if name.startswith("AppTask_") or name in ("prvIdleTask", "prvTimerTask")
        } == {TASKS[row["task"]][0] for row in tasks},
    }
    reachable = set().union(*(Closure_Get(TASKS[row["task"]][0]) for row in tasks))
    return {"schema": "silverstar.stack-budget/1", "configuration": config,
            "elf": str(elf.relative_to(root)), "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
            "compiler": Command_Read([prefix + "gcc", "--version"], root).splitlines()[0],
            "su_files": len(su_paths), "minimum_margin_bytes": MIN_MARGIN_BYTES,
            "callback_bindings": callback_bindings,
            "binding_contract": "silverstar.reviewed-callback-bindings/2",
            "binding_review_revision": BINDING_REVIEW_REVISION,
            "binding_source_proofs": binding_source_proofs,
            "callback_site_bindings": callback_site_bindings,
            "whole_program_stack_acceptance": "NOT PROVEN: MSP/main/ISR nesting and hardware margins require separate evidence",
            "method": __doc__, "checks": checks, "tasks": tasks,
            "library_frames": {name: count for name, count in sorted(library_frames.items()) if name in reachable},
            "hardware_high_water_marks": "not measured; use normal stack snapshot on SS0.5",
            "passes": all(checks.values()) and all(row["passes"] for row in tasks)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", choices=("Release", "Debug"), default="Release")
    parser.add_argument("--memory-layout", choices=("legacy", "eskf_window_sram", "auto"), default="legacy")
    parser.add_argument("--prefix", default="arm-none-eabi-")
    arguments = parser.parse_args()
    root = arguments.project.resolve(strict=True)
    print("FCCG_PROGRESS|STACK_REPORT|PLAN|1", flush=True)
    print("FCCG_PROGRESS|STACK_REPORT|BEGIN|1|1|ELF and stack budget", flush=True)
    report = StackReport_Build(root, arguments.config, arguments.prefix, arguments.memory_layout)
    destination = root / Path(report["elf"]).parent / "stack-budget.json"
    destination.resolve().relative_to(root)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["tasks"]:
        print(f"{row['task']}: configured={row['configured_bytes']} estimate={row['worst_known_bytes']} margin={row['margin_bytes']}")
    print(json.dumps(report["checks"], indent=2))
    if report["passes"]:
        print("FCCG_PROGRESS|STACK_REPORT|DONE|1|1|ELF and stack budget")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
