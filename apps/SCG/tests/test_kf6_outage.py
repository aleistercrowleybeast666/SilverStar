import json

from algorithm_parameters_support import Trajectory_Run
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile


def test_generated_c_outage_vectors_and_old_project_defaults(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("Kf6Outage")
    values = model.algorithm_parameters["silverstar.algorithm.estimator.kf6"]
    del values["gnss_reacquire_outage_ms"]
    del values["gnss_velocity_vertical_scale"]
    model = ProjectConfiguration_Reconcile(model, service.catalog).model
    values = model.algorithm_parameters["silverstar.algorithm.estimator.kf6"]
    assert values["gnss_reacquire_outage_ms"] == 300
    assert values["gnss_velocity_vertical_scale"] == 1.0
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    raw = Trajectory_Run(project, workspace_root, fixture_name="test_kf6_outage.c")
    actual = [[float(v) for v in row.split()] for row in raw.decode().splitlines()]
    golden = json.loads((workspace_root / "tests/fixtures/kf6_outage_vectors.json").read_text())["rows"]
    assert actual == golden
    for scenario in (0, 1, 2):
        rows = actual[scenario * 64:(scenario + 1) * 64]
        assert all(row[45 + group * 4] == 0 for row in rows for group in range(4))
    assert max(row[45] for row in actual[192:256]) >= 2
    for scenario in (4, 6):
        rows = actual[scenario * 64:(scenario + 1) * 64]
        assert all(row[45 + group * 4] == 0 for row in rows for group in (0, 1, 2))
        assert max(row[57] for row in rows) > 0


def test_vertical_noise_scale_is_consumed_by_generated_c(tmp_path, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("VerticalNoise")
    project = tmp_path / "generated"
    service.Project_Save(model, project, confirm_dangerous=True)
    baseline = Trajectory_Run(project, workspace_root)
    model.algorithm_parameters["silverstar.algorithm.estimator.kf6"]["gnss_velocity_vertical_scale"] = 1.5
    service.Project_Save(model, project, confirm_dangerous=True)
    changed = Trajectory_Run(project, workspace_root)
    assert baseline != changed
