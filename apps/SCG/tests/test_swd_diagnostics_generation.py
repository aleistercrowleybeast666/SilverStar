"""SCG owns schema/binder metadata; no firmware payload mutation is required."""
import json
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.generator.render import GeneratedFiles_Render, MetadataFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
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
    assert len(files)==22
    assert not any(path.endswith('.ssdiag') for path in graph.sources)
    makefile=metadata['Makefile'].decode() if isinstance(metadata['Makefile'],bytes) else metadata['Makefile']
    assert 'diagnostics/bind.py' not in makefile


def test_generated_source_contract_is_the_canonical_repository_contract(builtin_catalog):
    from silverstar_diagnostics.contract import Contract_Get
    model=ReferenceProject_Create('DiagnosticContract',catalog=builtin_catalog)
    files=MetadataFiles_Render(model,builtin_catalog,SourceGraph_Resolve(model,builtin_catalog))
    assert json.loads(files['DiagnosticContract.ssdiag'])['entries']==[e['id'] for e in Contract_Get()['entries']]
