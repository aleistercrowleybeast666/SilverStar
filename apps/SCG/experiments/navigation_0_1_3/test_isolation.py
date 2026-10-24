"""Read-only SCG metadata boundaries; never compile or execute device payloads."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from silverstar_fccg.plugins.catalog import PluginCatalog, PluginCatalogError
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve

HERE = Path(__file__).resolve().parent
SCG = HERE.parents[1]
FORBIDDEN_IDS = ("silverstar.algorithm.estimator.inekf",
                 "silverstar.algorithm.estimator.iekf",
                 "silverstar.algorithm.estimator.iekf15",
                 "silverstar.algorithm.estimator.iekf20")
PROMOTED_MODELS = ("eskf20", "inekf15", "inekf20")


@pytest.fixture(scope="module")
def catalog():
    value = PluginCatalog(SCG / "plugins/builtin", SCG / "plugins/installed")
    value.Scan()
    return value


def MetadataModel_Create(catalog):
    # The official reference constructor reads declarative manifests only.
    # Remove ALL devices before graph/validation calls; no GNSS adapter is run.
    model = ReferenceProject_Create("InEkfIsolationMetadata", catalog=catalog)
    model.device_instances = []
    model.resource_assignments = {}
    model.capability_source_overrides = {}
    model.protocols = {key: None for key in model.protocols}
    model.logging_streams = []
    model.strategies["estimator"] = None
    return model


def test_experiment_is_outside_discovery_and_has_no_registration(catalog):
    assert not tuple(HERE.rglob("plugin.json"))
    for root in (catalog.builtin_root, catalog.installed_root):
        assert not HERE.is_relative_to(root)
    for manifest in catalog.All_Get():
        assert not manifest.manifest_path.resolve().is_relative_to(HERE)
        assert manifest.component_id not in FORBIDDEN_IDS
    assert not set(FORBIDDEN_IDS).intersection(
        item.component_id for item in catalog.SelectionSlot_Get("estimator"))


@pytest.mark.parametrize("component_id", FORBIDDEN_IDS)
def test_manually_entered_id_is_rejected_by_catalog_validation_and_graph(catalog, component_id):
    with pytest.raises(PluginCatalogError, match="Unknown component"):
        catalog.Component_Get(component_id)
    model = MetadataModel_Create(catalog)
    model.strategies["estimator"] = component_id
    # Validation may fail earlier in dependency resolution; both paths must
    # explicitly identify the unknown component, not pass for unrelated errors.
    try:
        result = Project_Validate(model, catalog)
    except PluginCatalogError as error:
        assert component_id in str(error)
    else:
        assert not result.valid
        assert any(component_id in issue.message and issue.severity == "error"
                   for issue in result.issues)
    with pytest.raises(PluginCatalogError, match="Unknown component"):
        SourceGraph_Resolve(model, catalog)


@pytest.mark.parametrize("estimator", [None, "sf6", "kf6", "eskf15"])
def test_existing_source_graphs_have_no_experimental_sources(catalog, estimator):
    model = MetadataModel_Create(catalog)
    if estimator:
        model.strategies["estimator"] = "silverstar.algorithm.estimator." + estimator
    graph = SourceGraph_Resolve(deepcopy(model), catalog)
    assert graph.sources  # Exercise real production graph construction.
    assert not any("/GNSS/" in source for source in graph.sources)
    for path in (*graph.sources, *graph.include_dirs, *graph.virtual_sources):
        assert "experiments" not in path.casefold()
        assert "inekf" not in path.casefold() and "eskf20" not in path.casefold()
    if estimator:
        assert any(f"Estimator/{estimator.upper()}/" in source for source in graph.sources)


@pytest.mark.parametrize("model_id", PROMOTED_MODELS)
def test_promoted_models_use_owned_sources_and_keep_validation_only_metadata(catalog, model_id):
    component_id = "silverstar.algorithm.estimator." + model_id
    manifest = catalog.Component_Get(component_id)
    raw = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    assert raw["metadata"]["qualified_timing_profiles"] == []
    assert raw["metadata"]["software_validation_parameter"] == "software_validation_build"
    parameters = {item["id"]: item for item in raw["algorithm_parameters"]["parameters"]}
    assert parameters["software_validation_build"]["default"] == 1
    model = MetadataModel_Create(catalog)
    model.strategies["estimator"] = component_id
    model = ProjectConfiguration_Reconcile(model, catalog).model
    graph = SourceGraph_Resolve(model, catalog)
    assert any("Estimator/Augmented/Src/navigation_augmented_backend.c" in path
               for path in graph.sources)
    assert not any("experiments" in path.casefold() for path in graph.sources)
