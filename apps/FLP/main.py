from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def Application_Main() -> int:
    project_root = Path(__file__).resolve().parent
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        environment = os.environ.copy()
        environment["SILVERSTAR_FLP_VENV_REEXEC"] = "1"
        return subprocess.call(
            [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]], env=environment
        )

    source_root = project_root / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from silverstar_flp.app.application import main

    return int(main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(Application_Main())
