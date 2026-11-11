"""Read-only inventory of explicitly owned FLP test directories; never follow links."""
from collections import Counter
import json
import os
from pathlib import Path
import stat

TASK = Path(__file__).resolve().parent
REPO = TASK.parents[2]
owner = json.loads((TASK / "ownership.json").read_text(encoding="utf8"))
results = []
for name in owner["scratch_roots"]:
    root = Path(name)
    assert root.parent.resolve() == (REPO / ".work").resolve()
    row = {"root": str(root), "files": 0, "bytes": 0,
           "excluded": [], "suffixes": {}, "children": {}}
    if not root.exists():
        row["absent"] = True
        results.append(row)
        continue
    pending = [root]
    suffixes, children = {}, {}
    while pending:
        folder = pending.pop()
        info = folder.lstat()
        assert not info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        with os.scandir(folder) as entries:
            for entry in entries:
                path = Path(entry.path)
                data = path.lstat()
                relative = path.relative_to(root).as_posix()
                if data.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    row["excluded"].append({"path": relative, "reason": "reparse point: not followed"})
                elif stat.S_ISDIR(data.st_mode):
                    if entry.name == ".git":
                        row["excluded"].append({"path": relative, "reason": "nested repository metadata: retained"})
                    else:
                        pending.append(path)
                elif stat.S_ISREG(data.st_mode):
                    row["files"] += 1
                    row["bytes"] += data.st_size
                    suffix = path.suffix.casefold() or "[none]"
                    suffixes.setdefault(suffix, Counter()).update(files=1, bytes=data.st_size)
                    parts = path.relative_to(root).parts
                    child = "/".join(parts[:2]) if parts[0] == "0" else parts[0]
                    children.setdefault(child, Counter()).update(files=1, bytes=data.st_size)
                else:
                    row["excluded"].append({"path": relative, "reason": "nonregular path retained"})
    row["suffixes"] = dict(sorted(suffixes.items(), key=lambda pair: -pair[1]["bytes"]))
    row["children"] = dict(sorted(children.items(), key=lambda pair: -pair[1]["bytes"]))
    results.append(row)
(TASK / "owned-scratch-inventory.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
for row in results:
    print(json.dumps({key: row[key] for key in ("root", "files", "bytes", "excluded")}))
print("total", sum(row["files"] for row in results), sum(row["bytes"] for row in results))
