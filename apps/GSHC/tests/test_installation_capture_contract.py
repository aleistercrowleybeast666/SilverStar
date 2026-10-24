"""Offline capture provenance and fail-closed INFO regressions; no serial opens."""
import copy
from dataclasses import replace
import json
from threading import Event

import pytest

from services.installation_calibration_backend import InstallationBinding_Parse, InstallationCapabilities_Parse
from services.installation_calibration_fit import _digest
from services.installation_calibration_capture_contract import (CaptureProofResult, CaptureProvenance_Audit,
    InfoSnapshot_Decode)
from services.installation_calibration_backend import InstallationBackend, InstallationResult
from services.installation_calibration_protocol import SamplePart_Encode
from services.installation_calibration_worker import InstallationWorker
from test_installation_calibration_backend import MockInstallationOwner, response, run_job


def capabilities():
    return InstallationCapabilities_Parse(response("OK", "CAPS", maintenance="0.1", supported=1,
        install_contract=1, face_auto=1, check_only=1, sample_format=1, max_request=191,
        max_line=511, train_pairs=5, holdout_pairs=5, pair_capacity=4096, offline=1), allow_simulated=True)


def signed(data):
    data = copy.deepcopy(data)
    data["binding_digest"] = _digest({key: value for key, value in data.items() if key != "binding_digest"})
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode(), "B-" + data["binding_digest"][:30]


def test_info_missing_explicit_capture_time_qualification_is_not_accepted():
    data = copy.deepcopy(MockInstallationOwner().info)
    data.pop("capture_provenance", None)
    payload, binding = signed(data)
    with pytest.raises(ValueError):
        InstallationBinding_Parse(payload, binding, capabilities())


def test_info_unknown_extension_cannot_escape_the_immutable_binding():
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    data["unbound_time_override"] = "SENSOR_SYNCHRONIZED"
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError):
        InstallationBinding_Parse(payload, provider.binding, capabilities())


def test_info_duplicate_json_keys_are_rejected_before_binding():
    provider = MockInstallationOwner()
    payload = provider.payload.replace(b'{"', b'{"boot":"test-boot","', 1)
    with pytest.raises(ValueError):
        InstallationBinding_Parse(payload, provider.binding, capabilities())


@pytest.mark.parametrize("field,value", [
    ("sample_time_basis", "TARGET_RECEIVE_DECODE_PROXY"), ("sample_time_basis", "UNKNOWN"),
    ("sample_time_provenance", "UNKNOWN"), ("epoch_provenance", "UNKNOWN"),
    ("native_sequence_provenance", "UNKNOWN"), ("measurement_uncertainty_bound_us", None),
    ("measurement_uncertainty_bound_us", 2**32-1), ("measurement_uncertainty_bound_us", 1001),
])
def test_time_or_native_continuity_unknown_remains_a_closed_gate(field, value):
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    data["capture_provenance"]["sources"]["MAG"][field] = value
    payload, binding = signed(data)
    with pytest.raises(ValueError): InstallationBinding_Parse(payload, binding, capabilities())


def test_receive_proxy_is_not_qualified_even_if_uncertainty_is_fabricated_zero():
    provider = MockInstallationOwner()
    declaration = copy.deepcopy(provider.info["capture_provenance"])
    declaration["sources"]["MAG"].update(sample_time_basis="TARGET_RECEIVE_DECODE_PROXY",
        sample_time_provenance="JY901B_0x54_LOCAL_DECODE", measurement_uncertainty_bound_us=0)
    result = CaptureProvenance_Audit(declaration, provider.sources, provider.policy, simulated=True)
    assert result.result == CaptureProofResult.Unproven and "MEASUREMENT_TIME_UNPROVEN" in result.reason


def test_unknown_hardware_identity_is_explicit_without_inventing_unique_chip_proof():
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    item = data["capture_provenance"]["sources"]["MAG"]
    item["identity_scope"] = "DECLARED_ENDPOINT"
    payload, binding = signed(data)
    parsed = InstallationBinding_Parse(payload, binding, capabilities())
    assert parsed.capture_qualification.result == CaptureProofResult.Qualified
    assert json.loads(parsed.raw_json)["capture_provenance"]["sources"]["MAG"]["hardware_identity"] is None
    item["identity_scope"] = "CHIP_UNIQUE"
    payload, binding = signed(data)
    with pytest.raises(ValueError): InstallationBinding_Parse(payload, binding, capabilities())


def test_synthetic_time_and_identity_cannot_qualify_an_unsimulated_provider():
    provider = MockInstallationOwner()
    caps = replace(capabilities(), simulated=False)
    with pytest.raises(ValueError): InstallationBinding_Parse(provider.payload, provider.binding, caps)


def test_audit_cannot_skip_one_of_the_two_sources():
    provider = MockInstallationOwner()
    with pytest.raises(ValueError):
        CaptureProvenance_Audit(provider.info["capture_provenance"],provider.sources[:1],provider.policy,simulated=True)


def test_individually_small_source_bounds_must_also_fit_the_pair_policy():
    provider = MockInstallationOwner()
    declaration = copy.deepcopy(provider.info["capture_provenance"])
    for item in declaration["sources"].values(): item["measurement_uncertainty_bound_us"] = 600
    result = CaptureProvenance_Audit(declaration,provider.sources,provider.policy,simulated=True)
    assert result.result == CaptureProofResult.Unproven and "PAIR_TIME_BOUND_EXCEEDS_POLICY" in result.reason


@pytest.mark.parametrize("field,value", [("native_rate_unchanged", False), ("value_dependent", True),
    ("kind", "SELECT_BEST_VALUES"), ("nominal_output_millihz", True)])
def test_selection_declaration_cannot_reconfigure_or_bias_native_sampling(field, value):
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    data["capture_provenance"]["selection"][field] = value
    payload, binding = signed(data)
    with pytest.raises(ValueError): InstallationBinding_Parse(payload, binding, capabilities())


@pytest.mark.parametrize("change", ("missing_source_field", "missing_policy_field", "changed_parent", "changed_uid"))
def test_full_info_snapshot_and_digest_cover_every_mutable_parent(change):
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    if change == "missing_source_field": del data["sources"]["IMU"]["provider_calibration"]
    elif change == "missing_policy_field": del data["capture_policy"]["max_uncertainty_us"]
    elif change == "changed_parent": data["accel"]["generation"] += 1
    else: data["capture_provenance"]["sources"]["MAG"]["hardware_identity"] = "CHIP-A"
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError): InstallationBinding_Parse(payload, provider.binding, capabilities())


def test_frozen_info_does_not_alias_the_decoded_input():
    provider = MockInstallationOwner()
    data = copy.deepcopy(provider.info)
    payload, binding = signed(data)
    parsed = InstallationBinding_Parse(payload, binding, capabilities())
    data["capture_provenance"]["sources"]["MAG"]["measurement_uncertainty_bound_us"] = 999
    assert dict(parsed.capture_qualification.source_bounds)["MAG"] == 30
    assert parsed.raw_json == payload


@pytest.mark.parametrize("bad", [b"["*17+b"0"+b"]"*17, b"{\"boot\":NaN}", b"{}"+b" "*8192])
def test_info_depth_nonfinite_and_byte_bounds_are_checked_before_construction(bad):
    from services.installation_calibration_contract import InstallationContract_Load
    with pytest.raises(ValueError): InfoSnapshot_Decode(bad, InstallationContract_Load().Read()["info_snapshot"])


def test_canonical_info_pages_roundtrip_quotes_brackets_and_float_edge_values():
    provider = MockInstallationOwner()
    from services.installation_calibration_contract import InstallationContract_Load
    rules = InstallationContract_Load().Read()["info_snapshot"]
    assert len(provider.payload) <= 8192
    pages = tuple(provider.payload[i:i+48] for i in range(0, len(provider.payload), 48))
    assert len(pages) <= 171 and all(1 <= len(page) <= 48 for page in pages)
    assert InfoSnapshot_Decode(b"".join(pages), rules) == json.loads(provider.payload)
    variants = []
    for number in (0, 0.0, -0.0, 1e-30, 1e30):
        data = copy.deepcopy(provider.info)
        data["convention"]["evidence"] = 'DECLARED_[{\\"}]'
        data["accel"]["bias"] = list(data["accel"]["bias"])
        data["accel"]["bias"][0] = number
        payload, _ = signed(data)
        assert InfoSnapshot_Decode(payload, rules)["accel"]["bias"][0] == number
        variants.append(payload)
    assert len(set(variants)) == 5  # 0, 0.0 and -0.0 have distinct canonical bytes


def test_host_sample_cannot_understate_the_bound_frozen_in_info(tmp_path):
    class UnderstatedTimeOwner(MockInstallationOwner):
        def _capture(self, *args):
            super()._capture(*args)
            pair = self.collector.pairs[0]
            bad = replace(pair, imu=replace(pair.imu, uncertainty_us=0))
            first = list(self.batch[0]); first[0] = SamplePart_Encode(bad, "IMU", self.binding)[:-2]
            self.batch[0] = tuple(first)
    provider = UnderstatedTimeOwner()
    backend = InstallationBackend(provider, allow_simulated=True)
    worker = InstallationWorker(backend)
    path = tmp_path / "understated_time.jsonl"
    try:
        assert run_job(worker, "begin", archive_path=path).result == InstallationResult.Ok
        outcome = run_job(worker, "face", face="XP", attempt=1)
        assert outcome.result == InstallationResult.Failed and "SOURCE_TIME_BOUND_NOT_HONORED" in outcome.reason
        assert not backend.dataset.records and not outcome.apply_allowed
    finally: worker.Close()
    assert '"kind":"source_part"' in path.read_text(encoding="utf-8")


def test_replay_cannot_promote_a_crc_valid_record_with_understated_time(tmp_path):
    from services.installation_calibration_replay import InstallationReplay_Load
    provider = MockInstallationOwner()
    backend = InstallationBackend(provider, allow_simulated=True)
    worker = InstallationWorker(backend)
    original = tmp_path/"original.jsonl"
    try:
        assert run_job(worker,"begin",archive_path=original).result == InstallationResult.Ok
        assert run_job(worker,"face",face="XP",attempt=1).result == InstallationResult.Ok
        assert run_job(worker,"close").result == InstallationResult.Ok
    finally: worker.Close()
    assert InstallationReplay_Load(original).complete_faces == 1
    saved = original.read_bytes()
    pair = provider.collector.pairs[0]
    bad = replace(pair,imu=replace(pair.imu,uncertainty_us=0))
    items = [json.loads(line) for line in saved.splitlines()]
    first_part = next(item for item in items if item["kind"] == "source_part")
    first_part["line_hex"] = SamplePart_Encode(bad,"IMU",provider.binding)[:-2].hex()
    first_pair = next(item for item in items if item["kind"] == "pair")
    first_pair["imu"]["uncertainty_us"] = 0
    tampered = tmp_path/"tampered_underbound.jsonl"
    tampered.write_text("".join(json.dumps(item,sort_keys=True,separators=(",",":"))+"\n" for item in items),encoding="utf-8")
    with pytest.raises(ValueError,match="RAW_SOURCE_PART_MISMATCH"):
        InstallationReplay_Load(tampered)
    assert original.read_bytes() == saved


def test_cleanup_unknown_blocks_a_new_session_even_after_local_release(tmp_path):
    class UnconfirmedOwner(MockInstallationOwner):
        def Request(self, data, **kwargs):
            if b" CANCEL" in data: raise TimeoutError("remote outcome unknown")
            return super().Request(data, **kwargs)
    provider = UnconfirmedOwner()
    backend = InstallationBackend(provider, allow_simulated=True)
    worker = InstallationWorker(backend)
    try:
        assert run_job(worker, "begin", archive_path=tmp_path/"first.jsonl").result == InstallationResult.Ok
        assert run_job(worker, "close").result == InstallationResult.Unknown
        assert not provider.busy and backend.lease is None and not backend.cleanup_confirmed
        assert run_job(worker, "begin", archive_path=tmp_path/"second.jsonl").result == InstallationResult.Unknown
        assert not (tmp_path/"second.jsonl").exists()
    finally: worker.Close()


def test_late_or_cancelled_exchange_cannot_publish_a_success():
    class Clock:
        now = 0.
        def __call__(self): return self.now
    class LateLease:
        def __init__(self, clock, cancel, mode): self.clock, self.cancel, self.mode = clock, cancel, mode
        def Request(self, *_args, **_kwargs):
            if self.mode == "late": self.clock.now = 5.
            else: self.cancel.set()
            return (b"OK INSTALL CAPS supported=1",)
    from services.installation_calibration_protocol import Request
    for mode, error in (("late", TimeoutError), ("cancelled", InterruptedError)):
        clock, cancel = Clock(), Event()
        backend = InstallationBackend(clock=clock); backend.lease = LateLease(clock, cancel, mode)
        with pytest.raises(error): backend._request(Request("CAPS"), cancel, 120.)
