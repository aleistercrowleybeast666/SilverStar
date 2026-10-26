"""The same selections must have the same firmware/decoder identity across processes."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_raw_augmented_dependencies_and_digest_are_process_independent():
    scg = Path(__file__).resolve().parents[1]
    script = '''
import json
from dataclasses import replace
from pathlib import Path
from silverstar_fccg.plugins.catalog import PluginCatalog
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.generation_state import ProjectDigest_Get
root=Path.cwd()
catalog=PluginCatalog(root/'plugins/builtin',root/'plugins/installed');catalog.Scan()
model=ReferenceProject_Create('DependencyIdentity',catalog=catalog)
model.device_instances[0]=replace(model.device_instances[0],plugin='silverstar.device.imu.bmi088')
model.strategies['estimator']='silverstar.algorithm.estimator.eskf20'
model=ProjectConfiguration_Reconcile(model,catalog).model
print(json.dumps({'base':model.base_components,'digest':ProjectDigest_Get(model),
                 'components':model.ComponentIds_Get()},sort_keys=True))
'''
    results = []
    for seed in ('0', '1', '2', '3', '4', '5', '6', '7'):
        environment = {**os.environ, 'PYTHONHASHSEED': seed,
                       'PYTHONPATH': str(scg / 'src')}
        result = subprocess.run([sys.executable, '-c', script], cwd=scg,
                                env=environment, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        results.append(json.loads(result.stdout))
    assert 'silverstar.sensor.register_bus' in results[0]['base']
    assert 'silverstar.algorithm.augmented.common' in results[0]['base']
    assert all(result == results[0] for result in results), results
