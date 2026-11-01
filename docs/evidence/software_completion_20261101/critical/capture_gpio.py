"""Retain actual compiled inputs and complete GPIO/generation regression logs."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[4]
TEMP = ROOT / ".work/0.1.3-software-completion-20261101/critical"
OUT = Path(__file__).resolve().parent / "gpio-capacity"
OUT.mkdir(parents=True, exist_ok=True)
records = []
for label in ("gpio-before-v2", "gpio-after-v2"):
    for receipt in sorted((TEMP / label).glob("*/compiler-receipt.json")):
        document = json.loads(receipt.read_text(encoding="utf8"))
        objects = {}
        for name, expected in document["sources"].items():
            source = Path(name)
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise RuntimeError("Compiled source changed: " + name)
            target = OUT / "objects" / (expected + source.suffix)
            target.parent.mkdir(exist_ok=True)
            if target.exists() and target.read_bytes() != content:
                raise RuntimeError("Conflicting retained source")
            target.write_bytes(content)
            objects[name] = target.relative_to(OUT).as_posix()
        destination = OUT / label / receipt.parent.name
        destination.mkdir(parents=True, exist_ok=True)
        for name in ("compiler-receipt.json", "command.json", "compile.log", "run.log"):
            (destination / name).write_bytes((receipt.parent / name).read_bytes())
        executable = receipt.parent / "gpio.exe"
        records.append({"label": label, "receipt": (destination / receipt.name).relative_to(OUT).as_posix(),
                        "objects": objects, "executable": str(executable),
                        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()})
for label in ("gpio-before-v1", "gpio-after-v1", "gpio-before-v2", "gpio-after-v2",
              "architecture-after-v1", "ownership-after-v2", "ownership-after-v3"):
    for suffix in (".log", ".exit"):
        path = TEMP / (label + suffix)
        (OUT / path.name).write_bytes(path.read_bytes())
(OUT / "index.json").write_text(json.dumps({"compilations": records,
    "baseline": "8b028f280ba01dce0efc697479ef99ec143f7456",
    "scope": "Host modeled GPIO/IRQ boundary and generator ownership only; actual ARM/MSP acceptance is separate"},
    indent=2) + "\n", encoding="utf8")
print("Retained", len(records), "actual GCC analyzer compilations and complete regression logs")
