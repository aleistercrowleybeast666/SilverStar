"""Report linked vectors, calls and individual .su frames; never enroll a new proof."""
import hashlib
import json
from collections import deque
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
GCC = Path("D:/Arm GNU Toolchain/14.3 rel1/bin")
HERE = Path(__file__).resolve().parent


def capture(tool, *args):
    command = [str(GCC / ("arm-none-eabi-" + tool + ".exe")), *map(str,args)]
    result = subprocess.run(command, check=True, capture_output=True)
    return result.stdout.decode("utf8", errors="replace")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def path_to(edges, entry, needle):
    paths = deque([[entry]])
    seen = set()
    while paths:
        path = paths.popleft()
        name = path[-1]
        if name.startswith(needle):
            return path
        if name in seen:
            continue
        seen.add(name)
        paths.extend([*path, next_] for next_ in edges.get(name, ()) if next_ not in seen)
    return []


def main(version, case, config):
    project = ROOT / ".work/release-20261103/sensors" / version / case / "Flight_Controller"
    build = next((project / "build/FCCG").glob("SilverStar_*/" + config))
    elf = next(build.glob("*.elf"))
    dis = capture("objdump", "-d", elf)
    nm = capture("nm", "-S", "--defined-only", elf)
    names, edges = {}, {}
    current = None
    for line in dis.splitlines():
        function = re.fullmatch(r"([0-9a-f]+) <([^>]+)>:",line)
        if function:
            current = function[2]
            names[int(function[1],16)] = current
        call = re.search(r"\s(?:b|b\.n|b\.w|bl|blx)\s+[0-9a-f]+\s+<([^>+]+)>",line)
        if call and current and current != call[1]:
            edges.setdefault(current, set()).add(call[1])
    frames = {}
    for su in build.rglob("*.su"):
        for line in su.read_text(encoding="utf8",errors="replace").splitlines():
            match = re.match(r"(.+?):\d+:\d+:(\S+)\s+(\d+)\s+(.+)$",line)
            if match:
                frames[match[2]] = dict(source=match[1], bytes=int(match[3]), classification=match[4])
    traces = {}
    for entry, target in (("AppTask_Device","SystemMagRotation_MagObserve"),
            ("AppTask_Device","MagRotation_Step"),("AppTask_Device","LoggerBus_RotationEventPush"),
            ("AppTask_Device","SystemMagRotation_ImuObserve"),("AppTask_Serial","SystemMagRotation_StatusWrite"),
            ("EXTI2_IRQHandler","PlatformTime_Us"),("EXTI3_IRQHandler","PlatformTime_Us")):
        path = path_to(edges,entry,target)
        traces[entry+" -> "+target] = [dict(symbol=n,frame=frames.get(n)) for n in path]
    files = {str(su.relative_to(build)):digest(su) for su in build.rglob("*.su")
        if su.stem in ("mag_rotation","mag_rotation_runtime","system_mag_calibration","sensor_imu_adapter",
                       "mmc5983ma_adapter","system_installation_capture","platform_gpio_stm32f4","platform_gpio_stm32h7")}
    check = capture("objdump","-s","-j",".isr_vector",elf).splitlines()
    vector = bytearray()
    for line in check:
        m = re.match(r"^\s*[0-9a-f]+\s+((?:[0-9a-f]{8} ){1,4})",line)
        if m:
            vector.extend(bytes.fromhex(m[1]))
    irq = {}
    if case=="h743":
        for number,irq_name in [(8,"EXTI2_IRQHandler"),(9,"EXTI3_IRQHandler")]:
            start=(16+number)*4
            address = int.from_bytes(vector[start:start+4],"little")
            assert address&1 and names.get(address&~1)==irq_name
            irq[irq_name]=dict(irq=number, thumb_address=hex(address))
        assert traces["AppTask_Device -> MagRotation_Step"]
        assert traces["EXTI2_IRQHandler -> PlatformTime_Us"]
    else:
        assert not any(re.search(r"\bs_rotation$|\bs_edge_us$",s) for s in nm.splitlines())
    sym=[line for line in nm.splitlines() if re.search(r"\b(?:s_rotation|s_edge_us|s_provider)$",line)]
    result=dict(model=case,configuration=config,elf_sha256=digest(elf),tools=GCC.as_posix(),
        scope="Exact linked symbol/IRQ evidence and representative direct paths. Each .su is one local frame. Missing indirect, archive, exception and preemption closure precludes a strict bound.",
        vectors=irq, persistent_symbols=sym, paths=traces, su_sha256=files,
        assembly_sha256=hashlib.sha256(dis.encode("utf8")).hexdigest())
    (HERE/"final-v2"/f"{case}-{config}-call-evidence.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")


if __name__ == "__main__":
    main(*sys.argv[1:])
