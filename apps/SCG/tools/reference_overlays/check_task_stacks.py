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
BINDING_REVIEW_REVISION = "uart_maintenance_20261013_v16"
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
            BINDING_SOURCE_UART_MAINTENANCE_V16.get(path, []))


def BindingSourceHash_Get(text):
    # read_text normalizes CRLF; retain every other byte, including macros,
    # string whitespace and comments. Canonical body checks alone are weaker.
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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
                          BINDING_DEPENDENCIES_UART_MAINTENANCE_V16.get(path, []))
        graph_hash = hashlib.sha256("\n".join(dependencies).encode()).hexdigest()
        if graph_hash not in expected_graph:
            raise ValueError("Changed compiled callback dependency graph: " + path)
        for dependency_input in dependencies:
            # Included .inc, .c and other suffixes can change executable code.
            # The reviewed compiler graph, not a filename extension, is authoritative.
            BindingHeader_Verify(root, dependency_input)
        proofs.append({"source": path, "normalized_source_sha256": actual, "dependencies": dependencies})
    return proofs

def BindingHeader_Verify(root, path):
    (root / path).resolve().relative_to(root.resolve())
    if not (root / path).is_file() or BindingSourceHash_Get((root / path).read_text(encoding="utf-8")) not in BindingSourceVersions_Get(path):
        raise ValueError("Changed or missing reviewed callback compilation input: " + path)

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
