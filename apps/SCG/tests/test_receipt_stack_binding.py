"""Real compiler input tampering must remain a rejection after the v20 review."""

import ast
import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOL = (
    ROOT
    / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py"
)
EVIDENCE = ROOT / "docs/evidence/navigation_receipt_default_off_20261016"
NAMES = tuple(
    f"{family}_{mode}_{'default03' if family == 'eskf15' else 'default01'}"
    for family in ("eskf15", "kf6")
    for mode in (0, 1, 2)
)


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("receipt_stack_checker", TOOL)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    assert (
        result.BINDING_REVIEW_REVISION == "navigation_receipt_default_off_20261016_v20"
    )
    return result


def materialize(name, target, prefix="fixture"):
    source = (
        "Generated/Src/project_metadata.c"
        if prefix == "fixture_meta"
        else "System/Src/system_gnss_receipt.c"
    )
    selected = prefix + "/" + name + "/"
    with zipfile.ZipFile(EVIDENCE / "inputs.zip") as archive:
        for entry in archive.infolist():
            if entry.filename.startswith(selected):
                path = target / entry.filename.removeprefix(selected)
                assert path.resolve().is_relative_to(target.resolve())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(entry))
    build = target / "build"
    dependency = build / Path(source).with_suffix(".d")
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.write_bytes((target / "receipt.d").read_bytes())
    return source, build


@pytest.mark.parametrize("name", NAMES)
def test_actual_compiler_fixture_is_accepted(checker, tmp_path, name):
    source, build = materialize(name, tmp_path)
    (proof,) = checker.BindingSources_Verify(tmp_path, [source], build)
    assert proof["source"] == source and proof["compiled_input_sha256"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("kind", ("source", "header", "graph"))
def test_modified_complete_inputs_remain_rejected(checker, tmp_path, name, kind):
    source, build = materialize(name, tmp_path)
    if kind == "source":
        path = tmp_path / source
        path.write_bytes(
            path.read_bytes() + b"\n/* unreviewed complete-source change */\n"
        )
    elif kind == "header":
        path = tmp_path / "Generated/Inc/project_algorithm_parameters.h"
        path.write_bytes(
            path.read_bytes() + b"\n/* unreviewed included-header change */\n"
        )
    else:
        path = build / Path(source).with_suffix(".d")
        path.write_text(path.read_text().replace(source, "System/Src/unreviewed.c", 1))
    with pytest.raises(ValueError):
        checker.BindingSources_Verify(tmp_path, [source], build)


@pytest.mark.parametrize("name", NAMES)
def test_individually_known_header_cannot_be_mixed_with_another_source_tuple(
    checker, tmp_path, name
):
    source, build = materialize(name, tmp_path, "fixture_meta")
    family, mode, suffix = name.split("_", 2)
    other = f"{family}_{(int(mode) + 1) % 3}_{suffix}"
    header = "Generated/Inc/project_algorithm_parameters.h"
    with zipfile.ZipFile(EVIDENCE / "inputs.zip") as archive:
        different = archive.read("fixture_meta/" + other + "/" + header)
    path = tmp_path / header
    assert different != path.read_bytes()
    path.write_bytes(different)
    assert checker.BindingHeader_Verify(tmp_path, header)  # Known by itself.
    with pytest.raises(ValueError, match="paired source/compiler input closure"):
        checker.BindingSources_Verify(tmp_path, [source], build)


@pytest.mark.parametrize("name", NAMES[:3])
def test_active_header_is_outside_disabled_policy_review(checker, tmp_path, name):
    source, build = materialize(name, tmp_path)
    path = tmp_path / "Generated/Inc/project_algorithm_parameters.h"
    changed, count = re.subn(
        r"(\bSYSTEM_ESKF_GNSS_RECOVERY_ENABLED\s+)0\b", r"\g<1>1", path.read_text()
    )
    assert count == 1
    path.write_text(changed)
    with pytest.raises(ValueError):
        checker.BindingSources_Verify(tmp_path, [source], build)


def test_no_other_checker_AST_policy_changed_and_no_new_indirect_site_is_admitted():
    with zipfile.ZipFile(EVIDENCE / "inputs.zip") as archive:
        before = ast.parse(archive.read("review/checker_before_v20.py"))
        census = json.loads(archive.read("review/census.json"))
    after = ast.parse(TOOL.read_text(encoding="utf8"))
    assignments = {
        "BINDING_SOURCE_RECEIPT_V20",
        "BINDING_DEPENDENCIES_RECEIPT_V20",
        "BINDING_COMPILED_INPUTS_RECEIPT_V20",
        "BINDING_REVIEW_REVISION",
    }
    functions = {"BindingSourceVersions_Get", "BindingSources_Verify"}

    def preserved(tree):
        return [
            ast.dump(node, include_attributes=False)
            for node in tree.body
            if not (isinstance(node, ast.FunctionDef) and node.name in functions)
            and not (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id in assignments
                    for target in node.targets
                )
            )
        ]

    assert preserved(before) == preserved(after)
    assert all(
        not obj["indirect_sites"]
        for data in census["projects"].values()
        for obj in data["objects"].values()
    )
