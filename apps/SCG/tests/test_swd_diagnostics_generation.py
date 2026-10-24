"""SCG owns schema/binder metadata; no firmware payload mutation is required."""
import json
from types import SimpleNamespace

import pytest

from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import GeneratedFiles_Render, MetadataFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.generator.swd_diagnostics import SwdDiagnostics_Render
from silverstar_diagnostics.targets import Target_Get


def test_generated_schema_and_binder_follow_the_actual_model(builtin_catalog):
    model=ReferenceProject_Create('DiagnosticGeneration',catalog=builtin_catalog)
    graph=SourceGraph_Resolve(model,builtin_catalog)
    files=GeneratedFiles_Render(model,builtin_catalog,graph)
    metadata=MetadataFiles_Render(model,builtin_catalog,graph)
    schema=json.loads(metadata['DiagnosticGeneration.ssdiag'])
    assert schema['target']==Target_Get(model.hardware.mcu).name
    assert schema['binding'] is None and schema['diagnostics']=='silverstar.swd-diagnostics/1'
    assert schema['entries']==['task.preparation','thread.estimator','sensor.ins_solution','thread.logger']
    root=json.loads(metadata['Flight.ssdiag'])
    assert root['role']=='flight' and root['schema']['target']==schema['target']
    assert root['state']=='pending_build' and root['builds']=={} and root['schema']['binding'] is None
    assert root['maintenance']['uart']['baudrate']==230400
    assert len(files)==22
    assert not any(path.endswith('.ssdiag') for path in graph.sources)
    makefile=metadata['Makefile'].decode() if isinstance(metadata['Makefile'],bytes) else metadata['Makefile']
    assert 'diagnostics/bind.py' not in makefile
    assert 'FCCG_BUILD_ARTIFACT|ELF|$(BUILD_ROOT)/$(TARGET).elf' in makefile
    assert not any('ssdiag_runtime' in path or 'ssdiag_bind.py' in path for path in metadata)
    assert 'ssdiag-bind' not in makefile and 'ssdiag_bind.py' not in makefile


def test_generated_source_contract_is_the_canonical_repository_contract(builtin_catalog):
    from silverstar_diagnostics.contract import Contract_Get
    model=ReferenceProject_Create('DiagnosticContract',catalog=builtin_catalog)
    files=MetadataFiles_Render(model,builtin_catalog,SourceGraph_Resolve(model,builtin_catalog))
    assert json.loads(files['DiagnosticContract.ssdiag'])['entries']==[e['id'] for e in Contract_Get()['entries']]


def test_catalog_free_metadata_preserves_protocol_without_inventing_uart():
    model=ReferenceProject_Create('CatalogFree')
    files=SwdDiagnostics_Render(model,None,'all:\n\t@echo built\n')
    root=json.loads(files['Flight.ssdiag'])
    selection=model.protocols['maintenance']
    assert root['maintenance']==dict(component=selection.component,
        package_version=selection.version,profile=selection.profile)
    assert root['schema']['target']==Target_Get(model.hardware.mcu).name
    assert root['state']=='pending_build' and root['builds']=={} and root['schema']['binding'] is None
    assert json.loads(files['CatalogFree.ssdiag'])['target']==root['schema']['target']
    assert b'FCCG_BUILD_ARTIFACT|ELF|$(BUILD_ROOT)/$(TARGET).elf' in files['Makefile']


def test_catalog_metadata_rejects_invalid_resolved_uart(builtin_catalog,monkeypatch):
    model=ReferenceProject_Create('InvalidUart',catalog=builtin_catalog)
    assignment=SimpleNamespace(requirement=SimpleNamespace(binding_macro='PROJECT_RESOURCE_CONSOLE_UART'),
        provision=SimpleNamespace(metadata=dict(baud_rate=None,word_length=8,parity='none',
                                               stop_bits=1,handle='huart3',peripheral='USART3')))
    monkeypatch.setattr('silverstar_fccg.generator.maintenance_uart.ResourceAssignments_Resolve',
        lambda *_: SimpleNamespace(valid=True,errors=(),assignments=[assignment]))
    with pytest.raises(ValueError,match='explicit CubeMX baud'):
        SwdDiagnostics_Render(model,builtin_catalog)
