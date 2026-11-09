"""Generate the three current stack-review inputs; no build, admission or hardware access."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

SCG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCG / 'src'))

from h743_static_validate import Scenario_Create
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.logging import LoggingProfile_Reconcile
from silverstar_fccg.project.model import ProjectModel_Load
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate


def Main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--case', action='append', choices=('f4', 'capture', 'h7', 'research'),
                        help='Generate only the selected case(s); defaults to f4, capture and h7.')
    parser.add_argument('--h743-input', type=Path,
                        help='Reviewed synchronized software CubeMX fixture, preserved unchanged.')
    parser.add_argument('--research-model', type=Path,
                        help='Actual applied research project, required for the research case.')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output must be a new directory; existing projects are not overwritten.')
    cases = args.case or ('f4', 'capture', 'h7')
    if len(cases) != len(set(cases)):
        parser.error('Each case may be requested once.')
    if 'h7' in cases and args.h743_input is None:
        parser.error('The h7 case requires --h743-input.')
    if 'research' in cases and args.research_model is None:
        parser.error('The research case requires --research-model.')
    fixture = args.h743_input.resolve(strict=True) if args.h743_input else None
    inputs = {path.relative_to(fixture).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in fixture.rglob('*') if path.is_file()} if fixture else {}
    if fixture and (not inputs or any(path.is_symlink() for path in fixture.rglob('*'))):
        parser.error('Input must be an ordinary, populated CubeMX fixture directory.')
    research_path = args.research_model.resolve(strict=True) if args.research_model else None
    research_hash = hashlib.sha256(research_path.read_bytes()).hexdigest() if research_path else None
    service = FccgService(SCG)
    records = []
    for name in cases:
        if name == 'h7':
            model, _ = Scenario_Create(service, fixture, 'eskf20', 1, {})
            model.device_instances = [replace(row, interface='i2c', profile='bosch_sync_400_hz')
                                     if row.instance_id == 'imu0' else row
                                     for row in model.device_instances]
            model.base_components.append('silverstar.installation.mag_rotation')
            pins = {'imu0:drdy': 'BMI088_A_INT2_SYNC_READY',
                    'imu0:auxiliary_drdy': 'BMI088_G_INT3_A_INT1_SYNC_NET'}
            model.resource_assignments.update(pins)
            model = service.ProjectConfiguration_Reconcile(model).model
            model.resource_assignments.update(pins)
        elif name == 'research':
            model = ProjectModel_Load(research_path)
        else:
            model = ReferenceProject_Create('GuiConvergence_' + name, catalog=service.catalog)
            if name == 'capture':
                model.base_components.append('silverstar.installation.capture')
                model.device_instances = [replace(row, profile='jy901b_mag_capture')
                    if row.plugin == 'silverstar.device.imu.jy901b' else row
                    for row in model.device_instances]
        LoggingProfile_Reconcile(model, service.catalog)
        validation = Project_Validate(model, service.catalog)
        if not validation.valid:
            raise ValueError(str(validation))
        destination = args.output / name
        TargetGeneration_Apply(model, service.catalog, WorkspacePolicy(SCG), destination, TargetScope.FLIGHT)
        records.append({'name': name, 'project': str((destination / 'Flight_Controller').resolve()),
                        'model': model.Dictionary_Get()})
        print(name + ': generated', flush=True)
    unchanged = not fixture or inputs == {
        path.relative_to(fixture).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fixture.rglob('*') if path.is_file()}
    research_unchanged = not research_path or research_hash == hashlib.sha256(research_path.read_bytes()).hexdigest()
    if not unchanged or not research_unchanged:
        raise ValueError('An input changed during generation.')
    (args.output / 'generation.json').write_text(json.dumps({
        'projects': records, 'hardware_fixture': str(fixture) if fixture else None, 'fixture_hashes': inputs,
        'research_model': str(research_path) if research_path else None,
        'research_model_sha256': research_hash, 'research_model_unchanged': research_unchanged,
        'fixture_unchanged': unchanged, 'hardware_tested': False}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return 0


if __name__ == '__main__':
    raise SystemExit(Main())
