"""Describe this one FLP invocation; never merge retries or modify original outcomes."""
from collections import Counter
import argparse
from hashlib import sha256
import json
from pathlib import Path

TASK = Path(__file__).resolve().parent
ROOT = TASK.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tag', default='full')
tag = parser.parse_args().tag
rows = [json.loads(line) for line in (TASK / f"{tag}-1.jsonl").read_text(
    encoding="utf8").splitlines()]
collection = next(row["ids"] for row in rows if row["event"] == "collection")
states = {node: {} for node in collection}
for row in rows:
    if row["event"] == "phase":
        states[row["node"]][row["phase"]] = row


def outcome(phases):
    if any(phases.get(name, {}).get("result") == "failed"
           for name in ("setup", "teardown")):
        return "error"
    if phases.get("call", {}).get("result") == "failed":
        return "failed"
    if any(row["result"] == "skipped" for row in phases.values()):
        return "skipped"
    if all(phases.get(name, {}).get("result") == "passed"
           for name in ("setup", "call", "teardown")):
        return "passed"
    return "incomplete"


started = {row['node'] for row in rows if row['event'] == 'start'}
outcomes = {node: (outcome(phases) if node in started else 'untouched')
            for node, phases in states.items()}
outcomes = {node: ('interrupted' if status == 'incomplete' else status)
            for node, status in outcomes.items()}
counts = dict(Counter(outcomes.values()))
nonpasses = [{"node": node, "outcome": outcomes[node], "phases": phases}
             for node, phases in states.items() if outcomes[node] != "passed"]
inputs = json.loads((TASK / f"{tag}-inputs.json").read_text(encoding="utf8"))
integrity = {}
for group in ("source_files", "input_files"):
    changed = []
    for item in inputs[group]:
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            changed.append(item["path"])
    integrity[group] = {"checked": len(inputs[group]), "changed_or_missing": changed}
old = json.loads((TASK / "old-1953-causes.json").read_text(encoding="utf8"))
comparisons = [{**item, "current_outcome": outcomes.get(item["node"], "not_collected")}
               for item in old["nodes"]]
payload = dict(
    scope=__doc__, collected=len(collection), counts=counts,
    source_commit=inputs["source_commit"], source_and_input_integrity=integrity,
    qt_exception_file_exists=(TASK / f"{tag}-qt-exceptions.log").exists(),
    nonpasses=nonpasses,
    old_275_current_counts=dict(Counter(item["current_outcome"] for item in comparisons)),
    original_275_comparison=comparisons,
    runner_receipts=json.loads((TASK / f"{tag}-receipts.json").read_text(encoding="utf8")),
    files={name: sha256((TASK / name).read_bytes()).hexdigest()
           for name in (f"{tag}-1.log", f"{tag}-1.jsonl", f"{tag}-inputs.json", f"{tag}-environment.json")},
)
(TASK / f"{tag}-summary.json").write_text(json.dumps(payload, indent=2), encoding="utf8")
print(json.dumps({key: payload[key] for key in (
    "collected", "counts", "source_and_input_integrity", "old_275_current_counts")}, indent=2))
