"""The operation journal is required by the selected augmented backend."""
import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve, SourceGraphError
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate

CODE = "AUGMENTED_OPERATION_JOURNAL_REQUIRES_SSLOG"


@pytest.mark.parametrize("algorithm", ["eskf20", "inekf15", "inekf20"])
def test_augmented_without_logging_rejects_before_plan_or_source_graph(tmp_path, builtin_catalog, algorithm):
    model = ReferenceProject_Create("JournalDependency", catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator." + algorithm
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    assert Project_Validate(model, builtin_catalog).valid
    model.protocols["logging"] = None
    before = model.Dictionary_Get()
    validation = Project_Validate(model, builtin_catalog)
    assert any(row.level == "error" and row.code == CODE for row in validation.issues)
    with pytest.raises(SourceGraphError, match=CODE):
        SourceGraph_Resolve(model, builtin_catalog)
    output = tmp_path / "not-generated"
    plan = ProjectAssembler(catalog=builtin_catalog, workspace_policy=WorkspacePolicy(tmp_path)).Plan(model, output)
    assert not plan.valid and plan.operations == ()
    assert not output.exists() and model.Dictionary_Get() == before


@pytest.mark.parametrize("algorithm", ["eskf20", "inekf15", "inekf20", "kf6"])
def test_supported_selection_retains_actual_logging_sources(builtin_catalog, algorithm):
    model = ReferenceProject_Create("JournalSources", catalog=builtin_catalog)
    model.strategies["estimator"] = "silverstar.algorithm.estimator." + algorithm
    model = ProjectConfiguration_Reconcile(model, builtin_catalog).model
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert Project_Validate(model, builtin_catalog).valid
    assert "Protocol/SSLOG/Inc" in graph.include_dirs
    assert "APP/Src/logger_bus.c" in graph.sources
    if algorithm != "kf6":
        assert "Algorithm/Estimator/Augmented/Src/navigation_journal.c" in graph.sources
    else:
        model.protocols["logging"] = None
        assert not any(row.code == CODE for row in Project_Validate(model, builtin_catalog).issues)
