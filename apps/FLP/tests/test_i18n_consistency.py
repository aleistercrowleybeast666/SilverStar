"""Keep product catalogs complete for statically referenced labels."""
from __future__ import annotations

import ast
import json
from pathlib import Path


def test_catalogs_match_and_literal_translation_calls_resolve() -> None:
    root = Path(__file__).resolve().parents[1]
    catalog_dir = root / "src" / "silverstar_flp" / "i18n"
    english = json.loads((catalog_dir / "en_US.json").read_text(encoding="utf-8"))
    chinese = json.loads((catalog_dir / "zh_CN.json").read_text(encoding="utf-8"))
    assert english.keys() == chinese.keys()

    missing = set()
    for path in (root / "src" / "silverstar_flp").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            direct = isinstance(node.func, ast.Attribute) and node.func.attr == "Text_Get"
            plot_label = (isinstance(node.func, ast.Name) and node.func.id == "label"
                          and path.name in {"gnss_integrity.py", "service.py"})
            if not direct and not plot_label:
                continue
            argument = node.args[0]
            if (isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                    and argument.value not in english):
                missing.add((path.relative_to(root).as_posix(), argument.value))
    assert not missing


def test_retired_diagnostic_product_paths_are_absent() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "silverstar_flp"
    for relative in (
        "analysis/integrity_assistance.py",
        "analysis/gnss_integrity.py",
        "ui/offline_diagnostics.py",
    ):
        assert not (root / relative).exists()
    ui = "\n".join(path.read_text(encoding="utf-8") for path in (root / "ui").rglob("*.py"))
    for retired in (
        "integrity_assisted", "recomputeRequested", "_LandingReplay_Start",
        "Recomputed_Set", "Advanced Offline Diagnostics",
    ):
        assert retired not in ui
