"""Process-model identity is independent of parameters and GNSS policy."""
from dataclasses import replace

import numpy as np
import pytest

from silverstar_flp.core.analysis_source import ReplayResultStore
from silverstar_flp.core.project import Project_Load, Project_Save, ReplayConfiguration_Validate
from silverstar_flp.decoder_profiles import (
    DecoderProfileError,
    DecoderProfileMatcher,
    DecoderProfilePackage,
)
from silverstar_flp.decoder_profiles.kf6_revision import (
    COMPONENT,
    KERNEL_PATHS,
    MODELS,
    Kf6Revision_FromSemantics,
)
from silverstar_flp.plugins.algorithms.kf6.plugin import Kf6AlgorithmPlugin
from silverstar_flp.plugins.api.algorithm import ReplayMode, ReplayRequest
from tests.sslog_synthetic import START_TIMESTAMP_US, SyntheticSslogBuilder
from tests.test_decoder_profiles import (
    _ContainerMap_Get,
    _DescriptorPayload_Build,
    _Package_Write,
    _PackageFiles_Build,
    _SemanticsDocument_Build,
)
from tests.test_project_export import _ProjectDocument_Build


def Semantics_Build(revision=1):
    document = _SemanticsDocument_Build()
    document["component_locks"] = [{"component": COMPONENT, "version": "0.1.0" if revision == 1 else "0.2.0", "manifest_sha256": "a" * 64}]
    if revision == 2:
        document["metadata_declarations"] = {"kf6": {"revision": 2, "process_noise_model": MODELS[2], "kernel_sha256": {path: "b" * 64 for path in KERNEL_PATHS}}}
    return document


def test_optional_identity_allows_raw_exact_pair_but_denies_recorded_math(tmp_path):
    document = _SemanticsDocument_Build()
    files, hashes = _PackageFiles_Build(semantics_document=document)
    path, _ = _Package_Write(tmp_path / "raw_unknown.ssdecoder", files=files)
    package = DecoderProfilePackage.Load(path, container_plugins=_ContainerMap_Get())
    assert Kf6Revision_FromSemantics(package.semantics.raw_metadata) is None
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US)
    log = builder.File_Write(tmp_path / "raw_unknown.sslog")
    assert len(DecoderProfileMatcher(_ContainerMap_Get()).Match(log, [path]).matches) == 1
    from tests.synthetic_parameter_navigation import NavigationPair_Open
    dataset = NavigationPair_Open(tmp_path / "navigation", flight_samples=21).dataset
    metadata = dict(dataset.semantic_context.raw_metadata)
    metadata.pop("component_locks", None)
    metadata.pop("metadata_declarations", None)
    dataset = replace(dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata))
    plugin = Kf6AlgorithmPlugin()
    with pytest.raises(ValueError, match="kf6_algorithm_revision_missing"):
        plugin.run(dataset, ReplayRequest())
    with pytest.raises(ValueError, match="kf6_algorithm_revision_missing"):
        plugin.ProcessModelRevision_Resolve(dataset, ReplayRequest(mode=ReplayMode.OFFLINE))
    assert plugin.ProcessModelRevision_Resolve(dataset, ReplayRequest(mode=ReplayMode.WHAT_IF, process_model_revision=2)) == 2


@pytest.mark.parametrize("edit", [
    lambda s: s["metadata_declarations"].update(kf6=None),
    lambda s: s["metadata_declarations"].update(kf6=[]),
    lambda s: s.update(component_locks=["bad"]),
    lambda s: s["component_locks"][0].update(version=[]),
    lambda s: s["metadata_declarations"]["kf6"].update(revision=True),
    lambda s: s["metadata_declarations"]["kf6"].update(kernel_sha256="bad"),
    lambda s: s["metadata_declarations"]["kf6"].pop("kernel_sha256"),
    lambda s: s["metadata_declarations"]["kf6"].update(revision=1),
    lambda s: s["metadata_declarations"]["kf6"].update(process_noise_model=MODELS[1]),
])
def test_malformed_identity_is_decoder_error_and_discovery_continues(tmp_path, edit):
    bad = Semantics_Build(2)
    edit(bad)
    files, _ = _PackageFiles_Build(semantics_document=bad)
    bad_path, _ = _Package_Write(tmp_path / "bad.ssdecoder", files=files)
    with pytest.raises(DecoderProfileError):
        DecoderProfilePackage.Load(bad_path, container_plugins=_ContainerMap_Get())
    files, hashes = _PackageFiles_Build(semantics_document=Semantics_Build())
    good_path, _ = _Package_Write(tmp_path / "good.ssdecoder", files=files)
    builder = SyntheticSslogBuilder()
    builder.Record_Add(0x1D, _DescriptorPayload_Build(hashes), START_TIMESTAMP_US)
    log = builder.File_Write(tmp_path / "matching.sslog")
    matches = DecoderProfileMatcher(_ContainerMap_Get()).Match(log, [bad_path, good_path])
    assert len(matches.matches) == 1 and len(matches.errors) == 1


def test_explicit_legacy_model_conflict_without_revision_is_rejected():
    document = Semantics_Build()
    document["metadata_declarations"] = {"kf6": {"process_noise_model": MODELS[2]}}
    with pytest.raises(DecoderProfileError, match="kf6_process_noise_model_mismatch"):
        Kf6Revision_FromSemantics(document)
    assert Kf6Revision_FromSemantics(Semantics_Build()) == 1
    assert Kf6Revision_FromSemantics(Semantics_Build(2)) == 2


def test_selected_what_if_survives_project_roundtrip_and_result_identity(tmp_path):
    from tests.synthetic_parameter_navigation import NavigationPair_Open
    # Resolve the model difference above float32 roundoff in a short fixture.
    overrides = {"kf6": {"process_accel_std_e": 20, "process_accel_std_n": 20,
                         "process_accel_std_u": 20}}
    dataset = NavigationPair_Open(tmp_path / "navigation", overrides, flight_samples=21).dataset
    metadata = dict(dataset.semantic_context.raw_metadata)
    metadata["component_locks"] = [dict(lock) for lock in metadata["component_locks"]]
    for lock in metadata["component_locks"]:
        if lock["component"] == COMPONENT:
            lock["version"] = "0.1.0"
    dataset = replace(dataset, semantic_context=replace(dataset.semantic_context, raw_metadata=metadata))
    plugin = Kf6AlgorithmPlugin()
    recorded = plugin.run(dataset, ReplayRequest())
    request = ReplayRequest(mode=ReplayMode.WHAT_IF, process_model_revision=2)
    upgraded = plugin.run(dataset, request)
    assert recorded.diagnostics["process_model_revision"] == 1
    assert upgraded.diagnostics["process_model_revision"] == 2
    assert not np.array_equal(recorded.channels["kf6.covariance.diagonal"].values, upgraded.channels["kf6.covariance.diagonal"].values)
    path = tmp_path / "selected.ssflp"
    project = _ProjectDocument_Build(dataset.source_path, path)
    project.replay_configurations["selected"] = {
        "algorithm_id": upgraded.algorithm_id, "algorithm_version": upgraded.algorithm_version,
        "mode": request.mode.value, "input_source": request.input_source,
        "actual_values": dict(upgraded.parameters), "parameter_schema_identity": plugin.metadata.ParameterSchemaIdentity_Get(),
        "provenance": upgraded.diagnostics["config_source"], "process_model_revision": upgraded.diagnostics["process_model_revision"],
    }
    Project_Save(project, path)
    configuration = Project_Load(path).replay_configurations["selected"]
    restored = plugin.run(dataset, ReplayRequest(mode=configuration["mode"], input_source=configuration["input_source"], parameters=configuration["actual_values"], process_model_revision=configuration["process_model_revision"]))
    for name in upgraded.channels:
        np.testing.assert_array_equal(upgraded.channels[name].values, restored.channels[name].values)
    store = ReplayResultStore()
    first = store.Result_Add(recorded, algorithm_name="KF6")
    second = store.Result_Add(upgraded, algorithm_name="KF6")
    assert first.source_id != second.source_id and first.result_id != second.result_id
    assert first.diagnostics["process_model_revision"] != second.diagnostics["process_model_revision"]
    old = dict(configuration)
    old.pop("process_model_revision")
    ReplayConfiguration_Validate(old)
    assert plugin.ProcessModelRevision_Resolve(dataset, ReplayRequest(mode=old["mode"])) == 1
    with pytest.raises(ValueError, match="explicit_what_if"):
        plugin.ProcessModelRevision_Resolve(dataset, ReplayRequest(process_model_revision=2))
    with pytest.raises(ValueError, match="override_conflict"):
        plugin.run(dataset, request, analysis_algorithm_revision=1)


@pytest.mark.parametrize("value", [None, True, 0, 3, "2"])
def test_project_rejects_invalid_present_revision(tmp_path, value):
    plugin = Kf6AlgorithmPlugin()
    configuration = {"algorithm_id": plugin.metadata.plugin_id, "algorithm_version": plugin.metadata.version,
        "mode": "what_if", "input_source": "corrected_imu", "actual_values": dict(plugin.OfflineParameters_Get()),
        "parameter_schema_identity": plugin.metadata.ParameterSchemaIdentity_Get(), "provenance": "Algorithm Plugin actual defaults", "process_model_revision": value}
    with pytest.raises(ValueError, match="project_process_model_revision_invalid"):
        ReplayConfiguration_Validate(configuration)


def test_replay_page_restores_hidden_revision_without_a_new_selector(tmp_path):
    from PySide6.QtWidgets import QApplication

    from silverstar_flp.core.i18n import Translator
    from silverstar_flp.plugins.registry import builtin_registry
    from silverstar_flp.ui.pages.replay import ReplayPage
    from tests.synthetic_parameter_navigation import NavigationPair_Open
    application = QApplication.instance() or QApplication([])
    dataset = NavigationPair_Open(tmp_path / "page", flight_samples=3).dataset
    plugin = Kf6AlgorithmPlugin()
    page = ReplayPage(Translator("en_US"), builtin_registry())
    page.Dataset_Set(dataset)
    configuration = {"algorithm_id": plugin.metadata.plugin_id, "algorithm_version": plugin.metadata.version,
        "mode": "what_if", "input_source": "corrected_imu", "actual_values": dict(plugin.recorded_parameters(dataset)),
        "parameter_schema_identity": plugin.metadata.ParameterSchemaIdentity_Get(),
        "provenance": "Firmware build configuration from .ssdecoder", "process_model_revision": 2}
    page.Configuration_Set(configuration)
    assert page._Request_Get().process_model_revision == 2
    assert page.Configuration_Get()["process_model_revision"] == 2
    page.Dataset_Set(dataset)
    assert page._Request_Get().process_model_revision == 2
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(ReplayMode.OFFLINE))
    assert page._Request_Get().process_model_revision is None
    page.Dataset_Set(replace(dataset, source_path=tmp_path / "another_source.BIN"))
    assert page._process_model_preferences == {}
    page.deleteLater()
    application.processEvents()
