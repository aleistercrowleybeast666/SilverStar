"""Fresh, normally generated mode-2 inputs for exact CPU log production."""
import hashlib
import json
from pathlib import Path
import sys
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[3]
SCG = ROOT / 'apps/SCG'
sys.path.insert(0, str(SCG / 'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import DeviceInstance
from silverstar_fccg.project.validation import Project_Validate

service = FccgService(SCG)
output = ROOT / '.work/gui-convergence-20261110/native-horizon'
output.mkdir(exist_ok=True)
records = []
for family in ('kf6', 'eskf15'):
    model = service.ReferenceProject_Create('GuiConvergence_Native_' + family)
    # The combined JY901B barometer has no proven physical rate, and the reference
    # board has no configured I2C bus. Use its existing barometer-free JY901S
    # profile and explicitly remove barometer landing from this CPU-only input.
    model.device_instances = [replace(row, profile='jy901s') if row.instance_id == 'imu0' else row
                              for row in model.device_instances]
    model.strategies['landing'] = None
    owner = 'silverstar.algorithm.estimator.' + family
    model.strategies['estimator'] = owner
    model = ProjectConfiguration_Reconcile(model, service.catalog).model
    model.algorithm_parameters[owner]['fusion_timing_mode'] = 2
    model.algorithm_parameters[owner]['fusion_horizon_ms'] = 300
    model = ProjectConfiguration_Reconcile(model, service.catalog).model
    validation = Project_Validate(model, service.catalog)
    if not validation.valid:
        raise RuntimeError(str(validation))
    project = output / family
    service.Project_Save(model, project, confirm_dangerous=True)
    header = project / 'Generated/Inc/project_algorithm_parameters.h'
    records.append({'family': family, 'project': str(project), 'model': model.Dictionary_Get(),
                    'parameters_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
                    'hardware_tested': False})
    print(family, 'native mode2/300ms generated', flush=True)
Path(__file__).with_name('native_horizon_inputs.json').write_text(
    json.dumps(records, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
