"""Private static input derivation must preserve the original and fail closed."""
import importlib.util
import json
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools/validation/h743_static_validate.py"
spec = importlib.util.spec_from_file_location("h743_static_validate", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

CONFIG = """#define _USE_LFN 2
#define _FS_EXFAT 0
#define _FS_LOCK 2
#define _FS_REENTRANT 0
/* define the ff_malloc ff_free macros as standard malloc free */
#if !defined(ff_malloc) && !defined(ff_free)
#include <stdlib.h>
#define ff_malloc  malloc
#define ff_free  free
#endif
"""


def Input_Create(root, config=CONFIG):
    (root / "FATFS/Target").mkdir(parents=True)
    (root / "FATFS/Target/ffconf.h").write_text(config, encoding="utf8")
    (root / "Core/Src").mkdir(parents=True)
    (root / "Core/Src/main.c").write_text("/* original initialization */\n", encoding="utf8")
    (root / "fixture.ioc").write_text("Mcu.CPN=STM32H743ZIT6\n", encoding="utf8")
    return root


def test_static_derivative_changes_only_the_unused_aliases_and_keeps_source(tmp_path):
    source = Input_Create(tmp_path / "source")
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    output = tool.CubeMxStaticInput_Create(source, tmp_path / "private")
    assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert "ff_malloc" not in (output / "FATFS/Target/ffconf.h").read_text(encoding="utf8")
    assert (output / "Core/Src/main.c").read_bytes() == before[Path("Core/Src/main.c")]
    receipt = json.loads((tmp_path / "static-input-receipt.json").read_text(encoding="utf8"))
    assert receipt["changes"][0]["before_sha256"] != receipt["changes"][0]["after_sha256"]
    with pytest.raises(ValueError, match="already exist"):
        tool.CubeMxStaticInput_Create(source, output)


@pytest.mark.parametrize("old,new", [
    ("_USE_LFN 2", "_USE_LFN 3"),
    ("_FS_EXFAT 0", "_FS_EXFAT 1"),
    ("_FS_LOCK 2", "_FS_LOCK 1"),
    ("_FS_REENTRANT 0", "_FS_REENTRANT 1"),
    ("#define ff_free  free", "#define ff_free custom_free"),
    ("#define _USE_LFN 2", "#define _USE_LFN 2\n#define _USE_LFN 3"),
])
def test_unreviewed_or_heap_using_profile_is_rejected_before_copy(tmp_path, old, new):
    source = Input_Create(tmp_path / "source", CONFIG.replace(old, new))
    with pytest.raises(ValueError):
        tool.CubeMxStaticInput_Create(source, tmp_path / "private")
    assert not (tmp_path / "private").exists()
    assert (source / "FATFS/Target/ffconf.h").read_text(encoding="utf8") == CONFIG.replace(old, new)
