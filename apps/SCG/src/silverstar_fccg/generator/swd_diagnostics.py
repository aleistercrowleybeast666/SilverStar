"""Generated-only post-build diagnostics, without modifying firmware payloads."""
import json
from silverstar_diagnostics.contract import Schema_Create
from silverstar_diagnostics.targets import Target_Get
from silverstar_diagnostics.contract import DiagnosticError


def SwdDiagnostics_Render(model, catalog):
    part = model.hardware.mcu
    if not part:
        metadata = catalog.Component_Get(model.mcu).metadata
        part = metadata.get('part', metadata.get('mcu', 'unknown'))
    try: part = Target_Get(part).name
    except DiagnosticError: pass  # Schema remains explicit; unsupported target cannot bind.
    return {f'{model.identity.name}.ssdiag': json.dumps(Schema_Create(part or 'unknown'),ensure_ascii=False,indent=2)}
