"""Known-truth, physically realizable and adversarial offline tests."""
from dataclasses import FrozenInstanceError, asdict, replace
import ast
import json
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from .prototype import (CandidateResult, Convention, FACE_AXES, FACES, Geometry_Evaluate,
    ImuSixFace_Fit, InstallationSession, IntrinsicFitResult, MagEllipsoid_Fit, Policy,
    Rotation_DistanceDeg, Snapshot_Export, Snapshot_Import, Supplement_Suggest)
from .synthetic_cases import Case_Build, RotationCloud_Build

POLICY = Policy(starts=48)
REPORTS = {}


def save_report(name, result, case):
    row = asdict(result)
    row["truth_s"] = case.s_true
    row["truth_rotation"] = case.R_AM_true
    if result.candidates:
        row["best_rotation_error_deg"] = Rotation_DistanceDeg(result.candidates[0].R_AM, case.R_AM_true)
    REPORTS[name] = row
    assert not result.apply_allowed
    assert result.gates["global_uniqueness"] == "NOT_PROVEN_MULTISTART"
    return result


@pytest.fixture(scope="module", autouse=True)
def evidence():
    yield
    destination = os.environ.get("INSTALL_CAL_EVIDENCE")
    if destination:
        target = Path(destination).resolve()
        prefix = os.environ.get("INSTALL_CAL_PREFIX", "")
        allowed = Path(__file__).resolve().parents[4]/".work"/"dev013_installation_calibration_20261018"
        assert target.is_relative_to(allowed.resolve())
        (target/(prefix+"cases.json")).write_text(json.dumps(REPORTS, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        case = Case_Build()
        (target/(prefix+"raw_baseline.json")).write_text(json.dumps(Snapshot_Export(case.session, case.accel, case.mag, POLICY),
            indent=2, allow_nan=False)+"\n", encoding="utf-8")


@pytest.fixture(scope="module")
def normal():
    case = Case_Build()
    progress = []
    result = save_report("normal_six_faces", case.session.Solve(case.accel, case.mag, POLICY,
        progress=lambda done, total: progress.append((done, total))), case)
    REPORTS["normal_six_faces"]["progress"] = progress
    return case, result


@pytest.mark.parametrize("kind", ["normal", "symmetric", "ambiguous"])
def test_fixtures_are_rigid_poses_of_one_fixed_world_field(kind):
    case = Case_Build(kind)
    field = np.array([np.sqrt(1-case.s_true**2), 0., case.s_true])
    for i, face in enumerate(FACES):
        pose = np.array(case.R_WA[i]); row = case.session.records[i*10]
        a = case.accel.Correct(row.accel)/9.80665
        m = case.mag.Correct(row.magnetic)/48
        np.testing.assert_allclose(pose.T @ pose, np.eye(3), atol=1e-12)
        assert np.linalg.det(pose) == pytest.approx(1.)
        np.testing.assert_allclose(pose @ a, [0., 0., 1.], atol=1e-12)
        np.testing.assert_allclose(pose @ np.array(case.R_AM_true) @ m, field, atol=1e-12)
        assert a @ np.array(case.R_AM_true) @ m == pytest.approx(case.s_true)


def test_normal_six_faces_are_candidate_only(normal):
    case, result = normal
    assert result.result == CandidateResult.Candidate
    assert Rotation_DistanceDeg(result.candidates[0].R_AM, case.R_AM_true) < 1e-5
    assert result.candidates[0].s == pytest.approx(case.s_true, abs=1e-8)
    assert result.gates["local_excitation"] == "PASS"
    assert result.gates["holdout"] == "PASS"
    assert result.gates["candidate_separation"] == "NO_COMPETITOR_FOUND_NOT_PROOF"
    assert result.gyro_scale_status == "NOT_ESTIMATED_STATIC_SIX_FACE"
    assert result.dynamic_gyro_status == "NOT_IMPLEMENTED"
    assert REPORTS["normal_six_faces"]["progress"] == [(i, POLICY.starts) for i in range(POLICY.starts+1)]
    assert result.gates["holdout_selection"] == "VALIDATION_ONLY_NEVER_SELECTS"


def test_centered_jacobian_matches_independent_finite_difference():
    case = Case_Build()
    a = np.array([FACE_AXES[x] for x in FACES])
    m = np.array([case.mag.Correct(case.session.records[i*10].magnetic)/48 for i in range(6)])
    R = np.array(case.R_AM_true)
    weights = np.array([1, 2, 3, 4, 5, 6])/21
    _, _, _, _, analytic = Geometry_Evaluate(a, m, R, weights)
    finite = np.zeros((6, 3))
    for j in range(3):
        step = np.eye(3)[j]*1e-6
        plus = Geometry_Evaluate(a, m, Rotation.from_rotvec(step).as_matrix() @ R, weights)[1]
        minus = Geometry_Evaluate(a, m, Rotation.from_rotvec(-step).as_matrix() @ R, weights)[1]
        finite[:, j] = (plus-minus)/2e-6
    np.testing.assert_allclose(analytic, finite, atol=2e-10)


def test_physical_antipodal_six_face_degeneracy_rejected():
    case = Case_Build("symmetric")
    result = save_report("physical_symmetric_six", case.session.Solve(case.accel, case.mag, POLICY), case)
    assert result.result == CandidateResult.NeedSamples
    assert result.gates["local_excitation"] == "FAIL"
    assert result.candidates[0].singular_values[-1] < 1e-8
    assert result.candidates[0].train_rms < 1e-7  # residual alone would falsely pass


def test_two_exact_physical_solutions_survive_coarse_prior_and_full_local_rank():
    case = Case_Build("ambiguous")
    a = np.array([FACE_AXES[f] for f in FACES])
    m = np.array([case.mag.Correct(case.session.records[i*10].magnetic)/48 for i in range(6)])
    for R in (case.R_AM_true, case.alternate_R_AM):
        _, residual, singular, _, _ = Geometry_Evaluate(a, m, R)
        assert max(abs(residual)) < 1e-12
        assert singular[-1] > .01
    assert Rotation_DistanceDeg(case.R_AM_true, case.alternate_R_AM) > 25
    result = save_report("ambiguous_with_coarse_prior", case.session.Solve(case.accel, case.mag,
        replace(POLICY, starts=96), coarse_prior_R=case.R_AM_true, coarse_prior_radius_deg=75), case)
    assert result.result == CandidateResult.NeedSamples
    assert "MULTIPLE_SOLUTIONS" in result.reasons
    assert int(result.gates["coarse_prior_candidates_inside"]) >= 2
    assert result.gates["coarse_prior"] == "DIAGNOSTIC_ONLY_NEVER_DISAMBIGUATES"


def test_low_horizontal_field_is_not_certified_by_residual():
    case = Case_Build(s=.99999)
    result = save_report("near_vertical_field", case.session.Solve(case.accel, case.mag, POLICY), case)
    assert result.result == CandidateResult.NeedSamples
    assert set(result.reasons) & {"HORIZONTAL_FIELD", "LOCAL_EXCITATION", "MULTIPLE_SOLUTIONS"}


def test_noisy_six_face_candidate_and_error_budget():
    case = Case_Build(noise=.025)
    result = save_report("noisy_six_faces", case.session.Solve(case.accel, case.mag, POLICY), case)
    assert result.result == CandidateResult.Candidate
    assert Rotation_DistanceDeg(result.candidates[0].R_AM, case.R_AM_true) < .8


def corrupt_direction(case, split):
    rotation = Rotation.from_rotvec([.4, -.2, .3]).as_matrix()
    rows = []
    for row in case.session.records:
        if row.face == "XP" and row.split == split:
            rotated = rotation @ case.mag.Correct(row.magnetic)
            row = replace(row, magnetic=tuple(np.linalg.solve(case.mag.matrix, rotated)+case.mag.bias))
        rows.append(row)
    return InstallationSession(tuple(rows), case.session.convention)


def test_direction_outlier_not_hidden_by_robust_loss():
    case = Case_Build()
    session = corrupt_direction(case, "TRAIN")
    result = save_report("direction_outlier", session.Solve(case.accel, case.mag, POLICY), case)
    assert result.result == CandidateResult.NeedSamples
    assert set(result.reasons) & {"TRAIN", "HOLDOUT"}


def test_independent_holdout_failure_blocks_candidate():
    case = Case_Build()
    result = save_report("holdout_failure", corrupt_direction(case, "HOLDOUT").Solve(case.accel, case.mag, POLICY), case)
    assert result.result == CandidateResult.NeedSamples
    assert "HOLDOUT" in result.reasons
    assert result.candidates[0].train_rms < 1e-7


def test_same_face_resample_improves_weak_direction_without_tilt():
    base = Case_Build("symmetric")
    a = np.array([FACE_AXES[f] for f in FACES])
    m = np.array([base.mag.Correct(base.session.records[i*10].magnetic)/48 for i in range(6)])
    _, _, before, weak, _ = Geometry_Evaluate(a, m, base.R_AM_true)
    suggestions = Supplement_Suggest(weak)
    assert abs(FACE_AXES[suggestions[0][0]] @ weak) <= abs(FACE_AXES[suggestions[-1][0]] @ weak)
    # The user stays on a face; the simulation knows angles, the solver does not.
    case = Case_Build("symmetric", supplement=((suggestions[0][0], .7), (suggestions[2][0], 1.9)))
    result = save_report("same_face_supplement", case.session.Solve(case.accel, case.mag, POLICY), case)
    assert result.candidates[0].singular_values[-1] > before[-1]+.02
    assert result.result == CandidateResult.Candidate
    assert all(r.face in FACES for r in case.session.records)
    # Counterexample: a normal parallel to the weak rotation axis gives zero score.
    axial = Supplement_Suggest([1., 0., 0.])
    assert dict(axial)["XP"] == 0 and dict(axial)["YP"] == 1


@pytest.mark.parametrize("change,reason", [
    ({"sync_valid": False}, "UNQUALIFIED_SYNC"),
    ({"mag_us": 203000, "mag_receive_us": 203500}, "UNQUALIFIED_SYNC"),
    ({"clock": "PC_RECEIVE_PROXY"}, "CLOCK_CHANGED"),
    ({"quality_flags": ("SAMPLE_GAP",)}, "UNQUALIFIED_SYNC"),
    ({"imu_epoch": 999}, "EPOCH"),
    ({"boot": "other-boot"}, "SESSION"),
    ({"pair_id": 1}, "DUPLICATE_PAIR"),
    ({"imu_seq": 1}, "DISCONTINUITY"),
    ({"stage": "DYNAMIC"}, "DYNAMIC_GYRO_NOT_IMPLEMENTED"),
])
def test_unsafe_input_rejected_without_solver(change, reason):
    case = Case_Build(); rows = list(case.session.records)
    rows[1] = replace(rows[1], **change)
    result = InstallationSession(rows, case.session.convention).Solve(case.accel, case.mag, POLICY)
    assert result.result == CandidateResult.Rejected
    assert reason in result.reasons[0]
    assert not result.candidates and result.search_attempts == 0


def test_declared_wrong_axes_rejected_but_hidden_reflection_is_unidentifiable():
    with pytest.raises(ValueError):
        Convention(handedness="LEFT")
    case = Case_Build()
    wrong_frame = replace(case.mag, output_frame="G")
    assert case.session.Solve(case.accel, wrong_frame, POLICY).result == CandidateResult.Rejected
    reflection = np.diag([-1., 1., 1.])
    rows = [replace(row, magnetic=tuple(np.linalg.solve(case.mag.matrix,
            reflection @ case.mag.Correct(row.magnetic))+case.mag.bias)) for row in case.session.records]
    result = save_report("hidden_reflection_not_detectable", InstallationSession(rows, case.session.convention).Solve(case.accel, case.mag, POLICY), case)
    # (-R F) is proper and flips s: the scalar invariant cannot reveal this lie.
    assert result.result == CandidateResult.Candidate
    assert result.candidates[0].s == pytest.approx(-case.s_true, abs=1e-7)
    assert result.gates["coordinate_evidence"] == "DECLARED_NOT_HARDWARE_VERIFIED"
    assert not result.apply_allowed


def test_accel_gyro_misalignment_requires_explicit_composition(normal):
    case, result = normal
    R_GA = Rotation.from_rotvec([.25, -.15, .08]).as_matrix()
    convention = replace(case.session.convention, R_GA=tuple(map(tuple, R_GA)), gyro_axis_evidence="KNOWN_FIXTURE")
    session = InstallationSession(case.session.records, convention)
    report = save_report("explicit_accel_gyro_rotation", session.Solve(case.accel, case.mag, POLICY), case)
    np.testing.assert_allclose(report.candidates[0].R_GM, R_GA @ case.R_AM_true, atol=1e-7)
    assert Rotation_DistanceDeg(report.candidates[0].R_GM, case.R_AM_true) > 10
    unknown = InstallationSession(case.session.records, Convention())
    report = save_report("unknown_accel_gyro_axes", unknown.Solve(case.accel, case.mag, POLICY), case)
    assert report.candidates[0].R_GM is None and report.gates["gyro_axes"] == "NOT_PROVEN"


def test_intrinsic_refit_reuses_unchanged_raw_and_invalidates_old_candidate(normal):
    case, old = normal
    original = case.session.raw_digest
    previous_accel = replace(case.accel, bias=(.4, -.3, .2), matrix=tuple(map(tuple, np.eye(3))),
                             calibration_id="inaccurate-accel")
    previous_mag = replace(case.mag, bias=(8., -9., 6.), matrix=tuple(map(tuple, np.eye(3))),
                           calibration_id="inaccurate-mag")
    before = save_report("inaccurate_intrinsics", case.session.Solve(previous_accel, previous_mag, POLICY), case)
    assert before.result != CandidateResult.Candidate
    status, accel, gyro_bias = ImuSixFace_Fit(case.session, previous_accel)
    assert status == IntrinsicFitResult.Candidate
    np.testing.assert_allclose(accel.bias, case.accel.bias, atol=1e-12)
    np.testing.assert_allclose(accel.matrix, case.accel.matrix, atol=1e-12)
    np.testing.assert_allclose(gyro_bias, [.003, -.005, .002], atol=1e-12)
    status, mag = MagEllipsoid_Fit(RotationCloud_Build(case.mag), previous_mag)
    assert status == IntrinsicFitResult.Candidate
    np.testing.assert_allclose(mag.matrix, case.mag.matrix, atol=1e-10)
    np.testing.assert_allclose(mag.bias, case.mag.bias, atol=1e-10)
    assert not case.session.CandidateIsCurrent(old, accel, mag, POLICY)
    report = save_report("intrinsic_refit_from_original", case.session.Solve(accel, mag, POLICY), case)
    assert report.result == CandidateResult.Candidate
    assert case.session.raw_digest == original
    assert report.context_digest != old.context_digest
    assert not case.session.CandidateIsCurrent(before, accel, mag, POLICY)
    assert accel.matrix != previous_accel.matrix and mag.bias != previous_mag.bias
    assert case.session.records[0].acquisition_intrinsic_ids == ("acquisition-accel-g6", "acquisition-mag-g10")
    assert case.session.records[0].acquisition_intrinsic_generations == (6, 10)


def test_holdout_never_selects_a_different_training_candidate():
    case, ordinary = Case_Build("ambiguous"), Case_Build()
    reports = []
    for label, target in (("true", case.R_AM_true), ("alternate", case.alternate_R_AM)):
        rows = []
        for row, normal_row in zip(case.session.records, ordinary.session.records):
            if row.split == "HOLDOUT":
                corrected = np.array(target).T @ case.R_AM_true @ case.mag.Correct(normal_row.magnetic)
                row = replace(row, magnetic=tuple(np.linalg.solve(case.mag.matrix, corrected)+case.mag.bias))
            rows.append(row)
        report = save_report("holdout_cannot_select_"+label,
            InstallationSession(rows, case.session.convention).Solve(case.accel, case.mag, replace(POLICY, starts=96)), case)
        reports.append(report)
    for report in reports:
        assert report.result == CandidateResult.NeedSamples
        assert "MULTIPLE_SOLUTIONS" in report.reasons
    assert Rotation_DistanceDeg(reports[0].candidates[0].R_AM, reports[1].candidates[0].R_AM) < 1e-8


def test_bad_or_degenerate_intrinsics_are_not_repaired():
    case = Case_Build()
    with pytest.raises(ValueError):
        replace(case.mag, matrix=((-1., 0, 0), (0, 1., 0), (0, 0, 1.)))
    assert MagEllipsoid_Fit([(1., 1., 1.)]*128, case.mag)[0] == IntrinsicFitResult.Rejected
    assert MagEllipsoid_Fit([(1., 1., 1.)]*127, case.mag)[0] == IntrinsicFitResult.Rejected
    swapped = replace(case.accel, identity=replace(case.accel.identity, physical=8))
    assert case.session.Solve(swapped, case.mag, POLICY).result == CandidateResult.Rejected


def test_intrinsic_helpers_preserve_metadata_and_diagonal_model_limits():
    case = Case_Build()
    rows = list(case.session.records)
    rows[1] = replace(rows[1], imu_epoch=999)
    assert ImuSixFace_Fit(InstallationSession(rows, case.session.convention), case.accel)[0] == IntrinsicFitResult.Rejected
    assert ImuSixFace_Fit(case.session, replace(case.accel, unit="uT"))[0] == IntrinsicFitResult.Rejected
    assert MagEllipsoid_Fit([[1., 2.], [3.]], case.mag)[0] == IntrinsicFitResult.Rejected
    assert MagEllipsoid_Fit(RotationCloud_Build(case.mag), replace(case.mag, unit="m/s2"))[0] == IntrinsicFitResult.Rejected
    turned = Rotation.from_rotvec([0., 0., .2]).as_matrix()
    rows = [replace(r, accel=tuple(turned @ r.accel)) for r in case.session.records]
    assert ImuSixFace_Fit(InstallationSession(rows, case.session.convention), case.accel)[0] == IntrinsicFitResult.Rejected


def test_repeated_static_observations_do_not_fix_geometric_rank():
    case = Case_Build("symmetric")
    a = np.array([FACE_AXES[f] for f in FACES])
    m = np.array([case.mag.Correct(case.session.records[i*10].magnetic)/48 for i in range(6)])
    original = Geometry_Evaluate(a, m, case.R_AM_true)[2]
    repeated = Geometry_Evaluate(np.repeat(a, 20, axis=0), np.repeat(m, 20, axis=0), case.R_AM_true)[2]
    np.testing.assert_allclose(original, repeated, atol=1e-14)
    assert repeated[-1] < 1e-12


def test_owned_immutable_records_and_limits(normal):
    case, result = normal
    with pytest.raises(FrozenInstanceError):
        case.session.records = ()
    with pytest.raises(FrozenInstanceError):
        case.session.records[0].face = "XP"
    source = [1., 2., 3.]; row = replace(case.session.records[0], accel=source); source[0] = 99
    assert row.accel[0] == 1
    with pytest.raises(ValueError):
        InstallationSession((case.session.records*69)[:4097])
    with pytest.raises(ValueError):
        Policy(starts=257)
    with pytest.raises(ValueError):
        replace(case.session.records[0], magnetic=(np.nan, 0, 0))
    with pytest.raises(ValueError):
        replace(case.session.records[0], acquisition_intrinsic_ids=(["mutable"], "id"))
    with pytest.raises((TypeError, ValueError)):
        replace(result, apply_allowed=True)
    assert not hasattr(case.session, "Apply") and not hasattr(case.session, "Save")


def test_cancellation_during_bounded_search():
    case = Case_Build(); calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls > 30
    result = case.session.Solve(case.accel, case.mag, POLICY, cancel=cancel)
    assert result.result == CandidateResult.Cancelled and not result.apply_allowed
    assert 0 < result.search_attempts <= POLICY.starts


def test_window_holdout_leak_and_motion_rejected():
    case = Case_Build(); rows = list(case.session.records)
    rows[5] = replace(rows[5], window=rows[0].window)
    assert InstallationSession(rows, case.session.convention).Solve(case.accel, case.mag, POLICY).result == CandidateResult.Rejected
    rows = [replace(r, gyro=(2., 0, 0)) if r.face == "XP" else r for r in case.session.records]
    assert InstallationSession(rows, case.session.convention).Solve(case.accel, case.mag, POLICY).result == CandidateResult.NeedSamples


def test_experiment_has_no_production_or_transport_imports():
    root = Path(__file__).parent
    assert not (root/"plugin.json").exists()
    tree = ast.parse((root/"prototype.py").read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): modules += [x.name for x in node.names]
        if isinstance(node, ast.ImportFrom): modules.append(node.module)
    assert not any(x.startswith(("serial", "PySide6", "silverstar_fccg", "transport")) for x in modules)
    assert any(x=="services.installation_calibration_fit" for x in modules)


def test_complete_raw_snapshot_roundtrip_is_owned_and_context_bound(normal):
    case, report = normal
    payload = json.loads(json.dumps(Snapshot_Export(case.session, case.accel, case.mag, POLICY)))
    session, accel, mag, policy = Snapshot_Import(payload)
    assert session.raw_digest == case.session.raw_digest
    assert session.CandidateIsCurrent(report, accel, mag, policy)
    payload["records"][0]["accel"][0] = 999
    assert session.raw_digest == case.session.raw_digest and session.records[0].accel[0] != 999
    changed, *_ = Snapshot_Import(payload)
    assert changed.raw_digest != session.raw_digest
    payload.pop("policy")
    with pytest.raises(ValueError):
        Snapshot_Import(payload)
