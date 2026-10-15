"""Declaration admission and unavailable replay, without activating firmware modes."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from silverstar_flp.decoder_profiles import DecoderProfileError, DecoderProfilePackage
from silverstar_flp.decoder_profiles.fusion_timing import (
    FusionTiming_FromSemantics,
    FusionTimingUnavailable_Get,
    LEGACY_VERSIONS,
    SCHEMA_ID,
)
from silverstar_flp.plugins.api.algorithm import ReplayFidelity, ReplayMode, ReplayRequest
from silverstar_flp.plugins.registry import builtin_registry
from tests.test_decoder_profiles import (
    _ContainerMap_Get, _Package_Write, _PackageFiles_Build, _SemanticsDocument_Build,
)

KF6 = "silverstar.algorithm.estimator.kf6"
ESKF15 = "silverstar.algorithm.estimator.eskf15"


def _Declaration(component=KF6, mode=0):
    return {
        "schema_id": SCHEMA_ID, "revision": 1, "component": component, "mode": mode,
        "source_time": "resolved_measurement_epoch",
        "application_time": "estimator_present" if mode == 0 else "legacy_algorithm_epoch",
        "evaluation_time": "estimator_present", "output_state_time": "estimator_present",
        "output_covariance_time": "estimator_present", "replays_history": mode == 1,
    }


def _Document(component=KF6, version="99.0.0", mode=0):
    document = _SemanticsDocument_Build()
    document["algorithms"] = [component]
    document["component_locks"] = [{"component": component, "version": version}]
    document["firmware_algorithm_parameters"] = []
    document["metadata_declarations"] = {"fusion_timing": _Declaration(component, mode)}
    return document


def _Package_Load(tmp_path, document):
    files, _ = _PackageFiles_Build(semantics_document=document)
    path, _ = _Package_Write(tmp_path / "timing.ssdecoder", files=files)
    before = path.read_bytes()
    result = DecoderProfilePackage.Load(path, container_plugins=_ContainerMap_Get())
    assert path.read_bytes() == before
    return result


@pytest.mark.parametrize("component,version", [(key, value) for key, values in LEGACY_VERSIONS.items() for value in sorted(values)])
def test_missing_declaration_resolves_only_known_legacy_version(component, version):
    document = _Document(component, version)
    document["metadata_declarations"] = {}
    before = deepcopy(document)
    identity = FusionTiming_FromSemantics(document)
    assert (identity.mode, identity.revision, identity.evidence) == (1, 0, "legacy_component_lock")
    assert not identity.unavailable_reason
    assert document == before


@pytest.mark.parametrize("version", [None, "99.0.0", "0.2.1-dirty"])
def test_unknown_or_absent_version_never_inherits_replay_default(version):
    document = _Document(version=version)
    document["metadata_declarations"] = {}
    if version is None:
        document.pop("component_locks")
    identity = FusionTiming_FromSemantics(document)
    assert identity.mode is identity.revision is None
    assert identity.unavailable_reason == "fusion_timing_identity_unproven"


@pytest.mark.parametrize("component", [KF6, ESKF15])
def test_current_declaration_preserves_raw_package_and_is_unavailable(tmp_path, component):
    document = _Document(component)
    _Package_Load(tmp_path, document)
    identity = FusionTiming_FromSemantics(document)
    assert identity.mode == 0 and identity.revision == 1
    dataset = SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=document))
    assert FusionTimingUnavailable_Get(dataset) == ("fusion_timing_current_replay_not_implemented",)


@pytest.mark.parametrize("mutation,reason", [
    (lambda d: d.update(mode=True), "mode_unsupported"),
    (lambda d: d.update(mode=2), "mode_unsupported"),
    (lambda d: d.update(mode="0"), "mode_unsupported"),
    (lambda d: d.update(revision=True), "revision_unsupported"),
    (lambda d: d.update(revision=2), "revision_unsupported"),
    (lambda d: d.update(schema_id="unknown"), "revision_unsupported"),
    (lambda d: d.update(component=ESKF15), "component_mismatch"),
    (lambda d: d.update(application_time="resolved_measurement_epoch"), "timestamp_contract_mismatch"),
    (lambda d: d.update(source_time="estimator_present"), "timestamp_contract_mismatch"),
    (lambda d: d.update(output_covariance_time="source"), "timestamp_contract_mismatch"),
    (lambda d: d.update(replays_history=0), "history_contract_mismatch"),
    (lambda d: d.update(replays_history=True), "history_contract_mismatch"),
    (lambda d: d.update(extra="ignored"), "declaration_invalid"),
    (lambda d: d.pop("mode"), "declaration_invalid"),
])
def test_invalid_declaration_rejected_at_package_boundary(tmp_path, mutation, reason):
    document = _Document()
    mutation(document["metadata_declarations"]["fusion_timing"])
    with pytest.raises(DecoderProfileError, match="fusion_timing_" + reason):
        _Package_Load(tmp_path, document)


@pytest.mark.parametrize("component", [KF6, ESKF15])
def test_legacy_component_cannot_claim_current_mode(tmp_path, component):
    document = _Document(component, sorted(LEGACY_VERSIONS[component])[-1])
    with pytest.raises(DecoderProfileError, match="fusion_timing_legacy_component_mismatch"):
        _Package_Load(tmp_path, document)


def test_replay_declaration_does_not_certify_an_unknown_implementation():
    identity = FusionTiming_FromSemantics(_Document(mode=1))
    assert identity.mode == 1
    assert identity.unavailable_reason == "fusion_timing_identity_unproven"


@pytest.mark.parametrize("component", ["silverstar.algorithm.estimator.sf6", "silverstar.algorithm.ins.coning2_sculling2"])
def test_non_replay_algorithms_cannot_own_timing_declaration(tmp_path, component):
    document = _Document(component)
    with pytest.raises(DecoderProfileError, match="fusion_timing_owner_invalid"):
        _Package_Load(tmp_path, document)
    document["metadata_declarations"] = {}
    assert FusionTiming_FromSemantics(document) is None


def test_ambiguous_owners_and_component_locks_reject():
    document = _Document()
    document["algorithms"].append(ESKF15)
    with pytest.raises(DecoderProfileError, match="owner_ambiguous"):
        FusionTiming_FromSemantics(document)
    document = _Document()
    document["component_locks"] *= 2
    with pytest.raises(DecoderProfileError, match="identity_ambiguous"):
        FusionTiming_FromSemantics(document)


def test_old_multi_estimator_package_remains_readable_without_inferred_timing(tmp_path):
    document = _Document()
    document["algorithms"].append(ESKF15)
    document["metadata_declarations"] = {}
    before = deepcopy(document)
    _Package_Load(tmp_path, document)
    identity = FusionTiming_FromSemantics(document)
    assert identity.mode is identity.revision is None
    assert identity.unavailable_reason == "fusion_timing_identity_unproven"
    dataset = SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=document))
    assert FusionTimingUnavailable_Get(dataset) == ()
    assert document == before


def test_old_unknown_version_keeps_existing_numerical_admission_authority():
    document = _Document(version="0.0.10")
    document["metadata_declarations"] = {}
    identity = FusionTiming_FromSemantics(document)
    assert identity.mode is None
    assert identity.unavailable_reason == "fusion_timing_identity_unproven"
    dataset = SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=document))
    assert FusionTimingUnavailable_Get(dataset) == ()


def test_context_without_timing_metadata_keeps_legacy_admission_authority():
    dataset = SimpleNamespace(semantic_context=SimpleNamespace())
    assert FusionTimingUnavailable_Get(dataset) == ()


@pytest.mark.parametrize("document", [None, [], "invalid"])
def test_present_non_mapping_metadata_is_an_explicit_blocker(document):
    dataset = SimpleNamespace(semantic_context=SimpleNamespace(raw_metadata=document))
    assert FusionTimingUnavailable_Get(dataset) == ("fusion_timing_metadata_invalid",)


def test_new_actual_parameter_stays_unsupported_until_firmware_integration(tmp_path):
    document = _Document()
    document["firmware_algorithm_parameters"] = [{
        "component": KF6, "schema_id": "silverstar.algorithm-parameters/1.0",
        "manifest_sha256": "0" * 64, "parameters": [{
            "id": "fusion_timing_mode", "value": 0, "unit": "1", "representation": "value",
            "storage_type": "int32", "description": "Future inactive mode",
        }],
    }]
    with pytest.raises(DecoderProfileError, match="parameter_unknown:fusion_timing_mode"):
        _Package_Load(tmp_path, document)


@pytest.mark.parametrize("algorithm_id", ["silverstar.algorithm.kf6", ESKF15])
def test_plugins_refuse_current_declaration_before_numerical_work(tmp_path, algorithm_id):
    from tests.synthetic_parameter_navigation import NavigationPair_Open
    dataset = NavigationPair_Open(tmp_path / "source", flight_samples=9).dataset
    document = dict(dataset.semantic_context.raw_metadata)
    document["metadata_declarations"] = dict(document.get("metadata_declarations", {}))
    document["metadata_declarations"]["fusion_timing"] = _Declaration()
    document["component_locks"] = [{"component": KF6, "version": "99.0.0"}]
    context = replace(dataset.semantic_context, raw_metadata=document)
    dataset = replace(dataset, semantic_context=context)
    plugin = builtin_registry().Algorithm_Get(algorithm_id)
    available = plugin.availability(dataset)
    assert not available.available
    assert available.fidelity == ReplayFidelity.UNAVAILABLE
    assert "fusion_timing_current_replay_not_implemented" in available.missing_inputs
    request = ReplayRequest(mode=ReplayMode.WHAT_IF, process_model_revision=2 if algorithm_id.endswith("kf6") else None)
    with pytest.raises(ValueError, match="fusion_timing_current_replay_not_implemented"):
        plugin.run(dataset, request)


def test_machine_readable_contract_matches_runtime_modes_and_owner_scope():
    root = Path(__file__).resolve().parents[3]
    contract = json.loads((root / "contracts/navigation_fusion_timing_v1.json").read_text(encoding="utf8"))
    assert contract["$id"] == SCHEMA_ID
    assert set(contract["properties"]["component"]["enum"]) == set(LEGACY_VERSIONS)
    assert contract["properties"]["mode"]["enum"] == [0, 1]
    assert set(contract["required"]) == set(_Declaration())
