"""Create real SCG projects for FLP's explicit optional integration gates.

Synthetic software inputs only. No saved/old decoder is relabelled and no
firmware configuration macro is overridden. Compiler fixtures are separate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / 'apps/SCG'
TASK = Path(__file__).resolve().parent / 'inputs'
sys.path.insert(0, str(APP / 'src'))
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.hardware.cubemx import CubeMxImporter
from silverstar_fccg.project.resources import BoardResourceProvisions_Get


def main():
    TASK.mkdir(parents=True, exist_ok=True)
    service = FccgService(APP)
    # Keep import snapshots in this task workspace; the actual catalog is the
    # current SCG catalog and normal production validation/materialization runs.
    service.policy = WorkspacePolicy(TASK)
    service.hardware_importer = CubeMxImporter(service.policy)
    manifests = {}
    for name, estimator, mode in (
        ('existing', 'kf6', 0), ('pure', None, None),
        ('eskf', 'eskf15', 0), ('sf6', 'sf6', None),
        ('joint', 'kf6', 1),
    ):
        project = TASK / name
        model = service.ReferenceProject_Create('FLP_Software_' + name)
        model.strategies['estimator'] = (
            'silverstar.algorithm.estimator.' + estimator if estimator else None
        )
        model = service.ProjectConfiguration_Reconcile(model).model
        if mode is not None:
            model.algorithm_parameters['silverstar.algorithm.estimator.' + estimator][
                'fusion_timing_mode'] = mode
        if name == 'joint':
            model.algorithm_parameters['silverstar.algorithm.estimator.kf6'][
                'baro_measurement_delay_ms'] = 100
        required = {
            'existing': {'KF6_FULL_P'},
            'joint': {'KF6_FULL_P'},
            'eskf': {'ESKF15_STATE', 'ESKF15_FULL_P_PART', 'ESKF15_INITIAL_STATE',
                     'ESKF15_INITIAL_P_PART', 'ESKF15_MEASUREMENT',
                     'ESKF15_BODY_INPUT', 'NAV_QUALITY'},
            'sf6': {'SF6_STATE', 'SF6_MEASUREMENT'},
        }.get(name, set())
        model.logging_streams = [
            replace(stream, enabled=True, decimation=1)
            if stream.record.removeprefix('FLIGHT_LOG_RECORD_') in required else stream
            for stream in model.logging_streams
        ]
        if project.exists():
            if '--resume' not in sys.argv:
                raise RuntimeError(f'Fresh output required: {project}')
            saved = service.Project_Open(project)
            assert saved.identity.name == model.identity.name
            assert saved.strategies == model.strategies
            if mode is not None:
                assert saved.algorithm_parameters[
                    'silverstar.algorithm.estimator.' + estimator]['fusion_timing_mode'] == mode
            model = saved
        else:
            service.Project_Save(model, project, confirm_dangerous=True)
        decoder, = project.glob('*.ssdecoder')
        manifests[name] = dict(project=str(project), decoder=str(decoder),
            decoder_sha256=sha256(decoder.read_bytes()).hexdigest(),
            configuration_sha256=sha256((project/'SilverStar.ssproject').read_bytes()).hexdigest(),
            estimator=estimator, fusion_timing_mode=mode)
        print(name, decoder.name, flush=True)
        if name == 'existing':
            existing_model = deepcopy(model)

    reference = TASK / 'existing'
    inputs = TASK / 'cubemx_input'
    inputs.mkdir(exist_ok=True)
    board = service.catalog.Component_Get(existing_model.board)
    for directory in ('Core', 'FATFS'):
        if not (inputs / directory).exists():
            shutil.copytree(board.payload_root / directory, inputs / directory)
    if not (inputs / 'Drivers').exists():
        shutil.copytree(reference / 'Drivers', inputs / 'Drivers')
    for pattern in ('*.s', '*.ld'):
        for source in reference.glob(pattern):
            shutil.copy2(source, inputs / source.name)
    for source in board.payload_root.glob('*.ioc'):
        shutil.copy2(source, inputs / source.name)
    imported = service.CubeMxProject_Import(inputs, existing_model, risk_acknowledged=True)
    mapping = {item.resource_id: item.metadata['physical_resource']
               for item in BoardResourceProvisions_Get(board)}
    assignments = {key: mapping[value]
                   for key, value in existing_model.resource_assignments.items()}
    model = replace(existing_model, board='', hardware=imported.hardware,
                    resource_assignments=assignments)
    model.identity = replace(model.identity, name='FLP_Software_imported')
    model = service.ProjectConfiguration_Reconcile(model).model
    project = TASK / 'imported'
    service.Project_Save(model, project, confirm_dangerous=True)
    decoder, = project.glob('*.ssdecoder')
    manifests['imported'] = dict(project=str(project), decoder=str(decoder),
        decoder_sha256=sha256(decoder.read_bytes()).hexdigest(),
        configuration_sha256=sha256((project/'SilverStar.ssproject').read_bytes()).hexdigest(),
        estimator='kf6', fusion_timing_mode=0, snapshot=str(imported.snapshot_root))
    receipt = dict(scope=__doc__, source_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), projects=manifests)
    (TASK/'projects.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    print('all projects generated', flush=True)


if __name__ == '__main__':
    main()
