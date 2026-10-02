from __future__ import annotations

import importlib.util
import json

import pytest
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import GroundFiles_Render
from test_round2_targets import _GroundBoardProject_Get


@pytest.fixture
def generated_ground(builtin_catalog, workspace_root, tmp_path):
    files = GroundFiles_Render(_GroundBoardProject_Get(builtin_catalog), builtin_catalog,
                               WorkspacePolicy(workspace_root))
    for relative, content in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    spec = importlib.util.spec_from_file_location('generated_ground_gate', tmp_path / 'Tools/check_ground.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tmp_path, module


def test_generated_ground_gates_validate_actual_sources(generated_ground):
    root, module = generated_ground
    graph = module.Architecture_Check(root)
    assert len(graph['sources']) > 20
    module.Host_Check(root, 'gcc')


@pytest.mark.parametrize('fault', ['missing', 'escape', 'graph', 'role', 'startup'])
def test_generated_ground_architecture_rejects_faults(generated_ground, fault):
    root, module = generated_ground
    graph_path = root / 'Generated/ground_source_graph.json'
    graph = json.loads(graph_path.read_text())
    if fault == 'missing':
        (root / graph['sources'][0]).unlink()
    elif fault == 'escape':
        graph['include_dirs'].append('../escaped')
        graph_path.write_text(json.dumps(graph))
    elif fault == 'graph':
        graph['sources'] = graph['sources'][1:]
        graph_path.write_text(json.dumps(graph))
    elif fault == 'role':
        path = root / 'Generated/ground_target_metadata.json'
        metadata = json.loads(path.read_text())
        metadata['target_role'] = 'flight_controller'
        path.write_text(json.dumps(metadata))
    else:
        main = root / 'Core/Src/main.c'
        main.write_text(main.read_text().replace('GroundBridge_Process', 'MissingBridge_Process'))
    with pytest.raises(ValueError):
        module.Architecture_Check(root)
