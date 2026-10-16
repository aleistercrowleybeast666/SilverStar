"""Exact actual compiler fixtures: no successful report or local project teaches admission."""

import ast
import importlib.util
import json
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/navigation_horizon_stack_binding_20261016"
TOOL = (
    ROOT
    / "apps/SCG/plugins/builtin/silverstar_core_0_1_0/payload/Tools/check_task_stacks.py"
)
spec = importlib.util.spec_from_file_location("horizon_stack_binding", TOOL)
stacks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stacks)
SOURCE = "APP/Src/estimator_bus.c"
PROJECTS = ("kf6_2_native03", "eskf15_2_native02")


@pytest.fixture(params=PROJECTS)
def actual_compiler_inputs(request, tmp_path):
    manifest = json.loads((EVIDENCE / "inputs_unique.json").read_text(encoding="utf8"))
    archive_path = EVIDENCE / "inputs_unique.zip"
    assert sha256(archive_path.read_bytes()).hexdigest() == manifest["archive_sha256"]
    prefix = "compiler_fixture/" + request.param + "/"
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            if not name.startswith(prefix):
                continue
            raw = archive.read(name)
            assert sha256(raw).hexdigest() == manifest["entries"][name]
            relative = name.removeprefix(prefix)
            target = tmp_path / relative
            target.resolve().relative_to(tmp_path.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    build = tmp_path / "build"
    dependency = build / Path(SOURCE).with_suffix(".d")
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes((tmp_path / "estimator_bus.d").read_bytes())
    return tmp_path, build, request.param


def test_exact_actual_mode2_compiler_input_tuple_is_admitted(actual_compiler_inputs):
    root, build, _ = actual_compiler_inputs
    (proof,) = stacks.BindingSources_Verify(root, [SOURCE], build)
    assert proof["source"] == SOURCE
    assert (
        proof["compiled_input_sha256"]
        in stacks.BINDING_COMPILED_INPUTS_HORIZON_V19[SOURCE]
    )


@pytest.mark.parametrize(
    "mutation", ["missing_header", "changed_header", "added_input", "changed_source"]
)
def test_mode2_input_mutation_remains_fail_closed(actual_compiler_inputs, mutation):
    root, build, _ = actual_compiler_inputs
    header = root / "Generated/Inc/project_flight_config.h"
    if mutation == "missing_header":
        header.unlink()  # Deliberate fault in this test-owned copy only.
    elif mutation == "changed_header":
        header.write_bytes(header.read_bytes() + b"\n#define UNREVIEWED_BOUNDARY 1\n")
    elif mutation == "changed_source":
        source = root / SOURCE
        source.write_bytes(source.read_bytes() + b"\nvoid Changed_Binding(void) {}\n")
    else:
        (root / "unexpected.inc").write_text("/* fault input */\n", encoding="utf8")
        dependency = build / Path(SOURCE).with_suffix(".d")
        text = dependency.read_text(encoding="utf8")
        first, rest = text.split(":", 1)
        dependency.write_text(first + ": unexpected.inc " + rest, encoding="utf8")
    with pytest.raises(ValueError):
        stacks.BindingSources_Verify(root, [SOURCE], build)


@pytest.mark.parametrize(
    "replacement", ["legacy_approved", "other_algorithm_with_legacy_config"]
)
def test_individually_reviewed_inputs_cannot_form_unreviewed_mode2_tuple(
    actual_compiler_inputs, replacement
):
    root, build, project = actual_compiler_inputs
    relative = "Generated/Inc/project_flight_config.h"
    with zipfile.ZipFile(EVIDENCE / "inputs_unique.zip") as archive:
        if replacement == "legacy_approved":
            raw = archive.read("legacy/compiler_fixture/" + relative)
        else:
            other = next(name for name in PROJECTS if name != project)
            # Swapping the sole differing bus header would reproduce the other
            # complete approved bus tuple. Mix an independently approved legacy
            # configuration too, so this negative case is actually unreviewed.
            config = root / "Generated/Inc/project_flight_config.h"
            config.write_bytes(
                archive.read(
                    "legacy/compiler_fixture/Generated/Inc/project_flight_config.h"
                )
            )
            assert stacks.BindingSourceHash_Get(
                config.read_text(encoding="utf8")
            ) in stacks.BindingSourceVersions_Get(
                "Generated/Inc/project_flight_config.h"
            )
            relative = "Generated/Inc/project_algorithm_parameters.h"
            raw = archive.read("compiler_fixture/" + other + "/" + relative)
    target = root / relative
    assert raw != target.read_bytes()
    target.write_bytes(raw)
    assert stacks.BindingSourceHash_Get(
        target.read_text(encoding="utf8")
    ) in stacks.BindingSourceVersions_Get(relative)
    dependencies = (
        (build / Path(SOURCE).with_suffix(".d"))
        .read_text(encoding="utf8")
        .split(":", 1)[1]
        .replace("\\\n", " ")
        .split("\n", 1)[0]
        .split()
    )
    inputs = [
        [path, stacks.BindingSourceHash_Get((root / path).read_text(encoding="utf8"))]
        for path in dependencies
    ]
    closure = stacks.BindingClosureHash_Get(
        SOURCE,
        stacks.BindingSourceHash_Get((root / SOURCE).read_text(encoding="utf8")),
        inputs,
    )
    assert closure not in (
        stacks.BINDING_COMPILED_INPUTS_ALGORITHM_TIMING_V18.get(SOURCE, [])
        + stacks.BINDING_COMPILED_INPUTS_HORIZON_V19.get(SOURCE, [])
    )
    with pytest.raises(ValueError, match="paired source/compiler input closure"):
        stacks.BindingSources_Verify(root, [SOURCE], build)


def test_stack_algorithm_and_all_nonbinding_policies_are_preserved():
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf8"))
    assert manifest["all_nonbinding_policy_assignments_AST_equal"]
    assert manifest["changed_registration_functions"] == [
        "BindingSourceVersions_Get",
        "BindingSources_Verify",
    ]
    assert "StackReport_Build" in manifest["unchanged_functions"]
    with zipfile.ZipFile(EVIDENCE / "inputs_unique.zip") as archive:
        before = ast.parse(archive.read("review/checker_before_v19.py"))
    after = ast.parse(TOOL.read_text(encoding="utf8"))
    functions = lambda tree: {
        node.name: ast.dump(node, include_attributes=False)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    old_functions, new_functions = functions(before), functions(after)
    assert old_functions.keys() == new_functions.keys()
    for name in manifest["unchanged_functions"]:
        assert old_functions[name] == new_functions[name], name
    policies = lambda tree: [
        ast.dump(node, include_attributes=False)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and all(
            isinstance(target, ast.Name) and not target.id.startswith("BINDING_")
            for target in node.targets
        )
    ]
    assert policies(before) == policies(after)
