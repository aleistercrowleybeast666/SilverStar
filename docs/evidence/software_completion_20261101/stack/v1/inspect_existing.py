"""Read frozen previous candidates without altering their outputs or evidence."""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[5]
EVIDENCE = Path(__file__).resolve().parent
TOOL = ROOT / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py"
spec = importlib.util.spec_from_file_location("stack_initial", TOOL)
stacks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stacks)
PREFIX = "D:/Arm GNU Toolchain/14.3 rel1/bin/arm-none-eabi-"
projects = {
    "f407": ".work/0.1.3-treediagram-20261101/silverstar/firmware-v1/f407/Flight_Controller",
    "h743": ".work/0.1.3-treediagram-20261101/h7-storage-v6/final/Flight_Controller",
}
records = {}
for name, relative in projects.items():
    project = ROOT / relative
    graph = stacks.StackGraph_Load(project, "Release", PREFIX)
    diagnostic = stacks.StackDiagnostic_Build(project, "Release", PREFIX)
    rejection = ""
    partial = None
    try:
        stacks.StackReport_Build(project, "Release", PREFIX)
    except Exception as error:
        rejection = str(error)
        trace = error.__traceback__
        while trace:
            if trace.tb_frame.f_code.co_name == "StackReport_Build":
                partial = trace.tb_frame.f_locals
            trace = trace.tb_next
    # Inspect the actual rejected call only. No acceptance check is bypassed.
    assembly = stacks.Command_Read([PREFIX+"objdump", "-d", str(graph["elf"])], project)
    names = re.findall(r"^[0-9a-f]+ <([^>]+)>:", assembly, re.MULTILINE)
    duplicate = {key:value for key,value in Counter(names).items() if value > 1}
    nm = graph["nm"]
    paths = {"main": "main", **{key:value[0] for key,value in stacks.TASKS.items()}}
    edges = partial["edges"] if partial else graph["edges"]
    indirect = partial["indirect"] if partial else graph["indirect"]
    def Reachable(entry):
        visited = set()
        pending = [entry]
        while pending:
            item = pending.pop()
            if item not in visited:
                visited.add(item)
                pending.extend(edges.get(item, ()))
        return visited
    remaining = {label: sorted(Reachable(entry) & indirect) for label,entry in paths.items()}
    record = {"candidate":relative,"analysis_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "checker_sha256":hashlib.sha256(TOOL.read_bytes()).hexdigest(),"strict_rejection":rejection,
        "diagnostic_only_not_acceptance":True,"diagnostic":diagnostic,
        "duplicate_disassembly_names":duplicate,"indirect_after_existing_binding_checks":sorted(indirect),
        "reachable_unresolved_indirect":remaining,"library_frames":graph["library_frames"],
        "unbounded_functions":sorted(graph["unbounded"]),
        "irq_functions":[key for key in graph["instructions"] if key.endswith(("_IRQHandler","_Handler"))],
        "stack_symbols":[line for line in nm.splitlines() if any(token in line for token in ("_estack", "_Min_Stack_Size", "_stack", "g_pfnVectors"))]}
    records[name] = record
    (EVIDENCE/(name+"-baseline.json")).write_text(json.dumps(record,indent=2)+"\n",encoding="utf8")
    print(name,rejection,"remaining",remaining,"duplicates",duplicate,flush=True)
(EVIDENCE/"baseline-summary.json").write_text(json.dumps({key:{
    field:record[field] for field in ("candidate","analysis_head","strict_rejection","reachable_unresolved_indirect","duplicate_disassembly_names")}
    for key,record in records.items()},indent=2)+"\n",encoding="utf8")
