"""Early exact emitted gates; analysis source epoch, not final acceptance."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("build_analysis", Path(__file__).with_name("build_candidates.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

if __name__ == "__main__":
    import subprocess
    import time
    output = Path(__file__).resolve().parent / "gates-a"
    output.mkdir(exist_ok=False)
    def Run(name):
        records = []
        project = build.WORK / "a" / name / "Flight_Controller"
        for target in ("architecture-check", "power10-check"):
            command = [str(build.HOST / "mingw32-make.exe"), "-C", str(project),
                       "CONFIG=Release", "GCC_PATH=" + str(build.GCC), target]
            started = time.monotonic()
            log = output / (name + "-" + target + ".log")
            with log.open("w", encoding="utf8") as stream:
                result = subprocess.run(command, env=build.environment, stdout=stream, stderr=subprocess.STDOUT)
            records.append({"name": name, "target": target, "command": command,
                            "exit_code": result.returncode, "seconds": time.monotonic() - started, "log": log.name})
            print(name, target, result.returncode, flush=True)
        return records
    records = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(Run, name) for name in ("f407", "installation", "h743", "pid", "lqr")]
        for future in as_completed(pending):
            records.extend(future.result())
            (output / "commands.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
