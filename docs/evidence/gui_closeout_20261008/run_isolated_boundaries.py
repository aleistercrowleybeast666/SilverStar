"""Recheck the nine previously failing cases without claiming a batch pass."""
import json
import os
from pathlib import Path
import subprocess
import time

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).parent
nodes = [
    'test_project_artifact_boundaries.py::test_save_data_toggle_retains_files_configurations_and_can_enable_again',
    *[f'test_project_artifact_boundaries.py::test_parse_cache_faults_fall_back_only_to_strict_coordinator[{fault}]'
      for fault in ('corrupt', 'parser_revision', 'changed_log')],
    *[f'test_run_deletion.py::test_save_as_recovery_dependency_and_local_move[{value}]' for value in ('True', 'False')],
    'test_project_artifacts.py::test_four_completed_algorithms_and_two_distinct_runs_roundtrip',
    'test_project_artifacts.py::test_gui_reopen_restores_every_run_and_two_sources_without_replay',
    'test_project_artifacts.py::test_valid_full_parse_cache_never_calls_parser_and_preserves_explorer',
]
results = []
for index, node in enumerate(nodes):
    command = [str(repo/'apps/FLP/.venv/Scripts/python.exe'), str(out/'run_flp_tests.py'),
               '-p', 'closeout_test_paths', 'apps/FLP/tests/'+node, '-q',
               '--basetemp='+str(repo/'.work'/f'fi9{index}')]
    log = out/f'isolated_boundary_v9_{index}.log'
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=repo, env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                                stdout=stream, stderr=subprocess.STDOUT)
    results.append(dict(command=command, exit_code=result.returncode,
                        elapsed_seconds=time.monotonic()-started, log=str(log)))
    (out/'isolated_boundaries_v9.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(index, result.returncode, flush=True)
raise SystemExit(0 if all(item['exit_code'] == 0 for item in results) else 1)
